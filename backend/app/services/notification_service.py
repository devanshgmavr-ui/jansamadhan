"""Workflow email notifications (G7): durable intents, independent delivery.

Design (preferred production pattern from the spec):
  1. The workflow transition commits state + audit + a PENDING notification
     intent in ONE transaction (exactly one intent per audit event via the
     unique audit_id anchor).
  2. Delivery is attempted afterwards, independently: SENT/FAILED is
     recorded with its own commit. A mail failure can therefore never roll
     back workflow state, and a crash between commit and delivery leaves a
     PENDING intent that retry_failed() picks up.

INFORMATION_PROVIDED is audit-only by product decision (no email).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.government import (
    GovernmentAction,
    GovernmentActionType,
    Notification,
    NotificationStatus,
    NotificationType,
)
from app.models.problem import Problem
from app.models.user import User

logger = logging.getLogger(__name__)

# Bounded retries for failed sends; scheduler-compatible (a future worker
# can call retry_failed periodically). No infinite loops.
MAX_ATTEMPTS = 3

# Audit action -> announced notification type. INFORMATION_PROVIDED is
# deliberately absent: user answers are audit-only, never emailed.
NOTIFY_FOR_ACTION: dict[str, str] = {
    GovernmentActionType.GOV_REVIEW_CREATED.value: (
        NotificationType.GOV_REVIEW_PENDING.value
    ),
    GovernmentActionType.REOPENED_FOR_GOVERNMENT_REVIEW.value: (
        NotificationType.GOV_REVIEW_PENDING.value
    ),
    GovernmentActionType.REQUESTED_INFORMATION.value: (
        NotificationType.MORE_INFORMATION_REQUIRED.value
    ),
    GovernmentActionType.ASSIGNED_TO_PUBLIC.value: (
        NotificationType.ASSIGNED_TO_PUBLIC.value
    ),
    GovernmentActionType.MARKED_GOVERNMENT_ISSUE.value: (
        NotificationType.GOVERNMENT_ISSUE.value
    ),
    GovernmentActionType.AUTO_ESCALATED.value: (
        NotificationType.AUTO_ESCALATED.value
    ),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _frontend_base() -> str:
    return (settings.FRONTEND_URL or "").rstrip("/")


def build_workflow_email(
    *,
    notif_type: str,
    ticket: str,
    title: str,
    reason: str | None = None,
) -> tuple[str, str, str]:
    """Return (subject, body, link) for a workflow event. Professional
    transactional copy: ticket, title, status, explanation, safe link. Never
    claims acceptance, departments, or officials; never embeds secrets (the
    link carries no token)."""
    base = _frontend_base()
    detail_link = f"{base}/problems/{ticket}"
    if notif_type == NotificationType.GOV_REVIEW_PENDING.value:
        subject = f"JanSamadhan {ticket}: awaiting government review"
        body = (
            f"Your JanSamadhan problem is awaiting government review.\n\n"
            f"Ticket: {ticket}\n"
            f"Title: {title}\n"
            f"Status: Government review pending\n\n"
            f"It has passed the initial AI review. It will become publicly "
            f"available only after it is assigned to the public.\n\n"
            f"Track it here:\n{detail_link}\n"
        )
        return subject, body, detail_link
    if notif_type == NotificationType.MORE_INFORMATION_REQUIRED.value:
        edit_link = f"{base}/problems/{ticket}/edit"
        subject = f"JanSamadhan {ticket}: additional information required"
        body = (
            f"Additional information is required for your JanSamadhan problem.\n\n"
            f"Ticket: {ticket}\n"
            f"Title: {title}\n"
            f"Status: More information required\n\n"
            f"What was requested:\n{(reason or '').strip() or 'Please provide more detail about the problem.'}\n\n"
            f"Respond here (your ticket stays the same):\n{edit_link}\n"
        )
        return subject, body, edit_link
    if notif_type == NotificationType.ASSIGNED_TO_PUBLIC.value:
        subject = f"JanSamadhan {ticket}: now open for public solutions"
        body = (
            f"Your JanSamadhan problem has been routed to the public solution process.\n\n"
            f"Ticket: {ticket}\n"
            f"Title: {title}\n"
            f"Status: Open for public solutions\n\n"
            f"View it here:\n{detail_link}\n"
        )
        return subject, body, detail_link
    if notif_type == NotificationType.GOVERNMENT_ISSUE.value:
        subject = f"JanSamadhan {ticket}: recorded as a government issue"
        body = (
            f"Your JanSamadhan problem has been recorded as a government issue.\n\n"
            f"Ticket: {ticket}\n"
            f"Title: {title}\n"
            f"Status: Government issue\n\n"
            f"Reason recorded:\n{(reason or '').strip() or 'Classified for government-side handling.'}\n\n"
            f"Track it here:\n{detail_link}\n"
        )
        return subject, body, detail_link
    if notif_type == NotificationType.AUTO_ESCALATED.value:
        subject = f"JanSamadhan {ticket}: review window escalated"
        body = (
            f"The government review window for your JanSamadhan problem was exceeded.\n\n"
            f"Ticket: {ticket}\n"
            f"Title: {title}\n"
            f"Status: Escalated in the review queue\n\n"
            f"The request has been escalated in the JanSamadhan review queue. "
            f"No department has accepted responsibility.\n\n"
            f"Track it here:\n{detail_link}\n"
        )
        return subject, body, detail_link
    raise ValueError(f"Unknown notification type: {notif_type}.")


def owner_email(db: Session, problem: Problem) -> str | None:
    """Recipient rule (G7): the authenticated problem owner's account email
    from the database. Never an arbitrary address from problem text."""
    owner = db.get(User, problem.owner_id)
    address = (owner.email if owner is not None else "") or ""
    return address.strip() or None


def queue_for_audit(
    db: Session, *, problem: Problem, audit: GovernmentAction
) -> Notification | None:
    """Create the PENDING intent for an audit event inside the caller's
    transaction (no commit here). Idempotent via unique audit_id: a second
    call for the same event returns the existing row. Returns None for
    audit-only events (INFORMATION_PROVIDED) or when the owner has no
    email address."""
    notif_type = NOTIFY_FOR_ACTION.get(audit.action)
    if notif_type is None:
        return None
    # The audit row may be newly added without an assigned id yet; flush so
    # the exactly-once anchor (unique audit_id) is populated pre-commit.
    db.flush()
    existing = (
        db.execute(
            select(Notification).where(Notification.audit_id == audit.id)
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing
    recipient = owner_email(db, problem)
    if recipient is None:
        logger.warning(
            "notification skipped ticket=%s action=%s: owner has no email",
            problem.ticket,
            audit.action,
        )
        return None
    subject, body, link = build_workflow_email(
        notif_type=notif_type,
        ticket=problem.ticket,
        title=problem.title,
        reason=audit.reason,
    )
    intent = Notification(
        problem_id=problem.id,
        audit_id=audit.id,
        ticket=problem.ticket,
        type=notif_type,
        recipient=recipient,
        subject=subject,
        body=body,
        link=link,
    )
    db.add(intent)
    return intent


def _default_sender(*, to: str, subject: str, body: str) -> None:
    from app.services.brevo_provider import send_workflow_email

    send_workflow_email(to, subject, body)


def deliver_intent(db: Session, intent_id, *, sender=None) -> Notification | None:
    """Attempt one PENDING intent; record SENT/FAILED with its own commit.
    Skips non-PENDING rows (already handled), so repeats and concurrent
    callers are safe. Delivery exceptions never propagate: they become a
    FAILED record with a safe, secret-free message."""
    sender = sender or _default_sender
    intent = (
        db.execute(
            select(Notification)
            .where(Notification.id == intent_id)
            .with_for_update()
        )
        .scalars()
        .first()
    )
    if intent is None or intent.status != NotificationStatus.PENDING.value:
        return intent
    intent.attempts += 1
    try:
        sender(to=intent.recipient, subject=intent.subject, body=intent.body)
    except Exception as exc:  # noqa: BLE001 - mapped to a safe record
        intent.status = NotificationStatus.FAILED.value
        name = type(exc).__name__
        intent.error_detail = f"Delivery failed ({name})."
        logger.warning(
            "notification failed ticket=%s type=%s attempt=%s: %s",
            intent.ticket,
            intent.type,
            intent.attempts,
            name,
        )
    else:
        intent.status = NotificationStatus.SENT.value
        intent.error_detail = None
        intent.sent_at = _utcnow()
        logger.info(
            "notification sent ticket=%s type=%s at=%s",
            intent.ticket,
            intent.type,
            intent.sent_at.isoformat(),
        )
    db.add(intent)
    db.commit()
    db.refresh(intent)
    return intent


def deliver_for_problem(
    db: Session, problem_id, *, sender=None
) -> list[Notification]:
    """Deliver every PENDING intent for a problem (post-commit flush used by
    transition paths). Returns the handled intents."""
    ids = [
        row_id
        for (row_id,) in db.execute(
            select(Notification.id).where(
                Notification.problem_id == problem_id,
                Notification.status == NotificationStatus.PENDING.value,
            )
        ).all()
    ]
    return [
        row
        for row in (deliver_intent(db, row_id, sender=sender) for row_id in ids)
        if row is not None
    ]


def retry_failed(db: Session, *, limit: int = 100, sender=None) -> dict:
    """Bounded re-attempt of PENDING orphans and FAILED intents below
    MAX_ATTEMPTS (scheduler-compatible; no infinite loops). Returns counts."""
    rows = (
        db.execute(
            select(Notification)
            .where(
                Notification.status.in_(
                    [
                        NotificationStatus.PENDING.value,
                        NotificationStatus.FAILED.value,
                    ]
                ),
                Notification.attempts < MAX_ATTEMPTS,
            )
            .order_by(Notification.created_at.asc())
            .limit(max(limit, 1))
        )
        .scalars()
        .all()
    )
    sent = failed = 0
    for row in rows:
        if row.status == NotificationStatus.FAILED.value:
            # Re-arm for exactly one more attempt; SENT rows are never
            # touched, so a success is still recorded at most once.
            row.status = NotificationStatus.PENDING.value
            db.add(row)
            db.commit()
        done = deliver_intent(db, row.id, sender=sender)
        if done is not None and done.status == NotificationStatus.SENT.value:
            sent += 1
        else:
            failed += 1
    return {"attempted": len(rows), "sent": sent, "failed": failed}
