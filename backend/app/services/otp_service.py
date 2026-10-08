"""OTP issuance/verification with a pluggable delivery provider.

MockOTPProvider is the development default; BrevoOTPProvider delivers real
email/SMS when OTP_PROVIDER=brevo. OTP codes are never logged and only the
SHA-256 hash is persisted. Delivery happens before commit so a send failure
rolls back without changing verification state.
"""

import secrets
import urllib.error
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.otp import OTPChallenge, OTPChannel
from app.models.user import User


class OTPProvider(Protocol):
    def send(self, *, channel: OTPChannel, destination: str, code: str) -> None: ...


class MockOTPProvider:
    """Development provider: accepts the OTP without external delivery."""

    name = "mock"

    def send(self, *, channel: OTPChannel, destination: str, code: str) -> None:
        return None


def resolve_provider() -> OTPProvider:
    """Select the configured delivery provider. Mock is the safe default;
    Brevo delivers email OTP. There is no SMS verification."""
    from app.services.brevo_provider import BrevoOTPProvider

    mode = settings.OTP_PROVIDER.lower()
    if mode == "brevo":
        return BrevoOTPProvider()
    return MockOTPProvider()


def is_mock_mode() -> bool:
    return settings.OTP_PROVIDER.lower() == "mock"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash_code(code: str) -> str:
    return sha256(code.encode("utf-8")).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(900000) + 100000:06d}"


def _latest_challenge(
    db: Session, user_id, channel: OTPChannel
) -> OTPChallenge | None:
    stmt = (
        select(OTPChallenge)
        .where(
            OTPChallenge.user_id == user_id,
            OTPChallenge.channel == channel,
        )
        .order_by(OTPChallenge.created_at.desc())
    )
    return db.execute(stmt).scalars().first()


def issue_otp(
    db: Session,
    user: User,
    channel: OTPChannel,
    provider: OTPProvider | None = None,
) -> str:
    """Create or refresh the OTP challenge. Returns the plaintext code once;
    callers must only expose it in development responses, never in logs.

    Delivery happens BEFORE the challenge is committed: on provider failure
    the transaction is rolled back so no flags change, nothing is half-stored,
    and the user can safely retry/resend."""
    from app.services.brevo_provider import BrevoDeliveryError

    provider = provider or resolve_provider()
    now = _utcnow()
    existing = _latest_challenge(db, user.id, channel)
    if existing is not None and existing.consumed_at is None:
        elapsed = (now - existing.last_sent_at).total_seconds()
        if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="OTP already sent. Please wait before requesting a new one.",
            )
        if existing.resend_count >= 5:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Maximum OTP resend attempts reached. Please try again later.",
            )
        code = _new_code()
        existing.code_hash = _hash_code(code)
        existing.expires_at = now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
        existing.attempts = 0
        existing.max_attempts = settings.OTP_MAX_ATTEMPTS
        existing.resend_count += 1
        existing.last_sent_at = now
        db.add(existing)
    else:
        code = _new_code()
        db.add(
            OTPChallenge(
                user_id=user.id,
                channel=channel,
                code_hash=_hash_code(code),
                expires_at=now + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
                attempts=0,
                max_attempts=settings.OTP_MAX_ATTEMPTS,
                resend_count=0,
                last_sent_at=now,
            )
        )
    destination = user.email if channel == OTPChannel.EMAIL else (user.phone or "")
    try:
        provider.send(channel=channel, destination=destination, code=code)
    except BrevoDeliveryError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not deliver the OTP. Please try again.",
        )
    except (urllib.error.URLError, TimeoutError, OSError):
        # Any other transport-level failure at the delivery boundary is
        # treated the same fail-safe way; details never reach the client.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not deliver the OTP. Please try again.",
        )
    db.commit()
    return code


def verify_otp(db: Session, user: User, channel: OTPChannel, code: str) -> OTPChallenge:
    challenge = _latest_challenge(db, user.id, channel)
    now = _utcnow()
    if challenge is None or challenge.consumed_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active OTP found. Please request a new one.",
        )
    if now > challenge.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired. Please request a new one.",
        )
    if challenge.attempts >= challenge.max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP verification attempts reached.",
        )
    if not secrets.compare_digest(challenge.code_hash, _hash_code(code)):
        challenge.attempts += 1
        db.add(challenge)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP code.",
        )
    challenge.consumed_at = now
    db.add(challenge)
    db.commit()
    return challenge
