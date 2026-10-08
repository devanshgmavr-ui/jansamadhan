"""G7 audit actor type + workflow notification intents

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-06

Additive only:
1. government_actions.actor_type (nullable; pre-existing rows keep NULL =
   unknown historical actor, documented).
2. notifications table: durable per-audit-event email intents (unique
   audit_id guarantees exactly one intent per workflow transition).
No existing table, row, or status value is otherwise touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "government_actions",
        sa.Column("actor_type", sa.String(length=20), nullable=True),
    )
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket", sa.String(length=20), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, default=0),
        sa.Column("error_detail", sa.String(length=500), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["audit_id"], ["government_actions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_id", name="uq_notifications_audit_id"),
    )
    op.create_index(
        "ix_notifications_problem_id", "notifications", ["problem_id"]
    )
    op.create_index("ix_notifications_ticket", "notifications", ["ticket"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_status", "notifications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_ticket", table_name="notifications")
    op.drop_index("ix_notifications_problem_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_column("government_actions", "actor_type")
