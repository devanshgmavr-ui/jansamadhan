"""stage 7 solutions with pdf documents and lifecycle status

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-30

One problem can carry many solutions. Ownership (submitter != problem owner)
is enforced in application code; the schema keeps the link unambiguous.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "solutions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket", sa.String(length=20), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=False),
        sa.Column("skills", sa.String(length=500), nullable=True),
        sa.Column("expected_impact", sa.Text(), nullable=False),
        sa.Column("contributors", sa.String(length=500), nullable=True),
        sa.Column("estimated_resources", sa.String(length=500), nullable=True),
        sa.Column("pdf_stored_name", sa.String(length=64), nullable=False),
        sa.Column("pdf_original_name", sa.String(length=255), nullable=False),
        sa.Column("pdf_mime_type", sa.String(length=100), nullable=False),
        sa.Column("pdf_size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
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
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitter_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pdf_stored_name"),
        sa.UniqueConstraint("ticket"),
    )
    op.create_index("ix_solutions_problem_id", "solutions", ["problem_id"])
    op.create_index("ix_solutions_submitter_id", "solutions", ["submitter_id"])
    op.create_index("ix_solutions_ticket", "solutions", ["ticket"], unique=True)
    op.create_index("ix_solutions_status", "solutions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_solutions_status", table_name="solutions")
    op.drop_index("ix_solutions_ticket", table_name="solutions")
    op.drop_index("ix_solutions_submitter_id", table_name="solutions")
    op.drop_index("ix_solutions_problem_id", table_name="solutions")
    op.drop_table("solutions")
