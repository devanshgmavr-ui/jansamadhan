"""create users table

Revision ID: c9a1f2b4d6e7
Revises:
Create Date: 2026-09-29

Initial JanSamadhan migration: creates accounttype ENUM and users table.
Matches app.models.user.User. No plaintext password column (only password_hash).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9a1f2b4d6e7"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOTE: create_type=False on the column type + explicit checkfirst create.
    # The same ENUM object referenced in create_table would otherwise fire
    # the table-create event and issue a second CREATE TYPE in the same
    # transaction (alembic passes checkfirst=False there), causing
    # DuplicateObject. Explicit create handles fresh + pre-existing cases.
    accounttype_enum = postgresql.ENUM(
        "student",
        "university",
        "organization",
        "individual",
        name="accounttype",
        create_type=False,
    )
    accounttype_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("account_type", accounttype_enum, nullable=False),
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "is_phone_verified",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
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
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    postgresql.ENUM(name="accounttype").drop(op.get_bind(), checkfirst=True)
