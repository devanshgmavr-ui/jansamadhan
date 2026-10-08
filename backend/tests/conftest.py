"""G2 test isolation (read by pytest before any app import).

The ENTIRE suite runs against the scratch database ``jansamadhan_g2test``
on the same server. The shared development database is never touched: the
URL is asserted to be the scratch database before any application module
is imported, and every test truncates all app tables afterwards.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def _test_database_url() -> str:
    raw = None
    env_file = Path(__file__).resolve().parents[1] / ".env"
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("DATABASE_URL="):
            raw = line.split("=", 1)[1].strip()
            break
    assert raw, "DATABASE_URL not found in backend/.env"
    parts = urlsplit(raw)
    return urlunsplit((parts.scheme, parts.netloc, "/jansamadhan_g2test", "", ""))


TEST_DATABASE_URL = _test_database_url()
assert TEST_DATABASE_URL.endswith("/jansamadhan_g2test"), (
    "refusing to run tests: URL is not the isolated scratch database"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import itertools

import pytest
from sqlalchemy import text

_counter = itertools.count(1)


@pytest.fixture()
def db():
    """Session bound to the scratch DB; all app tables truncated after."""
    from app.db.base import Base
    from app.db.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        cleaner = SessionLocal()
        try:
            tables = [t for t in Base.metadata.tables if t != "alembic_version"]
            cleaner.execute(text("TRUNCATE " + ", ".join(tables) + " CASCADE"))
            cleaner.commit()
        finally:
            cleaner.close()


def make_user(db, account_type="individual"):
    from app.models.user import AccountType, User

    n = next(_counter)
    user = User(
        email=f"g2-{n}-{account_type}@example.test",
        account_type=AccountType(account_type),
        password_hash="not-a-real-hash",
        is_email_verified=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


APPROVABLE_PROBLEM = {
    "title": "Drinking water shortage in our ward",
    "category": "Water",
    "location": "Ward 12",
    "description": (
        "Borewells in our ward ran dry this summer and 200 families queue "
        "at water tankers every day for drinking water."
    ),
    "affected_group": "Families",
    "severity": "High",
    "desired_solution_type": "Install a new piped water supply line",
}

PERSONAL_PROBLEM = {
    "title": "My scooter broke down",
    "category": "Other",
    "location": "Home",
    "description": "My scooter broke down yesterday near my house.",
    "affected_group": "Me",
    "severity": "Low",
    "desired_solution_type": "Fix it",
}


def make_problem(db, owner, **overrides):
    from app.schemas.problem import ProblemCreate
    from app.services import problem_service

    fields = dict(APPROVABLE_PROBLEM)
    fields.update(overrides)
    return problem_service.create_problem(db, owner, ProblemCreate(**fields))


def make_official(db):
    from app.core.security import hash_password
    from app.models.government import GovernmentUser

    n = next(_counter)
    official = GovernmentUser(
        employee_id=f"GOV-TEST-{n:04d}",
        password_hash=hash_password("Stag1ng-Official"),
        full_name="Test Official",
        designation="Review Officer",
    )
    db.add(official)
    db.commit()
    db.refresh(official)
    return official
