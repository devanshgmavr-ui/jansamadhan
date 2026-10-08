from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory (parent of app/)
BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"

# Placeholder that must never be used in production.
DEFAULT_JWT_SECRET = "CHANGE_ME_GENERATE_A_LONG_RANDOM_SECRET"


class Settings(BaseSettings):
    APP_NAME: str = "JanSamadhan API"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    DATABASE_URL: str = (
        "postgresql+psycopg://USERNAME:PASSWORD@localhost:5432/jansamadhan"
    )
    JWT_SECRET_KEY: str = DEFAULT_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    OTP_EXPIRY_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    # OTP delivery: "mock" (development no-op) or "brevo" (email OTP).
    # There is no SMS verification.
    OTP_PROVIDER: str = "mock"
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = ""
    BREVO_SENDER_NAME: str = "JanSamadhan"
    BREVO_SMS_SENDER: str = "JanSamadhan"
    # Local frontend origins for development. Override in production via env.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Public frontend base URL used to build links sent by email (e.g. the
    # password-reset link). No secrets here.
    FRONTEND_URL: str = "http://localhost:5173"
    # AI review provider. "mock" is deterministic local logic; "openrouter"
    # calls the OpenRouter API and requires AI_API_KEY.
    AI_PROVIDER: str = "mock"
    AI_API_KEY: str = ""
    AI_MODEL: str = "openai/gpt-4o-mini"
    # Attachment storage: "local" (backend/uploads/*) or "supabase"
    # (private Supabase Storage bucket, server-side only). Frontend never
    # talks to Supabase directly; downloads stream through the backend.
    STORAGE_PROVIDER: str = "local"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ATTACHMENTS_BUCKET: str = "attachments"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"

    def assert_production_ready(self) -> None:
        if not self.is_development and self.JWT_SECRET_KEY == DEFAULT_JWT_SECRET:
            raise RuntimeError(
                "JWT_SECRET_KEY must be set to a real secret in production."
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.assert_production_ready()
    return settings


settings = get_settings()
