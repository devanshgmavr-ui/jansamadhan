"""Government routing lifecycle foundation (G2): state machine, SLA, audit.

Owns every mutation of GovernmentReview / GovernmentAction and the mirrored
Problem.status for the government-routing family of states. Each public
function performs its review-row update, the Problem.status mirror, and the
audit insert inside a single transaction: a failure rolls back all three, so
Problem.status can never diverge from its GovernmentReview row.

G3 will call apply_decision() from government HTTP endpoints; G2 already
wires the AI-approval and more-information paths internally. There is no
government HTTP API here.
"""

from datetime import datetime, timedelta, timezone

import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.government import (
    ActorType,
    GovernmentAction,
    GovernmentActionType,
    GovernmentReview,
    GovernmentReviewStatus,
    GovernmentUser,
)
from app.models.problem import Problem, ProblemStatus
from app.services import notification_service

# Exactly 24 hours from pending_since. No business hours, no holidays,
# no department-specific windows.
SLA_HOURS = 24

# The only legal government-routing edges. Terminal states (ASSIGNED_TO_
# PUBLIC, GOVERNMENT_ISSUE) have no outgoing edges: history is append-only
# and routing decisions are never silently undone.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    GovernmentReviewStatus.PENDING.value: frozenset(
        {
            GovernmentReviewStatus.ASSIGNED_TO_PUBLIC.value,
            GovernmentReviewStatus.GOVERNMENT_ISSUE.value,
            GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value,
            GovernmentReviewStatus.AUTO_ESCALATED.value,
        }
    ),
    GovernmentReviewStatus.AUTO_ESCALATED.value: frozenset(
        {
            GovernmentReviewStatus.ASSIGNED_TO_PUBLIC.value,
            GovernmentReviewStatus.GOVERNMENT_ISSUE.value,
            GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value,
        }
    ),
    GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value: frozenset(
        {GovernmentReviewStatus.PENDING.value}
    ),
    GovernmentReviewStatus.ASSIGNED_TO_PUBLIC.value: frozenset(),
    GovernmentReviewStatus.GOVERNMENT_ISSUE.value: frozenset(),
}

# GovernmentReview status -> mirrored Problem.status. ASSIGNED_TO_PUBLIC
# intentionally maps to OPEN so discovery, solutions, collaboration and the
# whole existing public lifecycle work unchanged.
REVIEW_TO_PROBLEM_STATUS: dict[str, str] = {
    GovernmentReviewStatus.PENDING.value: ProblemStatus.GOV_REVIEW_PENDING.value,
    GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value: (
        ProblemStatus.MORE_INFORMATION_REQUIRED.value
    ),
    GovernmentReviewStatus.GOVERNMENT_ISSUE.value: (
        ProblemStatus.GOVERNMENT_ISSUE.value
    ),
    GovernmentReviewStatus.AUTO_ESCALATED.value: ProblemStatus.AUTO_ESCALATED.value,
    GovernmentReviewStatus.ASSIGNED_TO_PUBLIC.value: ProblemStatus.OPEN.value,
}

_ACTION_FOR_TARGET: dict[str, str] = {
    GovernmentReviewStatus.ASSIGNED_TO_PUBLIC.value: (
        GovernmentActionType.ASSIGNED_TO_PUBLIC.value
    ),
    GovernmentReviewStatus.GOVERNMENT_ISSUE.value: (
        GovernmentActionType.MARKED_GOVERNMENT_ISSUE.value
    ),
    GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value: (
        GovernmentActionType.REQUESTED_INFORMATION.value
    ),
    GovernmentReviewStatus.AUTO_ESCALATED.value: (
        GovernmentActionType.AUTO_ESCALATED.value
    ),
}

