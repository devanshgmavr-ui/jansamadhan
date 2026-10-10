"""Government routing portal API (G3): neutral operational wording only.

Every endpoint except POST /auth/login requires get_current_government_user:
public access tokens ("access") fail the type check, so public credentials
can never authorize here. Business logic lives in
government_review_service; routers authenticate, validate, locate, call the
service, and serialize. Static routes are registered before /{ticket} so
"sweep-escalations" is never captured as a ticket.
"""

import json as _json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import bearer_scheme, get_current_government_user
from app.core import security
from app.db.database import get_db
from app.models.government import (
    GovernmentAction,
    GovernmentReview,
    GovernmentReviewStatus,
    GovernmentUser,
)
from app.models.problem import Problem, ProblemVersion
from app.schemas.government import (
    GovActionOut,
    GovAssignBody,
    GovDashboardOut,
    GovHistoryItem,
    GovLoginRequest,
    GovMessageResponse,
    GovQueueItem,
    GovQueueOut,
    GovReasonBody,
    GovSettingBody,
    GovSolutionReviewBody,
    GovRequestDetailOut,
    GovSweepOut,
    GovTokenResponse,
    GovUserOut,
)
from app.services import government_review_service
from app.services.ai import problem_review_service

router = APIRouter(prefix="/government", tags=["government"])

REVIEW_STATES = tuple(s.value for s in GovernmentReviewStatus)

GOVERNMENT_ONLY_DETAIL = (
    "Government review request not found."  # 404 keeps ticket probing blind
)


def _to_user_out(official: GovernmentUser) -> GovUserOut:
    return GovUserOut(
        id=official.id,
        employee_id=official.employee_id,
        full_name=official.full_name,
        designation=official.designation,
        is_active=official.is_active,
    )


def _actor_map(db: Session, actor_ids: set) -> dict:
    """Batch-load officials for audit display; unknown/system actors stay
    system-labelled. Only safe display fields are ever exposed."""
    from app.schemas.government import GovActorOut

    mapping = {}
    ids = [a for a in actor_ids if a is not None]
    if ids:
        rows = (
            db.execute(
                select(GovernmentUser).where(GovernmentUser.id.in_(ids))
            )
            .scalars()
            .all()
        )
        for row in rows:
            mapping[row.id] = GovActorOut(
                kind="official",
                employee_id=row.employee_id,
                full_name=row.full_name,
            )
    return mapping


def _history_items(db: Session, problem: Problem) -> list:
    rows = (
        db.execute(
            select(GovernmentAction)
            .where(GovernmentAction.problem_id == problem.id)
            .order_by(GovernmentAction.created_at.asc())
        )
        .scalars()
        .all()
    )
    actors = _actor_map(db, {r.actor_id for r in rows})
    from app.schemas.government import GovActorOut

    def _actor_for(row) -> GovActorOut:
        # Explicit stored kind wins (G7 actor_type); older rows without it
        # fall back to the original derivation. Public-user events never
        # expose an email address.
        if row.actor_type == "PUBLIC_USER":
            return GovActorOut(kind="public_user")
        if row.actor_id is not None:
            official = actors.get(row.actor_id)
            if official is not None:
                return official
            return GovActorOut(kind="official")
        return GovActorOut(kind="system")

    return [
        GovHistoryItem(
            action=r.action,
            previous_status=r.previous_status,
            new_status=r.new_status,
            actor=_actor_for(r),
            reason=r.reason,
            created_at=r.created_at,
        )
        for r in rows
    ]


def _gov_request_or_404(
    db: Session, ticket: str
) -> tuple[Problem, GovernmentReview]:
    """A ticket is a government request only while a GovernmentReview row
    exists for it. Anything else (unknown ticket, legacy pre-routing
    problem) is a flat 404."""
    problem = (
        db.execute(select(Problem).where(Problem.ticket == ticket))
        .scalars()
        .first()
    )
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=GOVERNMENT_ONLY_DETAIL
        )
    review = government_review_service.get_for_problem(db, problem.id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=GOVERNMENT_ONLY_DETAIL
        )
    return problem, review


