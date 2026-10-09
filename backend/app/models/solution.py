import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SolutionStatus(str, enum.Enum):
    SUBMITTED = "SUBMITTED"
    INITIAL_REVIEW = "INITIAL_REVIEW"
    UNDER_EVALUATION = "UNDER_EVALUATION"
    SHORTLISTED = "SHORTLISTED"
    COLLABORATION_FORMED = "COLLABORATION_FORMED"
    DEVELOPMENT = "DEVELOPMENT"
    PROTOTYPE = "PROTOTYPE"
    PILOT = "PILOT"
    IMPLEMENTED = "IMPLEMENTED"
    IMPACT_RECORDED = "IMPACT_RECORDED"


class SolutionReviewStatus(str, enum.Enum):
    """Phase 3 government review of a submitted solution. Independent of
    the development lifecycle above: officials approve/reject/request
    changes and select at most one winning solution per problem."""

    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    SELECTED = "SELECTED"


# Linear lifecycle. Only forward, one step at a time. Stage 9 advances
# solutions through these same transitions as projects progress.
SOLUTION_TRANSITIONS = {
    SolutionStatus.SUBMITTED.value: [SolutionStatus.INITIAL_REVIEW.value],
    SolutionStatus.INITIAL_REVIEW.value: [SolutionStatus.UNDER_EVALUATION.value],
    SolutionStatus.UNDER_EVALUATION.value: [SolutionStatus.SHORTLISTED.value],
    SolutionStatus.SHORTLISTED.value: [SolutionStatus.COLLABORATION_FORMED.value],
    SolutionStatus.COLLABORATION_FORMED.value: [SolutionStatus.DEVELOPMENT.value],
    SolutionStatus.DEVELOPMENT.value: [SolutionStatus.PROTOTYPE.value],
    SolutionStatus.PROTOTYPE.value: [SolutionStatus.PILOT.value],
    SolutionStatus.PILOT.value: [SolutionStatus.IMPLEMENTED.value],
    SolutionStatus.IMPLEMENTED.value: [SolutionStatus.IMPACT_RECORDED.value],
    SolutionStatus.IMPACT_RECORDED.value: [],
}


class Solution(Base):
    __tablename__ = "solutions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Permanent, backend-generated, never modified after creation.
    ticket: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Backend-enforced: never equal to the parent problem's owner (Stage 7 rule).
    submitter_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[str | None] = mapped_column(String(500), nullable=True)
    expected_impact: Mapped[str] = mapped_column(Text, nullable=False)
    contributors: Mapped[str | None] = mapped_column(String(500), nullable=True)
    estimated_resources: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_stored_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    pdf_original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pdf_mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")
    pdf_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SolutionStatus.SUBMITTED.value
    )
    # Phase 3 extended proposal fields (all optional).
    implementation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_cost: Mapped[str | None] = mapped_column(String(120), nullable=True)
    estimated_timeline: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Phase 3 government review. Selection is exclusive per problem
    # (is_selected); rejected solutions are kept, never deleted.
    review_status: Mapped[str] = mapped_column(
        String(30), nullable=False,
        default=SolutionReviewStatus.SUBMITTED.value,
    )
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("government_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_selected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
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
