import enum
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProblemStatus(str, enum.Enum):
    """Lifecycle states. Stage 4 only ever assigns UNDER_REVIEW;
    later stages drive the remaining transitions.

    G2 government routing: AI approval now lands on GOV_REVIEW_PENDING
    (never directly OPEN). APPROVED is retained as a legacy/compatibility
    value for any rows that referenced it; new code must not assign it.
    """

    UNDER_REVIEW = "UNDER_REVIEW"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    APPROVED = "APPROVED"  # legacy/compatibility only; see docstring
    REJECTED = "REJECTED"
    GOV_REVIEW_PENDING = "GOV_REVIEW_PENDING"
    MORE_INFORMATION_REQUIRED = "MORE_INFORMATION_REQUIRED"
    GOVERNMENT_ISSUE = "GOVERNMENT_ISSUE"
    AUTO_ESCALATED = "AUTO_ESCALATED"
    OPEN = "OPEN"
    COLLABORATION = "COLLABORATION"
    IN_DEVELOPMENT = "IN_DEVELOPMENT"
    PILOT = "PILOT"
    IMPLEMENTED = "IMPLEMENTED"
    CLOSED = "CLOSED"


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Permanent, backend-generated, never modified after creation.
    ticket: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    # Unambiguous ownership for later self-solution enforcement (Stage 7).
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_group: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    desired_solution_type: Mapped[str] = mapped_column(String(1000), nullable=False)
    skills: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supporting_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ProblemStatus.UNDER_REVIEW.value
    )
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ProblemVersion(Base):
    """Immutable per-revision snapshot. Stage 5 will link AI reviews here."""

    __tablename__ = "problem_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_group: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    desired_solution_type: Mapped[str] = mapped_column(String(1000), nullable=False)
    skills: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supporting_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revision_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProblemAttachment(Base):
    """Attachment metadata. Files live outside the DB (see storage service);
    internal paths are never exposed through the API."""

    __tablename__ = "problem_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stored_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
