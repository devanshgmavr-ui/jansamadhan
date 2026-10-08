"""stage 9 collaboration and project lifecycle

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-30

Team collaboration around problems/solutions, projects with milestones,
progress updates and impact preparation. All permissions enforced in code.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts2() -> list:
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
        "collaborations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("problem_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("solution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        *_ts2(),
        sa.ForeignKeyConstraint(["problem_id"], ["problems.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["solution_id"], ["solutions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collaborations_problem_id", "collaborations", ["problem_id"])
    op.create_table(
        "collaboration_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collaboration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        *_ts2(),
        sa.ForeignKeyConstraint(
            ["collaboration_id"], ["collaborations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collaboration_id", "user_id"),
    )
    op.create_index(
        "ix_collab_members_collab", "collaboration_members", ["collaboration_id"]
    )
    op.create_index("ix_collab_members_user", "collaboration_members", ["user_id"])
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collaboration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        *_ts2(),
        sa.ForeignKeyConstraint(
            ["collaboration_id"], ["collaborations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collaboration_id"),
    )
    op.create_table(
        "milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_ts2(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_milestones_project", "milestones", ["project_id"])
    op.create_table(
        "project_updates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_updates_project", "project_updates", ["project_id"])
    op.create_table(
        "impact_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("implementation_date", sa.Date(), nullable=True),
        sa.Column("affected_population", sa.String(length=200), nullable=True),
        sa.Column("outcomes", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_ts2(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )


def downgrade() -> None:
    op.drop_table("impact_records")
    op.drop_index("ix_updates_project", table_name="project_updates")
    op.drop_table("project_updates")
    op.drop_index("ix_milestones_project", table_name="milestones")
    op.drop_table("milestones")
    op.drop_table("projects")
    op.drop_index("ix_collab_members_user", table_name="collaboration_members")
    op.drop_index("ix_collab_members_collab", table_name="collaboration_members")
    op.drop_table("collaboration_members")
    op.drop_index("ix_collaborations_problem_id", table_name="collaborations")
    op.drop_table("collaborations")
