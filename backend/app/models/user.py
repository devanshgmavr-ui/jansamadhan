import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AccountType(str, enum.Enum):
    STUDENT = "student"
    UNIVERSITY = "university"
    ORGANIZATION = "organization"
    INDIVIDUAL = "individual"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    phone: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True
    )
    password_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    account_type: Mapped[AccountType] = mapped_column(
        # values_callable persists the lowercase values ("student", ...)
        # matching the PostgreSQL enum labels created by the migration.
        SQLEnum(
            AccountType,
            values_callable=lambda e: [m.value for m in e],
            name="accounttype",
            create_type=True,
        ),
        nullable=False,
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_phone_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
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
