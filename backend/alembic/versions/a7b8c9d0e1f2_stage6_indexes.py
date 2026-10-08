"""stage 6 discovery indexes

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-30

B-tree indexes serving the public discovery filters and ordering.
LIKE '%x%' substring search cannot use b-trees; those filters remain
sequential scans, acceptable at this scale and documented here.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_problems_status", "problems", ["status"])
    op.create_index("ix_problems_category", "problems", ["category"])
    op.create_index(
        "ix_problems_status_created", "problems", ["status", "created_at"]
    )
    op.create_index(
        "ix_classifications_area_scope",
        "problem_classifications",
        ["area", "scope"],
    )
    op.create_index("ix_tags_name", "tags", ["name"])


def downgrade() -> None:
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_index("ix_classifications_area_scope", table_name="problem_classifications")
    op.drop_index("ix_problems_status_created", table_name="problems")
    op.drop_index("ix_problems_category", table_name="problems")
    op.drop_index("ix_problems_status", table_name="problems")
