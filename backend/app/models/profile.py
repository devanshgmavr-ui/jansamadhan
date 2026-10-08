import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _user_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    user_id: Mapped[uuid.UUID] = _user_pk()
    college: Mapped[str] = mapped_column(String(255), nullable=False)
    course: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year: Mapped[str | None] = mapped_column(String(50), nullable=True)
    skills: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UniversityProfile(Base):
    __tablename__ = "university_profiles"

    user_id: Mapped[uuid.UUID] = _user_pk()
    university_name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OrganizationProfile(Base):
    __tablename__ = "organization_profiles"

    user_id: Mapped[uuid.UUID] = _user_pk()
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class IndividualProfile(Base):
    __tablename__ = "individual_profiles"

    user_id: Mapped[uuid.UUID] = _user_pk()
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interests: Mapped[str | None] = mapped_column(String(500), nullable=True)
    skills: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
