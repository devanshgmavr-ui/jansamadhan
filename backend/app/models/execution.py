"""Phase 3 execution tracking: solution attachments, government-issue
implementation updates and their attachments. References problems,
solutions, users, and officials by FK only; no complaint data duplicated."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SolutionAttachment(Base):
    """Supporting documents/images for a solution (Phase 3). Files live in
    object storage under solution-attachments/{solution_ticket}/; the row
    keeps provider-independent metadata only."""

    __tablename__ = "solution_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    solution_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("solutions.id", ondelete="CASCADE"),
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ImplementationStage(str, enum.Enum):
    """Closed vocabulary for government-issue progress updates (Phase 3)."""

    INVESTIGATION_STARTED = "INVESTIGATION_STARTED"
    SURVEY_COMPLETED = "SURVEY_COMPLETED"
    ADMINISTRATIVE_APPROVAL = "ADMINISTRATIVE_APPROVAL"
    BUDGET_APPROVED = "BUDGET_APPROVED"
    WORK_ORDER_ISSUED = "WORK_ORDER_ISSUED"
    IMPLEMENTATION_STARTED = "IMPLEMENTATION_STARTED"
    WORK_IN_PROGRESS = "WORK_IN_PROGRESS"
    TESTING = "TESTING"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"


class ImplementationUpdate(Base):
    """Official progress update on a government issue (Phase 3).
    Append-only; rows are never edited or deleted through the API."""

    __tablename__ = "implementation_updates"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("government_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ImplementationAttachment(Base):
    """Documents/images attached to an implementation update (Phase 3).
    Stored under implementation-attachments/{problem_ticket}/."""

    __tablename__ = "implementation_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    update_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("implementation_updates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stored_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
