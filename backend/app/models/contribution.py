import enum
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContributionType(str, enum.Enum):
    SOLUTION_PROPOSAL = "SOLUTION_PROPOSAL"
    RESEARCH = "RESEARCH"
    TECHNICAL = "TECHNICAL"
    PROTOTYPE_TESTING = "PROTOTYPE_TESTING"
    DEVELOPMENT = "DEVELOPMENT"
    COLLABORATION = "COLLABORATION"
    OTHER = "OTHER"


class ContributionStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"


class Contribution(Base):
    __tablename__ = "contributions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Author is always the authenticated user; never accepted from the client
    # as anyone else.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    problem_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    solution_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("solutions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ContributionStatus.PENDING.value
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
