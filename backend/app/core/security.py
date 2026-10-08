"""Password hashing (bcrypt) and JWT handling. Never logs secrets."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

# bcrypt rejects passwords longer than 72 bytes; enforce at validation.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


def validate_password_strength(password: str) -> None:
    from fastapi import HTTPException, status

    def reject(reason: str) -> None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Password invalid: {reason}",
        )

    if len(password) < MIN_PASSWORD_LENGTH:
        reject(f"must be at least {MIN_PASSWORD_LENGTH} characters long")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        reject("must be at most 72 bytes long")
    if not any(c.isalpha() for c in password):
        reject("must include at least one letter")
    if not any(c.isdigit() for c in password):
        reject("must include at least one number")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: uuid.UUID) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "type": "access",
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str]:
    """Return (token, jti). Only the SHA-256 of the token is stored server-side."""
    from hashlib import sha256

    jti = secrets.token_hex(16)
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    token_hash = sha256(token.encode("utf-8")).hexdigest()
    return token, jti


def decode_token(token: str, expected_type: str) -> dict:
    from fastapi import HTTPException, status

    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token."
        )
    if payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type."
        )
    if not payload.get("sub") or not payload.get("jti"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token."
        )
    return payload


# Government tokens (G3). Same JWT machinery, distinct type claim so public
# and government credentials are mutually unintelligible: decode_token with
# expected_type="access" rejects "government" tokens and vice versa.
# Access-only by design: the portal holds a short-lived token per session and
# logout revokes its JTI (see app.core.gov_revocation). No refresh tokens.
GOVERNMENT_TOKEN_TYPE = "government"


def create_government_token(official_id: uuid.UUID) -> str:
    now = _utcnow()
    payload = {
        "sub": str(official_id),
        "type": GOVERNMENT_TOKEN_TYPE,
        "jti": secrets.token_hex(16),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
