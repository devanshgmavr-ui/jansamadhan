"""government routing foundation tables

Revision ID: d5e6f7a8b9c0
Revises: f2a3b4c5d6e7
Create Date: 2026-10-06

G2: government officials, per-problem routing state, and append-only
routing audit. Fully additive: three new tables only. No existing table,
row, or status value is touched; no backfill of existing problems.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "government_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("designation", sa.String(length=200), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_government_users_email"),
    )
    op.create_index(
        "ix_government_users_email", "government_users", ["email"]
    )
    op.create_table(
        "government_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("pending_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("info_request", sa.Text(), nullable=True),
        sa.Column("user_response", sa.Text(), nullable=True),
        sa.Column(
            "escalation_flag",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["decided_by"], ["government_users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "problem_id", name="uq_government_reviews_problem_id"
        ),
    )
    op.create_index(
        "ix_government_reviews_status", "government_reviews", ["status"]
    )
    op.create_index(
        "ix_government_reviews_sla_due_at", "government_reviews", ["sla_due_at"]
    )
    op.create_index(
        "ix_government_reviews_decided_by", "government_reviews", ["decided_by"]
    )
    op.create_table(
        "government_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("previous_status", sa.String(length=30), nullable=True),
        sa.Column("new_status", sa.String(length=30), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["government_users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_government_actions_problem_id", "government_actions", ["problem_id"]
    )
    op.create_index(
        "ix_government_actions_ticket", "government_actions", ["ticket"]
    )
    op.create_index(
        "ix_government_actions_actor_id", "government_actions", ["actor_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_government_actions_actor_id", table_name="government_actions")
    op.drop_index("ix_government_actions_ticket", table_name="government_actions")
    op.drop_index(
        "ix_government_actions_problem_id", table_name="government_actions"
    )
    op.drop_table("government_actions")
    op.drop_index(
        "ix_government_reviews_decided_by", table_name="government_reviews"
    )
    op.drop_index(
        "ix_government_reviews_sla_due_at", table_name="government_reviews"
    )
    op.drop_index("ix_government_reviews_status", table_name="government_reviews")
    op.drop_table("government_reviews")
    op.drop_index("ix_government_users_email", table_name="government_users")
    op.drop_table("government_users")
