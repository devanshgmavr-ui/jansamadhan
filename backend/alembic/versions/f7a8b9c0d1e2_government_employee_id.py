"""Government auth restructure: employee_id identity, drop email

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-07

Product decision: officials authenticate with a provisioned employee_id +
password. No email/SMS OTP, no email verification, no email password-reset
for government authentication, so the government_users.email column is
removed.

1. Add government_users.employee_id (backfilled for pre-existing rows with
   deterministic GOV-NNNN identifiers ordered by created_at, then NOT NULL).
2. Unique constraint + index on employee_id.
3. Drop ix_government_users_email, uq_government_users_email, email column.

Pre-existing rows keep their identity via the backfilled employee_id; no
row is deleted. Downgrade re-adds a nullable email column (original
addresses are not recoverable) and drops employee_id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "government_users",
        sa.Column("employee_id", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE government_users AS g SET employee_id = s.eid "
            "FROM (SELECT id, 'GOV-' || LPAD(ROW_NUMBER() OVER "
            "(ORDER BY created_at, id)::text, 4, '0') AS eid "
            "FROM government_users WHERE employee_id IS NULL) AS s "
            "WHERE g.id = s.id"
        )
    )
    op.alter_column("government_users", "employee_id", nullable=False)
    op.create_unique_constraint(
        "uq_government_users_employee_id", "government_users", ["employee_id"]
    )
    op.create_index(
        "ix_government_users_employee_id", "government_users", ["employee_id"]
    )
    op.drop_index("ix_government_users_email", table_name="government_users")
    op.drop_constraint(
        "uq_government_users_email", "government_users", type_="unique"
    )
    op.drop_column("government_users", "email")


def downgrade() -> None:
    op.add_column(
        "government_users",
        sa.Column("email", sa.String(length=255), nullable=True),
    )
    op.drop_index(
        "ix_government_users_employee_id", table_name="government_users"
    )
    op.drop_constraint(
        "uq_government_users_employee_id",
        "government_users",
        type_="unique",
    )
    op.alter_column("government_users", "employee_id", nullable=True)
    op.drop_column("government_users", "employee_id")
