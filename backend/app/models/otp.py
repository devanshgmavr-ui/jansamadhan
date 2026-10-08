import enum
import uuid

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OTPChannel(str, enum.Enum):
    EMAIL = "email"
    PHONE = "phone"


class OTPChallenge(Base):
    """One OTP challenge per (user, channel). Only the SHA-256 hash is stored."""

    __tablename__ = "otp_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel: Mapped[OTPChannel] = mapped_column(
        SQLEnum(
            OTPChannel,
            values_callable=lambda e: [m.value for m in e],
            name="otpchannel",
            create_type=True,
        ),
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Origin marker retained from an earlier revision; only 'local' email OTP
    # challenges are created now. There is no SMS verification.
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="local")
    provider_verification_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    expires_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    consumed_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resend_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sent_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
