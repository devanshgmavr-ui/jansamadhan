"""Administrator-configurable runtime settings (Phase 4, Part F).

Key/value rows edited through the government API only; the backend reads
them with environment-variable fallback so unset keys behave exactly as
before. No code edits needed to tune REVIEW/AI/storage/upload behavior."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# Registry of tunable keys: default + one-line purpose. Unknown keys are
# rejected by the API so typos cannot create dead configuration.
KNOWN_SETTINGS: dict[str, tuple[str, str]] = {
    "AI_PROVIDER": ("mock", "AI screening provider: mock | openrouter"),
    "AI_MODEL": ("openai/gpt-4o-mini", "Model for OpenRouter screening"),
    "AI_API_KEY": ("", "OpenRouter key (secret; prefer environment)"),
    "ATTACHMENT_ALLOWED_EXTENSIONS": (
        ".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv",
        "Comma-separated upload extensions",
    ),
    "ATTACHMENT_MAX_MB": ("10", "Max problem-attachment megabytes"),
    "SOLUTION_PDF_MAX_MB": ("15", "Max solution-PDF megabytes"),
    "AUTO_CLOSE_DAYS": ("", "Days after completion to auto-close (empty = off)"),
    "POLLING_INTERVAL_SECONDS": ("30", "Frontend refresh interval hint"),
    "NOTIFICATIONS_ENABLED": ("true", "Master switch for workflow email"),
}
