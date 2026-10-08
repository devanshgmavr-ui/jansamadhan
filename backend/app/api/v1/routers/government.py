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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