def _list(raw) -> list:
    try:
        val = _json.loads(raw) if raw else []
        return val if isinstance(val, list) else []
    except Exception:
        return []


def _detail_out(
    db: Session, problem: Problem, review: GovernmentReview
) -> GovRequestDetailOut:
    from app.schemas.government import (
        GovAIReviewOut,
        GovReviewStateOut,
        GovVersionOut,
    )

    versions = (
        db.execute(
            select(ProblemVersion)
            .where(ProblemVersion.problem_id == problem.id)
            .order_by(ProblemVersion.version_number.asc())
        )
        .scalars()
        .all()
    )
    ai = problem_review_service.latest_review(db, problem)
    ai_out = None
    if ai is not None and ai.status == "COMPLETED":
        version_number = 0
        if ai.version_id is not None:
            version_row = db.get(ProblemVersion, ai.version_id)
            if version_row is not None:
                version_number = version_row.version_number
        similar = (
            db.query(problem_review_service.AIReviewSimilar)
            .filter(problem_review_service.AIReviewSimilar.review_id == ai.id)
            .all()
        )
        id_to_ticket = {}
        if similar:
            for t, pid in db.query(
                problem_review_service.Problem.ticket,
                problem_review_service.Problem.id,
            ).filter(
                problem_review_service.Problem.id.in_(
                    [s.problem_id for s in similar]
                )
            ):
                id_to_ticket[pid] = t
        ai_out = GovAIReviewOut(
            review_number=ai.review_number,
            version_number=version_number,
            provider=ai.provider,
            model=ai.model,
            status=ai.status,
            decision=ai.decision,
            reason=ai.reason,
            missing_info=_list(ai.missing_info),
            category=ai.category,
            affected_group=ai.affected_group,
            geo_context=ai.geo_context,
            problem_type=ai.problem_type,
            scope=ai.scope,
            tech_areas=_list(ai.tech_areas),
            tags=_list(ai.tags_suggested),
            duplicate_status=ai.duplicate_status,
            similar=[
                {"ticket": id_to_ticket.get(s.problem_id, "?"), "relation": s.relation}
                for s in similar
            ],
            created_at=ai.created_at,
        )
    actors = _actor_map(db, {review.decided_by} if review.decided_by else set())
    from app.schemas.government import GovActorOut

    decided_by = None
    if review.decided_by is not None:
        decided_by = actors.get(review.decided_by, GovActorOut(kind="system"))
    return GovRequestDetailOut(
        ticket=problem.ticket,
        title=problem.title,
        description=problem.description,
        category=problem.category,
        location=problem.location,
        affected_group=problem.affected_group,
        severity=problem.severity,
        desired_solution_type=problem.desired_solution_type,
        skills=problem.skills,
        supporting_info=problem.supporting_info,
        problem_status=problem.status,
        current_version=problem.current_version,
        created_at=problem.created_at,
        updated_at=problem.updated_at,
        versions=[
            GovVersionOut(
                version_number=v.version_number,
                title=v.title,
                category=v.category,
                location=v.location,
                description=v.description,
                affected_group=v.affected_group,
                severity=v.severity,
                desired_solution_type=v.desired_solution_type,
                skills=v.skills,
                supporting_info=v.supporting_info,
                revision_note=v.revision_note,
                created_at=v.created_at,
            )
            for v in versions
        ],
        ai_review=ai_out,
        government=GovReviewStateOut(
            review_status=review.status,
            pending_since=review.pending_since,
            sla_due_at=review.sla_due_at,
            expired=government_review_service.is_expired(review),
            decided_at=review.decided_at,
            decided_by=decided_by,
            escalation_flag=review.escalation_flag,
            info_request=review.info_request,
            user_response=review.user_response,
        ),
        history=_history_items(db, problem),
    )


def _action_out(problem: Problem, review: GovernmentReview) -> GovActionOut:
    return GovActionOut(
        ticket=problem.ticket,
        review_status=review.status,
        problem_status=problem.status,
        decided_at=review.decided_at,
    )


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

