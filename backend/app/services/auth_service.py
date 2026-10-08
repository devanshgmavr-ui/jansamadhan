"""Registration, login, token session and password-reset logic."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.models.auth_tokens import PasswordResetToken, RefreshToken
from app.models.otp import OTPChannel
from app.models.profile import (
    IndividualProfile,
    OrganizationProfile,
    StudentProfile,
    UniversityProfile,
)
from app.models.user import AccountType, User
from app.schemas.auth import RegisterRequest
from app.services import otp_service

RESET_TOKEN_EXPIRY_MINUTES = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def find_user_by_identifier(db: Session, identifier: str) -> User | None:
    identifier = identifier.strip()
    stmt = select(User).where(
        or_(
            User.email == identifier.lower(),
            User.phone == identifier,
        )
    )
    return db.execute(stmt).scalars().first()


def _require_profile_block(data: RegisterRequest, name: str):
    block = getattr(data, name)
    if block is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Profile section '{name}' is required for this account type.",
        )
    return block


def register_user(
    db: Session, data: RegisterRequest
) -> tuple[User, str]:
    """Create an inactive user + profile and issue the email OTP.

    Phone numbers are required and stored but never verified: there is no
    SMS verification in JanSamadhan. Returns (user, email_code). The
    plaintext code is returned once so the router can expose it in
    development only; never log it.
    """
    email = normalize_email(str(data.email))
    phone = data.phone  # already normalized by schema validator
    security.validate_password_strength(data.password)

    if db.execute(select(User).where(User.email == email)).scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    if db.execute(select(User).where(User.phone == phone)).scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this phone number already exists.",
        )

    first_name = (data.first_name or "").strip() or None
    last_name = (data.last_name or "").strip() or None
    if data.account_type in (AccountType.STUDENT, AccountType.INDIVIDUAL):
        if not first_name or not last_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="First name and last name are required.",
            )

    user = User(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        password_hash=security.hash_password(data.password),
        account_type=data.account_type,
        is_email_verified=False,
        is_phone_verified=False,
        is_active=False,
    )
    db.add(user)
    db.flush()  # assign user.id for profile + OTP rows

    if data.account_type == AccountType.STUDENT:
        block = _require_profile_block(data, "student")
        db.add(
            StudentProfile(
                user_id=user.id,
                college=block.college.strip(),
                course=block.course,
                year=block.year,
                skills=block.skills,
            )
        )
    elif data.account_type == AccountType.UNIVERSITY:
        block = _require_profile_block(data, "university")
        db.add(
            UniversityProfile(
                user_id=user.id,
                university_name=block.university_name.strip(),
                institution_type=block.institution_type,
                location=block.location,
                website=block.website,
            )
        )
    elif data.account_type == AccountType.ORGANIZATION:
        block = _require_profile_block(data, "organization")
        db.add(
            OrganizationProfile(
                user_id=user.id,
                organization_name=block.organization_name.strip(),
                organization_type=block.organization_type,
                industry=block.industry,
                location=block.location,
                website=block.website,
            )
        )
    else:
        block = _require_profile_block(data, "individual")
        db.add(
            IndividualProfile(
                user_id=user.id,
                location=block.location,
                interests=block.interests,
                skills=block.skills,
            )
        )
    db.commit()
    db.refresh(user)

    email_code = otp_service.issue_otp(db, user, OTPChannel.EMAIL)
    return user, email_code


def activate_if_verified(db: Session, user: User) -> User:
    if user.is_email_verified and not user.is_active:
        user.is_active = True
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def authenticate(db: Session, identifier: str, password: str) -> User:
    user = find_user_by_identifier(db, identifier)
    if user is None or not user.password_hash or not security.verify_password(
        password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not activated. Please complete email and phone verification.",
        )
    return user


def create_session(db: Session, user: User) -> tuple[str, str]:
    access = security.create_access_token(user.id)
    refresh, jti = security.create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            token_hash=sha256(refresh.encode("utf-8")).hexdigest(),
            expires_at=_utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    return access, refresh


def rotate_refresh(db: Session, refresh_token: str) -> tuple[str, str]:
    payload = security.decode_token(refresh_token, expected_type="refresh")
    record = (
        db.execute(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
        .scalars()
        .first()
    )
    now = _utcnow()
    if (
        record is None
        or record.revoked_at is not None
        or _aware(record.expires_at) <= now
        or record.token_hash != sha256(refresh_token.encode("utf-8")).hexdigest()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or revoked.",
        )
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable."
        )
    access = security.create_access_token(user.id)
    new_refresh, new_jti = security.create_refresh_token(user.id)
    record.revoked_at = now
    record.replaced_by = new_jti
    db.add(record)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=new_jti,
            token_hash=sha256(new_refresh.encode("utf-8")).hexdigest(),
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        )
    )
    db.commit()
    return access, new_refresh


def revoke_refresh(db: Session, refresh_token: str) -> None:
    """Idempotent logout: revoke if usable, otherwise succeed silently."""
    try:
        payload = security.decode_token(refresh_token, expected_type="refresh")
    except HTTPException:
        return
    record = (
        db.execute(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
        .scalars()
        .first()
    )
    if record is not None and record.revoked_at is None:
        record.revoked_at = _utcnow()
        db.add(record)
        db.commit()


def revoke_access_token(db: Session, user: User, access_token: str) -> None:
    """Record the access token's jti on the denylist so it stops working
    immediately. Idempotent; also prunes already-expired entries."""
    from app.models.revoked_token import RevokedToken

    try:
        payload = security.decode_token(access_token, expected_type="access")
    except HTTPException:
        return
    if payload.get("sub") != str(user.id):
        return
    try:
        expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    except (KeyError, ValueError, OSError, OverflowError):
        return
    if db.get(RevokedToken, payload["jti"]) is None:
        db.add(
            RevokedToken(
                jti=payload["jti"], user_id=user.id, expires_at=expires_at
            )
        )
    db.query(RevokedToken).filter(
        RevokedToken.expires_at <= _utcnow()
    ).delete(synchronize_session=False)
    db.commit()


def revoke_all_refresh(db: Session, user: User) -> None:
    records = (
        db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    now = _utcnow()
    for record in records:
        record.revoked_at = now
        db.add(record)
    db.commit()


def request_password_reset(db: Session, identifier: str) -> str | None:
    """Create a reset token. Returns plaintext token once (dev exposure only).
    Returns None for unknown identifiers to avoid user enumeration."""
    user = find_user_by_identifier(db, identifier)
    if user is None or not user.is_active:
        return None
    token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=sha256(token.encode("utf-8")).hexdigest(),
            expires_at=_utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES),
        )
    )
    db.commit()
    return token


def reset_password(db: Session, token: str, new_password: str) -> None:
    record = (
        db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash
                == sha256(token.encode("utf-8")).hexdigest()
            )
        )
        .scalars()
        .first()
    )
    now = _utcnow()
    expires = _aware(record.expires_at) if record else None
    if record is None or record.used_at is not None or expires is None or expires <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or expired.",
        )
    security.validate_password_strength(new_password)
    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or expired.",
        )
    user.password_hash = security.hash_password(new_password)
    record.used_at = now
    db.add(user)
    db.add(record)
    db.commit()
    revoke_all_refresh(db, user)


def serialize_profile(db: Session, user: User) -> dict | None:
    if user.account_type == AccountType.STUDENT:
        row = db.get(StudentProfile, user.id)
        return (
            {
                "college": row.college,
                "course": row.course,
                "year": row.year,
                "skills": row.skills,
            }
            if row
            else None
        )
    if user.account_type == AccountType.UNIVERSITY:
        row = db.get(UniversityProfile, user.id)
        return (
            {
                "university_name": row.university_name,
                "institution_type": row.institution_type,
                "location": row.location,
                "website": row.website,
            }
            if row
            else None
        )
    if user.account_type == AccountType.ORGANIZATION:
        row = db.get(OrganizationProfile, user.id)
        return (
            {
                "organization_name": row.organization_name,
                "organization_type": row.organization_type,
                "industry": row.industry,
                "location": row.location,
                "website": row.website,
            }
            if row
            else None
        )
    row = db.get(IndividualProfile, user.id)
    return (
        {"location": row.location, "interests": row.interests, "skills": row.skills}
        if row
        else None
    )
