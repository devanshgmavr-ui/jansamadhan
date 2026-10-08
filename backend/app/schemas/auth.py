import re
import uuid
from datetime import datetime

from pydantic import AfterValidator, BaseModel, EmailStr, Field
from typing import Annotated

from app.models.otp import OTPChannel
from app.models.user import AccountType

PHONE_RE = re.compile(r"^(?:\+?91|0)?([6-9][0-9]{9})$")


def _normalize_phone(v: str) -> str:
    """India-only mobile numbers. Accepts +91XXXXXXXXXX, 91XXXXXXXXXX,
    0XXXXXXXXXX or bare 10-digit input; always normalizes to +91XXXXXXXXXX.
    The 10-digit number must start with 6-9 (valid Indian mobile series)."""
    v = re.sub(r"[\s\-()]", "", v or "")
    m = PHONE_RE.match(v)
    if not m:
        raise ValueError(
            "phone must be a valid Indian mobile number: 10 digits starting "
            "with 6-9, with optional +91/91/0 prefix"
        )
    return f"+91{m.group(1)}"


PhoneStr = Annotated[str, AfterValidator(_normalize_phone)]


class StudentProfileIn(BaseModel):
    college: str = Field(min_length=1, max_length=255)
    course: str | None = Field(default=None, max_length=255)
    year: str | None = Field(default=None, max_length=50)
    skills: str | None = Field(default=None, max_length=500)


class UniversityProfileIn(BaseModel):
    university_name: str = Field(min_length=1, max_length=255)
    institution_type: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)


class OrganizationProfileIn(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)
    organization_type: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)


class IndividualProfileIn(BaseModel):
    location: str | None = Field(default=None, max_length=255)
    interests: str | None = Field(default=None, max_length=500)
    skills: str | None = Field(default=None, max_length=500)


class RegisterRequest(BaseModel):
    account_type: AccountType
    email: EmailStr
    phone: PhoneStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    student: StudentProfileIn | None = None
    university: UniversityProfileIn | None = None
    organization: OrganizationProfileIn | None = None
    individual: IndividualProfileIn | None = None


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class OTPVerifyRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    channel: OTPChannel
    # Email OTPs are exactly 6 digits. There is no SMS verification.
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class OTPResendRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    channel: OTPChannel


class ForgotPasswordRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)


class ForgotPasswordResponse(BaseModel):
    message: str
    # Development only: reset token so the mock flow can complete locally.
    # Always None outside development.
    dev_reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str
    # Development only: returned solely when ENVIRONMENT=development so the
    # mock OTP flow can be completed without a real SMS/email provider.
    # Always None in any other environment.
    dev_otp: str | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    phone: str | None
    account_type: AccountType
    first_name: str | None
    last_name: str | None
    is_email_verified: bool
    is_phone_verified: bool
    is_active: bool
    created_at: datetime
    profile: dict | None = None