# Problem statuses that keep a problem out of every public surface.
# Mirrors discovery_service.PUBLIC_STATUSES by exclusion; asserted in tests.
NON_PUBLIC_GOVERNMENT_STATUSES = frozenset(
    {
        ProblemStatus.GOV_REVIEW_PENDING.value,
        ProblemStatus.MORE_INFORMATION_REQUIRED.value,
        ProblemStatus.GOVERNMENT_ISSUE.value,
        ProblemStatus.AUTO_ESCALATED.value,
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Operational log: transitions and escalations only (ticket, action,
# states, actor kind, timestamp). Never passwords, OTPs, tokens, keys.
logger = logging.getLogger(__name__)


def sla_due_for(pending_since: datetime) -> datetime:
    """SLA deadline for a pending cycle. Pure function of the stored
    pending_since; never client-provided."""
    return pending_since + timedelta(hours=SLA_HOURS)


def review_to_problem_status(gov_status: str) -> str:
    """Mirrored Problem.status for a GovernmentReview status."""
    try:
        return REVIEW_TO_PROBLEM_STATUS[gov_status]
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown government review status: {gov_status}.",
        )


# Phase 1 decision classification. Single source of truth: assigning to the
# public means a PUBLIC challenge, a government issue means GOVERNMENT
# handling. Anything else has no resolution yet.
RESOLUTION_FOR_STATUS = {
    GovernmentReviewStatus.ASSIGNED_TO_PUBLIC.value: "PUBLIC",
    GovernmentReviewStatus.GOVERNMENT_ISSUE.value: "GOVERNMENT",
}


def resolution_type_for(gov_status: str | None) -> str | None:
    """Public classification for a review status, or None when undecided."""
    return RESOLUTION_FOR_STATUS.get(gov_status or "")


def assert_transition(from_status: str, to_status: str) -> None:
    """Reject illegal routing edges server-side. Raises 422."""
    allowed = ALLOWED_TRANSITIONS.get(from_status)
    if allowed is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown government review status: {from_status}.",
        )
    if to_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Illegal government transition: {from_status} "
                f"cannot move to {to_status}."
            ),
        )


def is_expired(review: GovernmentReview, now: datetime | None = None) -> bool:
    """A review is expired only while PENDING and past its SLA deadline.
    Pure predicate; performs no mutation (sweep/escalate act on it)."""
    if review.status != GovernmentReviewStatus.PENDING.value:
        return False
    moment = now or _utcnow()
    return moment > review.sla_due_at


def get_for_problem(db: Session, problem_id) -> GovernmentReview | None:    return (
        db.execute(
            select(GovernmentReview).where(
                GovernmentReview.problem_id == problem_id
            )
        )
        .scalars()
        .first()
    )


def _audit(
    db: Session,
    problem: Problem,
    *,
    action: str,
    previous_status: str | None,
    new_status: str,
    actor_id=None,
    actor_type: str | None = None,
    reason: str | None = None,
) -> GovernmentAction:
    row = GovernmentAction(
        problem_id=problem.id,
        ticket=problem.ticket,
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        actor_id=actor_id,
        actor_type=actor_type,
        reason=reason,
    )
    db.add(row)
    return row


def record_event(
    db: Session,
    problem: Problem,
    *,
    action: str,
    actor_id=None,
    actor_type: str | None = None,
    reason: str | None = None,
) -> GovernmentAction:
    """Append a standalone workflow audit event (Phase 4: solution and
    implementation lifecycle). No status change; flushed for use as a
    notification anchor, committed by the caller."""
    row = _audit(
        db, problem, action=action, previous_status=None,
        new_status=problem.status, actor_id=actor_id, actor_type=actor_type,
        reason=reason,
    )
    db.flush()
    return row


