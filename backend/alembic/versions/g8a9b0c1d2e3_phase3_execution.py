"""Phase 3 resolution execution: solution review fields, solution
attachments, implementation updates and attachments

Revision ID: g8a9b0c1d2e3
Revises: f7a8b9c0d1e2
Create Date: 2026-10-09

Additive only (fully reversible via downgrade):
1. solutions: implementation_plan, estimated_cost, estimated_timeline
   (nullable); review_status (default SUBMITTED), review_reason,
   reviewed_by (FK government_users SET NULL), reviewed_at, is_selected.
2. solution_attachments table.
3. implementation_updates + implementation_attachments tables.
No existing table, row, or status value is otherwise touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "g8a9b0c1d2e3"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("solutions", sa.Column("implementation_plan", sa.Text(), nullable=True))
    op.add_column("solutions", sa.Column("estimated_cost", sa.String(length=120), nullable=True))
    op.add_column("solutions", sa.Column("estimated_timeline", sa.String(length=120), nullable=True))
    op.add_column(
        "solutions",
        sa.Column("review_status", sa.String(length=30), nullable=False, server_default="SUBMITTED"),
    )
    op.add_column("solutions", sa.Column("review_reason", sa.Text(), nullable=True))
    op.add_column("solutions", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("solutions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "solutions",
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_foreign_key(
        "fk_solutions_reviewed_by", "solutions", "government_users",
        ["reviewed_by"], ["id"], ondelete="SET NULL",
    )
    op.create_table(
        "solution_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("solution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stored_name", sa.String(length=64), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["solution_id"], ["solutions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index("ix_solution_attachments_solution_id", "solution_attachments", ["solution_id"])
    op.create_table(
        "implementation_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["government_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_implementation_updates_problem_id", "implementation_updates", ["problem_id"])
    op.create_table(
        "implementation_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("update_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stored_name", sa.String(length=64), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["update_id"], ["implementation_updates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index(
        "ix_implementation_attachments_update_id", "implementation_attachments", ["update_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_implementation_attachments_update_id", table_name="implementation_attachments")
    op.drop_table("implementation_attachments")
    op.drop_index("ix_implementation_updates_problem_id", table_name="implementation_updates")
    op.drop_table("implementation_updates")
    op.drop_index("ix_solution_attachments_solution_id", table_name="solution_attachments")
    op.drop_table("solution_attachments")
    op.drop_constraint("fk_solutions_reviewed_by", "solutions", type_="foreignkey")
    op.drop_column("solutions", "is_selected")
    op.drop_column("solutions", "reviewed_at")
    op.drop_column("solutions", "reviewed_by")
    op.drop_column("solutions", "review_reason")
    op.drop_column("solutions", "review_status")
    op.drop_column("solutions", "estimated_timeline")
    op.drop_column("solutions", "estimated_cost")
    op.drop_column("solutions", "implementation_plan")
