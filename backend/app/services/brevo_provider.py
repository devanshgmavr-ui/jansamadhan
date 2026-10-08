"""Brevo delivery provider for OTP messages (backend-only).

Brevo delivers the message; generation, hashing, expiry, attempt limits and
verification stay in otp_service. The plaintext code exists here only for the
duration of the HTTPS call and is never logged or persisted.

No new third-party dependency: plain stdlib HTTPS against Brevo's v3 REST API.
"""

import json
import logging
import re
import urllib.error
import urllib.request

from app.core.config import settings
from app.models.otp import OTPChannel

logger = logging.getLogger(__name__)

EMAIL_API_URL = "https://api.brevo.com/v3/smtp/email"
SMS_API_URL = "https://api.brevo.com/v3/transactionalSMS/sms"
REQUEST_TIMEOUT = 20


class BrevoDeliveryError(Exception):
    """Safe, user-facing-safe failure. Never carries secrets or OTP content."""


def _api_key() -> str:
    key = settings.BREVO_API_KEY or ""
    if not key:
        raise BrevoDeliveryError("OTP delivery is not configured.")
    return key


def _post_json(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "api-key": _api_key()},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            if resp.status >= 400:
                raise BrevoDeliveryError("OTP delivery failed. Please try again.")
    except urllib.error.HTTPError as exc:
        # Log status only: bodies may contain account details.
        logger.warning("Brevo delivery failed: HTTP %s", exc.code)
        raise BrevoDeliveryError("OTP delivery failed. Please try again.") from None
    except BrevoDeliveryError:
        raise
    except Exception:
        logger.warning("Brevo delivery failed: network error")
        raise BrevoDeliveryError("OTP delivery failed. Please try again.") from None


def _send_email_otp(destination: str, code: str) -> None:
    sender_email = (settings.BREVO_SENDER_EMAIL or "").strip()
    if not sender_email:
        raise BrevoDeliveryError("OTP delivery is not configured.")
    _post_json(
        EMAIL_API_URL,
        {
            "sender": {"name": settings.BREVO_SENDER_NAME, "email": sender_email},
            "to": [{"email": destination}],
            "subject": "JanSamadhan Email Verification Code",
            "textContent": (
                "Your JanSamadhan verification code is:\n\n"
                f"{code}\n\n"
                "This code expires shortly.\n\n"
                "If you did not request this verification code, "
                "you can ignore this email."
            ),
        },
    )


def send_password_reset_email(destination: str, reset_url: str) -> None:
    """Password-recovery email. The URL carries the one-time reset token;
    it is built by the caller and never logged here."""
    sender_email = (settings.BREVO_SENDER_EMAIL or "").strip()
    if not sender_email:
        raise BrevoDeliveryError("Email delivery is not configured.")
    _post_json(
        EMAIL_API_URL,
        {
            "sender": {"name": settings.BREVO_SENDER_NAME, "email": sender_email},
            "to": [{"email": destination}],
            "subject": "JanSamadhan Password Reset",
            "textContent": (
                "You requested a password reset for your JanSamadhan account.\n\n"
                f"Reset your password here:\n{reset_url}\n\n"
                "This link expires shortly and can be used only once.\n\n"
                "If you did not request this, you can ignore this email."
            ),
        },
    )


def _normalize_msisdn(destination: str) -> str:
    digits = re.sub(r"\D", "", destination or "")
    if len(digits) < 7 or len(digits) > 15:
        raise BrevoDeliveryError("OTP delivery failed. Please try again.")
    return digits


def _send_sms_otp(destination: str, code: str) -> None:
    _post_json(
        SMS_API_URL,
        {
            "sender": settings.BREVO_SMS_SENDER,
            "recipient": _normalize_msisdn(destination),
            "content": f"JanSamadhan verification code: {code}. This code expires shortly.",
            "type": "transactional",
        },
    )


class BrevoOTPProvider:
    """Real delivery provider. Name must stay 'brevo' (used in audit logic)."""

    name = "brevo"

    def send(self, *, channel: OTPChannel, destination: str, code: str) -> None:
        if channel == OTPChannel.EMAIL:
            _send_email_otp(destination, code)
        else:
            _send_sms_otp(destination, code)


def send_workflow_email(destination: str, subject: str, text_content: str) -> None:
    """Transactional workflow notification (G7). Separate from OTP/reset
    mail: caller-built subject/body, same safe transport (key from settings,
    status-only failure logging, never logs content or secrets)."""
    sender_email = (settings.BREVO_SENDER_EMAIL or "").strip()
    if not sender_email:
        raise BrevoDeliveryError("Email delivery is not configured.")
    _post_json(
        EMAIL_API_URL,
        {
            "sender": {"name": settings.BREVO_SENDER_NAME, "email": sender_email},
            "to": [{"email": destination}],
            "subject": subject,
            "textContent": text_content,
        },
    )
