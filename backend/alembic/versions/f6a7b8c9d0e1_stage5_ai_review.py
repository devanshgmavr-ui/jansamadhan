"""stage 5 ai review: reviews, similar refs, classifications, tags

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-30

Immutable AI review audit rows linked to exact problem versions, plus the
current classification and normalized tags applied on APPROVED decisions.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("missing_info", sa.Text(), nullable=True),
        sa.Column("understandable", sa.Boolean(), nullable=True),
        sa.Column("sufficient_info", sa.Boolean(), nullable=True),
        sa.Column("solvable", sa.Boolean(), nullable=True),
        sa.Column("duplicate_status", sa.String(length=20), nullable=True),
        sa.Column("problem_type", sa.String(length=60), nullable=True),
        sa.Column("affected_group", sa.String(length=120), nullable=True),
        sa.Column("geo_context", sa.String(length=30), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=True),
        sa.Column("scope", sa.String(length=30), nullable=True),
        sa.Column("tech_areas", sa.Text(), nullable=True),
        sa.Column("tags_suggested", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["problem_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("problem_id", "review_number"),
    )
    op.create_index("ix_ai_reviews_problem_id", "ai_reviews", ["problem_id"])
    op.create_table(
        "ai_review_similar",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["ai_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_review_similar_review_id", "ai_review_similar", ["review_id"]
    )
    op.create_table(
        "problem_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("area", sa.String(length=30), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("affected_group", sa.String(length=120), nullable=False),
        sa.Column("problem_type", sa.String(length=60), nullable=False),
        sa.Column("tech_areas", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["problem_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("problem_id"),
    )
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "problem_tags",
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("problem_id", "tag_id"),
    )
    op.create_index("ix_problem_tags_tag_id", "problem_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_problem_tags_tag_id", table_name="problem_tags")
    op.drop_table("problem_tags")
    op.drop_table("tags")
    op.drop_table("problem_classifications")
    op.drop_index("ix_ai_review_similar_review_id", table_name="ai_review_similar")
    op.drop_table("ai_review_similar")
    op.drop_index("ix_ai_reviews_problem_id", table_name="ai_reviews")
    op.drop_table("ai_reviews")