def ensure_pending_review(
    db: Session,
    problem: Problem,
    *,
    now: datetime | None = None,
    reason: str | None = None,
    commit: bool = True,
) -> GovernmentReview:
    """Create (or recycle for a new cycle) the PENDING review row for an
    AI-approved problem and mirror Problem.status. Idempotent per cycle:
    an already-PENDING row is returned unchanged with no extra audit event.
    Exactly one row per problem is enforced by the unique problem_id
    constraint; the row is locked for the transition.

    commit=False joins an outer transaction (used by the AI-approval path
    so the review row, classification, review state and audit event all
    commit atomically); standalone callers use the default commit=True."""
    moment = now or _utcnow()
    existing = (
        db.execute(
            select(GovernmentReview)
            .where(GovernmentReview.problem_id == problem.id)
            .with_for_update()
        )
        .scalars()
        .first()
    )
    if existing is None:
        review = GovernmentReview(
            problem_id=problem.id,
            status=GovernmentReviewStatus.PENDING.value,
            pending_since=moment,
            sla_due_at=sla_due_for(moment),
        )
        db.add(review)
        db.flush()
        audit_row = _audit(
            db,
            problem,
            action=GovernmentActionType.GOV_REVIEW_CREATED.value,
            previous_status=None,
            new_status=GovernmentReviewStatus.PENDING.value,
            actor_id=None,
            actor_type=ActorType.SYSTEM.value,
            reason=reason or "AI approved; eligible for government routing review.",
        )
        notify_audit = audit_row
    elif existing.status == GovernmentReviewStatus.PENDING.value:
        # Same cycle re-run (e.g. duplicate approval processing): no new
        # window, no duplicate audit event, and therefore no new notification.
        review = existing
        notify_audit = None
    elif existing.status in (
        GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value,
        GovernmentReviewStatus.AUTO_ESCALATED.value,
    ):
        previous = existing.status
        existing.status = GovernmentReviewStatus.PENDING.value
        existing.pending_since = moment
        existing.sla_due_at = sla_due_for(moment)
        existing.escalation_flag = False
        existing.decided_at = None
        existing.decided_by = None
        db.add(existing)
        audit_row = _audit(
            db,
            problem,
            action=GovernmentActionType.REOPENED_FOR_GOVERNMENT_REVIEW.value,
            previous_status=previous,
            new_status=GovernmentReviewStatus.PENDING.value,
            actor_id=None,
            actor_type=ActorType.SYSTEM.value,
            reason=reason or "Re-approved after user response; new review window.",
        )
        notify_audit = audit_row
        review = existing
    else:
        # ASSIGNED_TO_PUBLIC / GOVERNMENT_ISSUE are terminal: an approval
        # must never resurrect a routed problem through this path.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Government review already decided "
                f"({existing.status}); cannot reopen as pending."
            ),
        )
    problem.status = ProblemStatus.GOV_REVIEW_PENDING.value
    db.add(problem)
    if notify_audit is not None:
        # Joins the same transaction: state + audit + intent commit together.
        notification_service.queue_for_audit(
            db, problem=problem, audit=notify_audit
        )
    if commit:
        db.commit()
        # Delivery is independent: a mail failure only records FAILED.
        notification_service.deliver_for_problem(db, problem.id)
    else:
        db.flush()
    db.refresh(review)
    db.refresh(problem)
    return review


def apply_decision(
    db: Session,
    problem: Problem,
    *,
    to_status: str,
    actor_id,
    reason: str | None = None,
    info_request: str | None = None,
    now: datetime | None = None,
) -> GovernmentReview:
    """Apply one government routing decision atomically: review row +
    Problem.status mirror + audit row in a single transaction. Called by G3
    endpoints; G2 wires no HTTP to it. An actor (GovernmentUser id) is
    required: system events use escalate_if_expired(), never this path."""
    if actor_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A government routing decision requires an official actor.",
        )
    if to_status == GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value and not (
        info_request or ""
    ).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Requesting more information requires a reason for the user.",
        )
    if to_status == GovernmentReviewStatus.GOVERNMENT_ISSUE.value and not (
        reason or ""
    ).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Marking a government issue requires a reason for auditability.",
        )
    moment = now or _utcnow()
    review = (
        db.execute(
            select(GovernmentReview)
            .where(GovernmentReview.problem_id == problem.id)
            .with_for_update()
        )
        .scalars()
        .first()
    )
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No government review exists for this problem.",
        )
    assert_transition(review.status, to_status)
    previous = review.status
    review.status = to_status
    review.decided_at = moment
    review.decided_by = actor_id
    if to_status == GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value:
        review.info_request = (info_request or "").strip()
    db.add(review)
    # The information request itself is the auditable reason when no
    # separate reason was supplied, so history and email stay meaningful.
    audit_reason = reason
    if to_status == GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value and not (
        audit_reason or ""
    ).strip():
        audit_reason = review.info_request
    audit_row = _audit(
        db,
        problem,
        action=_ACTION_FOR_TARGET[to_status],
        previous_status=previous,
        new_status=to_status,
        actor_id=actor_id,
        actor_type=ActorType.GOVERNMENT_OFFICIAL.value,
        reason=audit_reason,
    )
    problem.status = review_to_problem_status(to_status)
    db.add(problem)
    notification_service.queue_for_audit(db, problem=problem, audit=audit_row)
    db.commit()
    logger.info(
        "government decision ticket=%s action=%s previous=%s new=%s actor=official at=%s",
        problem.ticket,
        _ACTION_FOR_TARGET[to_status],
        previous,
        to_status,
        moment.isoformat(),
    )
    notification_service.deliver_for_problem(db, problem.id)
    db.refresh(review)
    db.refresh(problem)
    return review


