"""add verifynow fields to otp challenges

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-10-01

Stores the MessageCentral VerifyNow verificationId for provider-generated
SMS codes. Existing rows default to 'local' (JanSamadhan-generated codes).
No data change: additive nullable/defaulted columns only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "otp_challenges",
        sa.Column("provider", sa.String(length=20), nullable=False, server_default="local"),
    )
    op.add_column(
        "otp_challenges",
        sa.Column("provider_verification_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("otp_challenges", "provider_verification_id")
    op.drop_column("otp_challenges", "provider")
