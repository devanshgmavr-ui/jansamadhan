"""stage 4 problems: problems, versions, attachments

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-30

Problem submission with permanent backend-generated tickets
(JS-PS-YYYY-XXXXXX), immutable revision history and attachment metadata.
Status is a plain string column; Stage 5+ will drive lifecycle transitions.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "problems",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket", sa.String(length=20), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_group", sa.String(length=500), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("desired_solution_type", sa.String(length=1000), nullable=False),
        sa.Column("skills", sa.String(length=500), nullable=True),
        sa.Column("supporting_info", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket"),
    )
    op.create_index("ix_problems_owner_id", "problems", ["owner_id"])
    op.create_index("ix_problems_ticket", "problems", ["ticket"], unique=True)
    op.create_table(
        "problem_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_group", sa.String(length=500), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("desired_solution_type", sa.String(length=1000), nullable=False),
        sa.Column("skills", sa.String(length=500), nullable=True),
        sa.Column("supporting_info", sa.Text(), nullable=True),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_note", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("problem_id", "version_number"),
    )
    op.create_index(
        "ix_problem_versions_problem_id", "problem_versions", ["problem_id"]
    )
    op.create_table(
        "problem_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stored_name", sa.String(length=64), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index(
        "ix_problem_attachments_problem_id", "problem_attachments", ["problem_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_problem_attachments_problem_id", table_name="problem_attachments")
    op.drop_table("problem_attachments")
    op.drop_index("ix_problem_versions_problem_id", table_name="problem_versions")
    op.drop_table("problem_versions")
    op.drop_index("ix_problems_ticket", table_name="problems")
    op.drop_index("ix_problems_owner_id", table_name="problems")
    op.drop_table("problems")
