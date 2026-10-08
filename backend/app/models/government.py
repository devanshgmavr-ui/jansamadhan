"""Government routing foundation (G2): officials, review state, audit trail.

GovernmentUser is completely separate from the public User model: it is not
another AccountType, public registration can never create one, and future
government authentication (G3) will validate against this table only.

GovernmentReview holds exactly one row per problem (unique problem_id) and
represents the CURRENT government-routing cycle. History is never stored by
mutating these rows: every transition appends a GovernmentAction row, which
is append-only by design (no service function updates or deletes it, and no
API may do so either).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GovernmentReviewStatus(str, enum.Enum):
    """Routing states. These are NOT ProblemStatus values; the service layer
    maps each one onto the mirrored Problem.status (ASSIGNED_TO_PUBLIC maps
    to OPEN so the entire existing public lifecycle is reused)."""

    PENDING = "PENDING"
    ASSIGNED_TO_PUBLIC = "ASSIGNED_TO_PUBLIC"
    GOVERNMENT_ISSUE = "GOVERNMENT_ISSUE"
    MORE_INFORMATION_REQUIRED = "MORE_INFORMATION_REQUIRED"
    AUTO_ESCALATED = "AUTO_ESCALATED"


class GovernmentActionType(str, enum.Enum):
    """Closed vocabulary for the audit trail. Centralized here so transition
    code never scatters raw action strings."""

    GOV_REVIEW_CREATED = "GOV_REVIEW_CREATED"
    ASSIGNED_TO_PUBLIC = "ASSIGNED_TO_PUBLIC"
    MARKED_GOVERNMENT_ISSUE = "MARKED_GOVERNMENT_ISSUE"
    REQUESTED_INFORMATION = "REQUESTED_INFORMATION"
    INFORMATION_PROVIDED = "INFORMATION_PROVIDED"
    REOPENED_FOR_GOVERNMENT_REVIEW = "REOPENED_FOR_GOVERNMENT_REVIEW"
    AUTO_ESCALATED = "AUTO_ESCALATED"


class ActorType(str, enum.Enum):
    """Who caused an audit event. Stored explicitly (G7) so system actions
    and public-user actions can never be mistaken for an official's doing.
    Pre-G7 rows keep NULL (unknown historical actor)."""

    GOVERNMENT_OFFICIAL = "GOVERNMENT_OFFICIAL"
    PUBLIC_USER = "PUBLIC_USER"
    SYSTEM = "SYSTEM"


class GovernmentUser(Base):
    """Authorized official. Provisioned through controlled administrative
    processes only; there is deliberately no public signup path, no email
    OTP, no SMS, and no email password-reset for this table.

    Identity is the provisioned employee_id (unique, an identifier rather
    than a secret); only the bcrypt password_hash is secret.
    """

    __tablename__ = "government_users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Provisioned employee/government ID. Normalized (strip) at write time
    # and matched exactly at login. Unique by database constraint.
    employee_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    # Bcrypt hash only (security.hash_password). Plaintext never stored.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    designation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class GovernmentReview(Base):
    """Current government-routing cycle for one problem. At most one row per
    problem (unique problem_id). Resubmission after more-information reuses
    this row with a fresh pending window; past cycles live on in
    GovernmentAction rows."""

    __tablename__ = "government_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=GovernmentReviewStatus.PENDING.value
    )
    # UTC-aware. sla_due_at is always pending_since + 24 hours for a fresh
    # pending cycle (service-enforced, never client-provided).
    pending_since: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sla_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Nullable so system events (auto-escalation) carry no actor; SET NULL
    # keeps the review row intact if an official record is ever removed.
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("government_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    info_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class GovernmentAction(Base):
    """Append-only audit record. No service function updates or deletes rows
    in this table; deactivating/removing an official SETs NULL the actor
    reference so history survives."""

    __tablename__ = "government_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Redundant by design: the ticket at action time, for audit readability.
    ticket: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("government_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Explicit actor kind (G7): SYSTEM for automatic events, PUBLIC_USER for
    # submitter-driven events, GOVERNMENT_OFFICIAL for routed decisions.
    actor_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class NotificationType(str, enum.Enum):
    """Workflow email kinds (G7). Only government-routing events notify;
    INFORMATION_PROVIDED is audit-only by product decision."""

    GOV_REVIEW_PENDING = "GOV_REVIEW_PENDING"
    MORE_INFORMATION_REQUIRED = "MORE_INFORMATION_REQUIRED"
    ASSIGNED_TO_PUBLIC = "ASSIGNED_TO_PUBLIC"
    GOVERNMENT_ISSUE = "GOVERNMENT_ISSUE"
    AUTO_ESCALATED = "AUTO_ESCALATED"


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class Notification(Base):
    """Durable workflow-email intent (G7). Created transactionally with the
    workflow transition it announces (one row per audit event via unique
    audit_id); delivery is attempted independently afterwards, so a mail
    failure can never roll back workflow state. No secrets stored."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Exactly-once anchor: the audit event this email announces.
    audit_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("government_actions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    ticket: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=NotificationStatus.PENDING.value,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
