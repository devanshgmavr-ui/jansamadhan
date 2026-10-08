from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.core.deps import bearer_scheme, get_current_user
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models.otp import OTPChannel
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    OTPResendRequest,
    OTPVerifyRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.services import auth_service, otp_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _dev(value: str | None) -> str | None:
    # Dev-only OTP echo is strictly a mock-provider facility. With a real
    # delivery provider the code must only exist in the user's inbox.
    if settings.is_development and otp_service.is_mock_mode():
        return value
    return None


def _user_out(db: Session, user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        phone=user.phone,
        account_type=user.account_type,
        first_name=user.first_name,
        last_name=user.last_name,
        is_email_verified=user.is_email_verified,
        is_phone_verified=user.is_phone_verified,
        is_active=user.is_active,
        created_at=user.created_at,
        profile=auth_service.serialize_profile(db, user),
    )


@router.post("/register", response_model=MessageResponse, status_code=201)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    user, email_code = auth_service.register_user(db, data)
    # Mock-mode development echo only; never returned with real delivery.
    if settings.is_development and otp_service.is_mock_mode():
        dev_otp = f"email:{email_code}"
    else:
        dev_otp = None
    return MessageResponse(
        message=(
            "Registration received. Verify your email with the "
            "OTP code to activate your account."
        ),
        dev_otp=dev_otp,
    )


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(data: OTPVerifyRequest, db: Session = Depends(get_db)):
    if data.channel != OTPChannel.EMAIL:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use channel 'email' for this endpoint.",
        )
    user = auth_service.find_user_by_identifier(db, data.identifier)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        )
    otp_service.verify_otp(db, user, OTPChannel.EMAIL, data.code)
    user.is_email_verified = True
    db.add(user)
    db.commit()
    auth_service.activate_if_verified(db, user)
    db.refresh(user)
    message = "Email verified successfully."
    if user.is_active:
        message += " Your account is now activated. You can sign in."
    return MessageResponse(message=message)


@router.post("/resend-otp", response_model=MessageResponse)
def resend_otp(data: OTPResendRequest, db: Session = Depends(get_db)):
    if data.channel == OTPChannel.PHONE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Phone verification is not required.",
        )
    user = auth_service.find_user_by_identifier(db, data.identifier)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found."
        )
    if user.is_email_verified:
        return MessageResponse(message="Email is already verified.")
    code = otp_service.issue_otp(db, user, OTPChannel.EMAIL)
    return MessageResponse(message="A new OTP has been sent.", dev_otp=_dev(code))


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    from app.core import ratelimit

    key = request.client.host if request.client else "unknown"
    if ratelimit.is_blocked(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )
    try:
        user = auth_service.authenticate(db, data.identifier, data.password)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            ratelimit.record_failure(key)
        raise
    ratelimit.record_success(key)
    access, refresh = auth_service.create_session(db, user)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    access, new_refresh = auth_service.rotate_refresh(db, data.refresh_token)
    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", response_model=MessageResponse)
def logout(
    data: LogoutRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    auth_service.revoke_access_token(db, user, credentials.credentials)
    auth_service.revoke_refresh(db, data.refresh_token)
    return MessageResponse(message="Signed out successfully.")


@router.get("/me", response_model=UserOut)
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _user_out(db, user)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Identical response whether or not the account exists (no enumeration).
    # On success the reset link is emailed; delivery failure never leaks
    # whether the account exists either.
    token = auth_service.request_password_reset(db, data.identifier)
    if token is not None:
        from app.services.brevo_provider import BrevoDeliveryError, send_password_reset_email

        user = auth_service.find_user_by_identifier(db, data.identifier)
        if user is not None and "@" in (user.email or ""):
            reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
            try:
                send_password_reset_email(user.email, reset_url)
            except BrevoDeliveryError:
                pass
    return ForgotPasswordResponse(
        message=(
            "If an active account exists for this email/phone, "
            "a password reset token has been issued."
        ),
        dev_reset_token=_dev(token),
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    auth_service.reset_password(db, data.token, data.new_password)
    return MessageResponse(
        message="Password has been reset. Please sign in with your new password."
    )
