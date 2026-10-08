import enum
import uuid

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReviewDecision(str, enum.Enum):
    APPROVED = "APPROVED"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    NOT_SOCIETAL = "NOT_SOCIETAL"


class AIReview(Base):
    """Immutable audit record. One row per review run, linked to the exact
    problem version. Rows are never overwritten."""

    __tablename__ = "ai_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problem_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMPLETED")
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_info: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    understandable: Mapped[bool | None] = mapped_column(nullable=True)
    sufficient_info: Mapped[bool | None] = mapped_column(nullable=True)
    solvable: Mapped[bool | None] = mapped_column(nullable=True)
    duplicate_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    problem_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    affected_group: Mapped[str | None] = mapped_column(String(120), nullable=True)
    geo_context: Mapped[str | None] = mapped_column(String(30), nullable=True)
    category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    scope: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tech_areas: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    tags_suggested: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    error_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AIReviewSimilar(Base):
    __tablename__ = "ai_review_similar"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ai_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class ProblemClassification(Base):
    """Current classification of a problem, replaced on each APPROVED review."""

    __tablename__ = "problem_classifications"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problem_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    area: Mapped[str] = mapped_column(String(30), nullable=False)
    scope: Mapped[str] = mapped_column(String(30), nullable=False)
    affected_group: Mapped[str] = mapped_column(String(120), nullable=False)
    problem_type: Mapped[str] = mapped_column(String(60), nullable=False)
    tech_areas: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)


class ProblemTag(Base):
    __tablename__ = "problem_tags"

    problem_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("problems.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