@router.post("/auth/login", response_model=GovTokenResponse)
def gov_login(
    data: GovLoginRequest, request: Request, db: Session = Depends(get_db)
):
    """Official sign-in with provisioned employee_id + password. No email,
    no OTP, no password-reset email: credentials are provisioned
    administratively. Generic errors only: existence, password, and
    active-state are never distinguished. Throttled per client IP."""
    from app.core import ratelimit

    key = f"gov:{request.client.host if request.client else 'unknown'}"
    if ratelimit.is_blocked(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )
    official = (
        db.execute(
            select(GovernmentUser).where(
                GovernmentUser.employee_id == data.employee_id.strip()
            )
        )
        .scalars()
        .first()
    )
    valid = (
        official is not None
        and official.is_active
        and security.verify_password(data.password, official.password_hash)
    )
    if not valid:
        ratelimit.record_failure(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )
    ratelimit.record_success(key)
    return GovTokenResponse(
        access_token=security.create_government_token(official.id)
    )


@router.post("/auth/logout", response_model=GovMessageResponse)
def gov_logout(
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Revoke the current government session JTI. Idempotent: logging out
    twice (or with an already-revoked token, which would 401 first) is safe."""
    from app.core import gov_revocation

    payload = security.decode_token(
        credentials.credentials,
        expected_type=security.GOVERNMENT_TOKEN_TYPE,
    )
    gov_revocation.revoke(payload.get("jti") or "")
    return GovMessageResponse(message="Signed out successfully.")


@router.get("/auth/me", response_model=GovUserOut)
def gov_me(
    official: GovernmentUser = Depends(get_current_government_user),
):
    return _to_user_out(official)


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

@router.get("/dashboard", response_model=GovDashboardOut)
def gov_dashboard(
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Server-derived routing counts. No charts, no analytics."""
    rows = (
        db.execute(
            select(GovernmentReview.status, func.count())
            .group_by(GovernmentReview.status)
        )
        .all()
    )
    counts = {state: 0 for state in REVIEW_STATES}
    for state, count in rows:
        if state in counts:
            counts[state] = count
    return GovDashboardOut(
        pending=counts[GovernmentReviewStatus.PENDING.value],
        attention=counts[GovernmentReviewStatus.AUTO_ESCALATED.value],
        government_issue=counts[GovernmentReviewStatus.GOVERNMENT_ISSUE.value],
        assigned_to_public=counts[
            GovernmentReviewStatus.ASSIGNED_TO_PUBLIC.value
        ],
        more_information_required=counts[
            GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value
        ],
    )


# --------------------------------------------------------------------------
# Queue, detail, history, sweep (static routes first: see module docstring)
# --------------------------------------------------------------------------

@router.get("/requests", response_model=GovQueueOut)
def gov_queue(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Routing queue. Actionable ordering: expired/escalated first, then
    oldest pending window first. Expiry is server-computed per row."""
    if status_filter is not None and status_filter not in REVIEW_STATES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown government review status.",
        )
    stmt = (
        select(GovernmentReview, Problem)
        .join(Problem, Problem.id == GovernmentReview.problem_id)
        .order_by(GovernmentReview.pending_since.asc())
    )
    if status_filter:
        stmt = stmt.where(GovernmentReview.status == status_filter)
    all_rows = db.execute(stmt).all()
    total = len(all_rows)

    def _rank(pair) -> tuple:
        review, _ = pair
        flag = 0
        if review.status == GovernmentReviewStatus.AUTO_ESCALATED.value:
            flag = 0
        elif government_review_service.is_expired(review):
            flag = 0
        else:
            flag = 1
        return (flag, review.pending_since)

    ordered = sorted(all_rows, key=_rank)
    start = (page - 1) * page_size
    items = []
    for review, problem in ordered[start : start + page_size]:
        items.append(
            GovQueueItem(
                ticket=problem.ticket,
                title=problem.title,
                category=problem.category,
                location=problem.location,
                affected_group=problem.affected_group,
                problem_status=problem.status,
                review_status=review.status,
                pending_since=review.pending_since,
                sla_due_at=review.sla_due_at,
                expired=government_review_service.is_expired(review),
                escalation_flag=review.escalation_flag,
                decided_at=review.decided_at,
                created_at=problem.created_at,
            )
        )
    pages = (total + page_size - 1) // page_size if total else 0
    return GovQueueOut(
        total=total, page=page, page_size=page_size, pages=pages, items=items
    )


@router.post("/requests/sweep-escalations", response_model=GovSweepOut)
def gov_sweep(
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Explicit escalation sweep (no cron/workers in G3). Delegates to the
    idempotent G2 service; reports what was evaluated and escalated."""
    now = government_review_service._utcnow()
    due_ids = [
        row_id
        for (row_id,) in db.execute(
            select(GovernmentReview.problem_id).where(
                GovernmentReview.status
                == GovernmentReviewStatus.PENDING.value,
                GovernmentReview.sla_due_at <= now,
            )
        ).all()
    ]
    escalated_ids = government_review_service.sweep_expired(db, now=now)
    id_to_ticket = (
        {
            pid: ticket
            for pid, ticket in db.execute(
                select(Problem.id, Problem.ticket).where(
                    Problem.id.in_(escalated_ids)
                )
            ).all()
        }
        if escalated_ids
        else {}
    )
    return GovSweepOut(
        evaluated=len(due_ids),
        escalated=len(escalated_ids),
        escalated_tickets=[
            id_to_ticket[pid] for pid in escalated_ids if pid in id_to_ticket
        ],
    )


@router.get("/requests/export")
def gov_export_requests(
    report: str = Query(default="complaints", max_length=30),
    format: str = Query(default="csv", max_length=10),
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """CSV/PDF report downloads (Phase 4, Part D). Static route: must stay
    registered before /requests/{ticket} so 'export' is never captured."""
    from fastapi.responses import Response

    from app.services import export_service

    if report == "analytics":
        from app.services import analytics_service as _analytics

        summary = _analytics.overview(db)
        headers = ["metric", "value"]
        rows = [
            ["total_complaints", summary["total_complaints"]],
            ["public_challenges", summary["public_challenges"]],
            ["government_issues", summary["government_issues"]],
            ["solutions_submitted", summary["solutions_submitted"]],
            ["solutions_selected", summary["solutions_selected"]],
            ["completed_projects", summary["completed_projects"]],
        ]
    elif report == "complaints":
        headers, rows = export_service.complaint_rows(db)
    elif report == "challenges":
        headers, all_rows = export_service.complaint_rows(db)
        rows = [r for r in all_rows if r[5] in (
            "OPEN", "COLLABORATION", "IN_DEVELOPMENT", "PILOT",
            "IMPLEMENTED")]
    elif report == "implementations":
        headers, rows = export_service.implementation_rows(db)
    elif report == "solutions":
        headers, rows = export_service.solution_rows(db)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Report must be complaints, challenges, implementations, solutions, or analytics.",
        )
    if format == "pdf":
        return Response(
            content=export_service.to_pdf(
                f"JanSamadhan {report} report", headers, rows),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{report}.pdf"'
            },
        )
    return Response(
        content=export_service.to_csv(headers, rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{report}.csv"'
        },
    )


@router.get("/requests/{ticket}", response_model=GovRequestDetailOut)
def gov_detail(
    ticket: str,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    problem, review = _gov_request_or_404(db, ticket)
    return _detail_out(db, problem, review)


@router.get("/requests/{ticket}/history")
def gov_history(
    ticket: str,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    problem, _ = _gov_request_or_404(db, ticket)
    return _history_items(db, problem)


# --------------------------------------------------------------------------
# Routing actions (all via the G2 state-machine service)
# --------------------------------------------------------------------------

@router.post("/requests/{ticket}/assign-public", response_model=GovActionOut)
def gov_assign_public(
    ticket: str,
    data: GovAssignBody,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Route to the public solution process: review becomes
    ASSIGNED_TO_PUBLIC while the problem itself becomes OPEN (reused, never
    a second public state)."""
    problem, _ = _gov_request_or_404(db, ticket)
    review = government_review_service.apply_decision(
        db,
        problem,
        to_status=GovernmentReviewStatus.ASSIGNED_TO_PUBLIC.value,
        actor_id=official.id,
        reason=(data.reason or "").strip() or None,
    )
    return _action_out(problem, review)


@router.post(
    "/requests/{ticket}/mark-government-issue", response_model=GovActionOut
)
def gov_mark_issue(
    ticket: str,
    data: GovReasonBody,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Classify as a government-side issue. A meaningful reason is required
    for auditability. Never becomes public."""
    problem, _ = _gov_request_or_404(db, ticket)
    review = government_review_service.apply_decision(
        db,
        problem,
        to_status=GovernmentReviewStatus.GOVERNMENT_ISSUE.value,
        actor_id=official.id,
        reason=data.reason.strip(),
    )
    return _action_out(problem, review)


@router.post(
    "/requests/{ticket}/request-information", response_model=GovActionOut
)
def gov_request_information(
    ticket: str,
    data: GovReasonBody,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Ask the submitting user for more information. The reason is stored
    as info_request and shown to the user (G4); empty reasons are rejected
    both here (schema) and in the service (whitespace guard)."""
    problem, _ = _gov_request_or_404(db, ticket)
    review = government_review_service.apply_decision(
        db,
        problem,
        to_status=GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value,
        actor_id=official.id,
        reason=data.reason.strip(),
        info_request=data.reason.strip(),
    )
    return _action_out(problem, review)


# --------------------------------------------------------------------------
# Phase 3: solution review/selection + implementation tracking
# --------------------------------------------------------------------------

def _solution_out(db: Session, solution) -> dict:
    from app.services import solution_service

    return {
        "ticket": solution.ticket,
        "problem_ticket": solution_service.problem_ticket_of(db, solution),
        "title": solution.title,
        "short_description": solution.short_description,
        "status": solution.status,
        "review_status": solution.review_status,
        "review_reason": solution.review_reason,
        "reviewed_at": solution.reviewed_at,
        "is_selected": solution.is_selected,
        "created_at": solution.created_at,
        "updated_at": solution.updated_at,
    }


@router.get("/requests/{ticket}/solutions")
def gov_request_solutions(
    ticket: str,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """All submitted solutions of one routed problem, newest last, for
    official review. Officials only; submitters use the public API."""
    from app.services import solution_service

    problem, _ = _gov_request_or_404(db, ticket)
    rows, _ = solution_service.solutions_for_government(db, problem.ticket)
    return {"ticket": problem.ticket, "total": len(rows),
            "items": [_solution_out(db, s) for s in rows]}


@router.post("/solutions/{ticket}/review")
def gov_review_solution(
    ticket: str,
    data: GovSolutionReviewBody,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Approve / reject / request-modification on a solution. Rejected
    solutions are kept, never deleted. Static route: registered before
    any /{ticket} capture could shadow it (solutions live outside
    /requests)."""
    from app.services import solution_service

    solution = solution_service.review_solution(
        db, official, ticket, data.decision.strip().upper(),
        reason=(data.reason or "").strip() or None,
    )
    return _solution_out(db, solution)


@router.post("/solutions/{ticket}/select")
def gov_select_solution(
    ticket: str,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Mark the winning solution. Exactly one per problem: any previous
    selection is cleared (archived, never deleted). Requires APPROVED."""
    from app.services import solution_service

    solution = solution_service.select_solution(db, official, ticket)
    return _solution_out(db, solution)


@router.get("/requests/{ticket}/implementation")
def gov_list_implementation(
    ticket: str,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Implementation updates of a government issue, oldest first."""
    from app.services import implementation_service

    problem, _ = _gov_request_or_404(db, ticket)
    rows = implementation_service.list_updates(db, problem.id)
    attach = implementation_service.attachments_for(db, [u.id for u in rows])
    return {
        "ticket": problem.ticket,
        "total": len(rows),
        "items": [_implementation_out(problem.ticket, u, attach.get(u.id, []))
                  for u in rows],
    }


@router.post("/requests/{ticket}/implementation", status_code=201)
def gov_create_implementation(
    ticket: str,
    stage: str = Form(min_length=3, max_length=40),
    title: str = Form(min_length=5, max_length=200),
    description: str | None = Form(default=None, max_length=5000),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    """Append a progress update (with optional documents/images) to a
    government issue. Append-only; stage must use the closed vocabulary."""
    from app.services import implementation_service

    problem, _ = _gov_request_or_404(db, ticket)
    update = implementation_service.create_update(
        db, official, problem.ticket, stage=stage.strip().upper(),
        title=title, description=description, files=files,
    )
    attach = implementation_service.attachments_for(db, [update.id])
    return _implementation_out(
        problem.ticket, update, attach.get(update.id, []))


@router.get("/requests/{ticket}/implementation/attachments/{attachment_id}/download")
def gov_download_implementation_attachment(
    ticket: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    from app.services import implementation_service
    from fastapi.responses import Response

    problem, _ = _gov_request_or_404(db, ticket)
    own_ids = {u.id for u in implementation_service.list_updates(db, problem.id)}
    record, content = implementation_service.read_attachment(
        db, attachment_id)
    if record.update_id not in own_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found."
        )
    return Response(
        content=content,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{record.original_name}"'
        },
    )


def _implementation_out(ticket: str, update, attachments: list) -> dict:
    return {
        "id": update.id,
        "problem_ticket": ticket,
        "stage": update.stage,
        "title": update.title,
        "description": update.description,
        "attachments": [
            {
                "id": a.id,
                "original_name": a.original_name,
                "mime_type": a.mime_type,
                "size_bytes": a.size_bytes,
                "created_at": a.created_at,
            }
            for a in attachments
        ],
        "created_at": update.created_at,
    }


# --------------------------------------------------------------------------
# Phase 4: analytics, exports, audit, settings, activity feed
# --------------------------------------------------------------------------

@router.get("/analytics/overview")
def gov_analytics(
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    from app.services import analytics_service

    return analytics_service.overview(db)


@router.get("/audit")
def gov_audit(
    official: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=40),
    ticket: str | None = Query(default=None, max_length=20),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=1000),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current: GovernmentUser = Depends(get_current_government_user),
):
    from app.services import export_service

    headers, rows = export_service.audit_rows(
        db, official=official, action=action, ticket=ticket,
        date_from=date_from, date_to=date_to, limit=page * limit)
    total = len(rows)
    page_rows = rows[(page - 1) * limit:page * limit]
    return {"total": total, "page": page, "limit": limit,
            "items": [dict(zip(headers, r)) for r in page_rows]}


@router.get("/settings")
def gov_list_settings(
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    from app.services import settings_service

    return {"items": settings_service.list_settings(db)}


@router.put("/settings/{key}")
def gov_update_setting(
    key: str,
    data: GovSettingBody,
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    from app.services import settings_service

    return settings_service.set_setting(db, key.strip(), data.value or "")


@router.get("/notifications/feed")
def gov_notification_feed(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    official: GovernmentUser = Depends(get_current_government_user),
):
    from sqlalchemy import desc

    from app.models.execution import ImplementationUpdate
    from app.models.problem import Problem
    from app.models.solution import Solution

    feed: list[dict] = []
    pending = db.execute(
        select(GovernmentReview)
        .where(GovernmentReview.status == "PENDING")
        .order_by(desc(GovernmentReview.pending_since)).limit(limit)
    ).scalars().all()
    for r in pending:
        feed.append({"kind": "pending_review",
                     "ticket": _ticket_of(db, r.problem_id),
                     "created_at": r.pending_since})
    sols = db.execute(
        select(Solution).order_by(desc(Solution.created_at)).limit(limit)
    ).scalars().all()
    for s in sols:
        feed.append({"kind": "solution_submitted", "ticket": s.ticket,
                     "created_at": s.created_at})
    ups = db.execute(
        select(ImplementationUpdate)
        .order_by(desc(ImplementationUpdate.created_at)).limit(limit)
    ).scalars().all()
    for u in ups:
        feed.append({"kind": "implementation_update",
                     "ticket": _ticket_of(db, u.problem_id),
                     "created_at": u.created_at})
    feed.sort(key=lambda e: e["created_at"], reverse=True)
    return {"total": len(feed), "items": feed[:limit]}


def _ticket_of(db: Session, problem_id) -> str:
    from app.models.problem import Problem

    problem = db.get(Problem, problem_id)
    return problem.ticket if problem else "?"