def record_information_provided(
    db: Session,
    problem: Problem,
    *,
    response_text: str | None,
    now: datetime | None = None,  # accepted for signature symmetry; unused
) -> GovernmentReview:
    """Record the user's answer to a MORE_INFORMATION_REQUIRED request.
    Stores the response and appends the audit event; the status change back
    to review happens through the normal revision -> AI re-review path."""
    _ = now
    review = (
        db.execute(
            select(GovernmentReview)
            .where(GovernmentReview.problem_id == problem.id)
            .with_for_update()
        )
        .scalars()
        .first()
    )
    if review is None or review.status != (
        GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This problem is not awaiting user information.",
        )
    review.user_response = (response_text or "").strip() or (
        "User submitted updated information."
    )
    db.add(review)
    _audit(
        db,
        problem,
        action=GovernmentActionType.INFORMATION_PROVIDED.value,
        previous_status=GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value,
        new_status=GovernmentReviewStatus.MORE_INFORMATION_REQUIRED.value,
        actor_id=None,
        actor_type=ActorType.PUBLIC_USER.value,
        reason=None,
    )
    db.commit()
    db.refresh(review)
    return review


def escalate_if_expired(
    db: Session, problem: Problem, *, now: datetime | None = None
) -> GovernmentReview | None:
    """Flip an expired PENDING review to AUTO_ESCALATED. Idempotent: already
    escalated, decided, or non-expired reviews are returned untouched with no
    new audit row, so repeated calls (portal retries, sweeps) are safe."""
    moment = now or _utcnow()
    review = (
        db.execute(
            select(GovernmentReview)
            .where(GovernmentReview.problem_id == problem.id)
            .with_for_update()
        )
        .scalars()
        .first()
    )
    if review is None or not is_expired(review, moment):
        return review
    review.status = GovernmentReviewStatus.AUTO_ESCALATED.value
    review.escalation_flag = True
    review.decided_at = moment
    review.decided_by = None
    db.add(review)
    audit_row = _audit(
        db,
        problem,
        action=GovernmentActionType.AUTO_ESCALATED.value,
        previous_status=GovernmentReviewStatus.PENDING.value,
        new_status=GovernmentReviewStatus.AUTO_ESCALATED.value,
        actor_id=None,
        actor_type=ActorType.SYSTEM.value,
        reason=(
            "No routing decision within the 24-hour review window; "
            "escalated in the government review queue. No department "
            "has accepted responsibility."
        ),
    )
    problem.status = ProblemStatus.AUTO_ESCALATED.value
    db.add(problem)
    notification_service.queue_for_audit(db, problem=problem, audit=audit_row)
    db.commit()
    logger.info(
        "government escalation ticket=%s action=%s previous=%s new=%s actor=system at=%s",
        problem.ticket,
        GovernmentActionType.AUTO_ESCALATED.value,
        GovernmentReviewStatus.PENDING.value,
        GovernmentReviewStatus.AUTO_ESCALATED.value,
        moment.isoformat(),
    )
    notification_service.deliver_for_problem(db, problem.id)
    db.refresh(review)
    db.refresh(problem)
    return review


def sweep_expired(
    db: Session, *, now: datetime | None = None, limit: int = 100
) -> list:
    """Escalate all expired PENDING reviews (bounded batch for G3 endpoint
    use). Returns the escalated problem ids. No scheduler is created here."""
    moment = now or _utcnow()
    rows = (
        db.execute(
            select(GovernmentReview)
            .where(
                GovernmentReview.status == GovernmentReviewStatus.PENDING.value,
                GovernmentReview.sla_due_at <= moment,
            )
            .order_by(GovernmentReview.sla_due_at.asc())
            .limit(max(limit, 1))
        )
        .scalars()
        .all()
    )
    escalated = []
    for review in rows:
        problem = db.get(Problem, review.problem_id)
        if problem is None:
            continue
        escalated_review = escalate_if_expired(db, problem, now=moment)
        if (
            escalated_review is not None
            and escalated_review.status
            == GovernmentReviewStatus.AUTO_ESCALATED.value
        ):
            escalated.append(problem.id)
    return escalated


def get_actor(db: Session, actor_id) -> GovernmentUser | None:
    """Fetch the official for attribution; G3 uses this to validate actors."""
    if actor_id is None:
        return None
    return db.get(GovernmentUser, actor_id)
