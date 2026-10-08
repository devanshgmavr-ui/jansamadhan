"""Government auth restructure tests: employee_id + password only.

No government self-registration, no email/SMS OTP, no email verification,
no password-reset email, no Brevo for government authentication. Scratch
DB only (conftest isolation).
"""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core import gov_revocation, ratelimit, security
from app.main import app
from app.models.government import GovernmentUser
from tests.conftest import make_official, make_problem, make_user

client = TestClient(app, raise_server_exceptions=False)

GOV = "/api/v1/government"
PASSWORD = "Stag1ng-Official"


@pytest.fixture(autouse=True)
def _reset_state():
    ratelimit.reset_login_attempts()
    gov_revocation.clear()
    yield
    ratelimit.reset_login_attempts()
    gov_revocation.clear()


def authz(token):
    return {"Authorization": f"Bearer {token}"}


def gov_login(employee_id, password=PASSWORD):
    return client.post(
        f"{GOV}/auth/login",
        json={"employee_id": employee_id, "password": password},
    )


# 1. valid employee_id + password ---------------------------------------------
def test_login_with_employee_id_returns_token(db):
    official = make_official(db)
    r = gov_login(official.employee_id)
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"access_token", "token_type"}


# 2/3. wrong id / wrong password -> generic 401 --------------------------------
def test_wrong_employee_id_generic_401(db):
    make_official(db)
    r = gov_login("GOV-DOES-NOT-EXIST", "Whatever-1")
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials."


def test_wrong_password_generic_401(db):
    official = make_official(db)
    r = gov_login(official.employee_id, "Wrong-Pass-1")
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials."


# 4. inactive ------------------------------------------------------------------
def test_inactive_employee_rejected(db):
    official = make_official(db)
    official.is_active = False
    db.add(official)
    db.commit()
    r = gov_login(official.employee_id)
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials."


# 5. token type / jti / expiry --------------------------------------------------
def test_government_token_claims(db):
    official = make_official(db)
    token = gov_login(official.employee_id).json()["access_token"]
    payload = security.decode_token(
        token, expected_type=security.GOVERNMENT_TOKEN_TYPE
    )
    assert payload["type"] == "government"
    assert payload.get("jti")
    assert payload.get("exp")


# 6/7/8. isolation --------------------------------------------------------------
def test_gov_token_serves_gov_but_not_public(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    gov = gov_login(official.employee_id).json()["access_token"]
    assert client.get(f"{GOV}/dashboard", headers=authz(gov)).status_code == 200
    assert client.get(f"{GOV}/requests", headers=authz(gov)).status_code == 200
    r = client.get("/api/v1/users/me/problems", headers=authz(gov))
    assert r.status_code == 401


def test_public_token_rejected_by_government(db):
    owner = make_user(db)
    make_official(db)
    pub = security.create_access_token(owner.id)
    assert client.get(f"{GOV}/dashboard", headers=authz(pub)).status_code == 401


# 9/10. logout revocation ---------------------------------------------------------
def test_logout_revokes_government_token(db):
    official = make_official(db)
    token = gov_login(official.employee_id).json()["access_token"]
    assert client.post(f"{GOV}/auth/logout", headers=authz(token)).status_code == 200
    assert client.get(f"{GOV}/auth/me", headers=authz(token)).status_code == 401


# 11. throttling -------------------------------------------------------------------
def test_login_throttling(db):
    for _ in range(5):
        assert gov_login("GOV-GHOST-1", "bad-pass-1").status_code == 401
    assert gov_login("GOV-GHOST-1", "bad-pass-1").status_code == 429


# 12/13/14/15. no registration / OTP / SMS / reset for government -------------------
@pytest.mark.parametrize("method,path", [
    ("POST", f"{GOV}/auth/register"),
    ("POST", f"{GOV}/register"),
    ("POST", f"{GOV}/auth/resend-otp"),
    ("POST", f"{GOV}/auth/verify-email"),
    ("POST", f"{GOV}/auth/verify-otp"),
    ("POST", f"{GOV}/auth/verify-sms"),
    ("POST", f"{GOV}/auth/send-sms"),
    ("POST", f"{GOV}/auth/forgot-password"),
    ("POST", f"{GOV}/auth/reset-password"),
    ("POST", f"{GOV}/auth/password-reset"),
])
def test_no_government_auth_side_doors(db, method, path):
    r = client.request(method, path, json={"employee_id": "x", "password": "y"})
    assert r.status_code in (404, 405), (method, path, r.status_code)


def test_government_openapi_has_no_otp_or_reset(db):
    from app.main import app as application

    text = str(application.openapi()["paths"])
    for route in application.openapi()["paths"]:
        if "/government" in route:
            lowered = route.lower()
            assert "otp" not in lowered, route
            assert "forgot" not in lowered, route
            assert "reset" not in lowered, route
            assert "verify" not in lowered, route
            assert "register" not in lowered, route
            assert "sms" not in lowered, route
    assert text  # keep linter honest about the dump


# 16. uniqueness ----------------------------------------------------------------------
def test_employee_id_unique(db):
    from app.core.security import hash_password

    db.add(GovernmentUser(employee_id="GOV-DUP-1",
                          password_hash=hash_password(PASSWORD)))
    db.commit()
    db.add(GovernmentUser(employee_id="GOV-DUP-1",
                          password_hash=hash_password(PASSWORD)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# 17/18. no credential leakage ----------------------------------------------------------
def test_password_and_hash_never_returned(db):
    official = make_official(db)
    token = gov_login(official.employee_id).json()["access_token"]
    bodies = [
        client.post(f"{GOV}/auth/login",
                    json={"employee_id": official.employee_id,
                          "password": PASSWORD}).text,
        client.get(f"{GOV}/auth/me", headers=authz(token)).text,
        client.get(f"{GOV}/dashboard", headers=authz(token)).text,
    ]
    for raw in bodies:
        assert PASSWORD not in raw
        assert "password_hash" not in raw
        assert official.password_hash not in raw


# 19. never logged --------------------------------------------------------------------------
def test_password_never_logged(db, caplog):
    official = make_official(db)
    with caplog.at_level(logging.DEBUG):
        gov_login(official.employee_id, "Wrong-Pass-1")
        gov_login(official.employee_id)
    assert PASSWORD not in caplog.text


# 20. workflow functional after login ----------------------------------------------------------
def test_workflow_functional_after_employee_login(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    token = gov_login(official.employee_id).json()["access_token"]
    queue = client.get(f"{GOV}/requests?status=PENDING&page=1&page_size=10",
                       headers=authz(token))
    assert queue.status_code == 200, queue.text
    assert problem.ticket in [i["ticket"] for i in queue.json()["items"]]
    detail = client.get(f"{GOV}/requests/{problem.ticket}", headers=authz(token))
    assert detail.status_code == 200, detail.text
