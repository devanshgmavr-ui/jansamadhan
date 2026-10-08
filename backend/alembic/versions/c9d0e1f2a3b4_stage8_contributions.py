"""stage 8 contributions

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-30

User contributions linked to problems and optionally solutions. The author
is always the authenticated user; moderation belongs to the problem owner.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("solution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["solution_id"], ["solutions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contributions_user_id", "contributions", ["user_id"])
    op.create_index("ix_contributions_problem_id", "contributions", ["problem_id"])
    op.create_index("ix_contributions_solution_id", "contributions", ["solution_id"])
    op.create_index("ix_contributions_status", "contributions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_contributions_status", table_name="contributions")
    op.drop_index("ix_contributions_solution_id", table_name="contributions")
    op.drop_index("ix_contributions_problem_id", table_name="contributions")
    op.drop_index("ix_contributions_user_id", table_name="contributions")
    op.drop_table("contributions")
