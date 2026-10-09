"""Phase 2 transparency dashboard tests: approved-only public listing,
filters, stats, and privacy. Scratch DB only."""

import pytest
from fastapi.testclient import TestClient

from app.core import gov_revocation, ratelimit, security
from app.main import app
from tests.conftest import (
    APPROVABLE_PROBLEM,
    PERSONAL_PROBLEM,
    make_official,
    make_user,
)

client = TestClient(app, raise_server_exceptions=False)

PUB = "/api/v1"


@pytest.fixture(autouse=True)
def _reset_state():
    ratelimit.reset_login_attempts()
    gov_revocation.clear()
    yield
    ratelimit.reset_login_attempts()
    gov_revocation.clear()


def authz(token):
    return {"Authorization": f"Bearer {token}"}


def public_token(db, user):
    return security.create_access_token(user.id)


def gov_token(db, official):
    return security.create_government_token(official.id)


def seed_decided(db):
    """One OPEN challenge + one government issue; returns tickets."""
    owner = make_user(db)
    official = make_official(db)
    utok = public_token(db, owner)
    gtok = gov_token(db, official)
    t1 = client.post(f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
                     headers=authz(utok)).json()["ticket"]
    t2 = client.post(f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
                     headers=authz(utok)).json()["ticket"]
    assert client.post(f"/api/v1/government/requests/{t1}/assign-public",
                       json={"reason": "Strong potential."},
                       headers=authz(gtok)).status_code == 200
    assert client.post(f"/api/v1/government/requests/{t2}/mark-government-issue",
                       json={"reason": "Departmental matter."},
                       headers=authz(gtok)).status_code == 200
    return t1, t2


def test_transparency_lists_both_resolutions(db):
    t1, t2 = seed_decided(db)
    r = client.get(f"{PUB}/problems/transparency")
    assert r.status_code == 200, r.text
    by_ticket = {i["ticket"]: i for i in r.json()["items"]}
    assert set((t1, t2)) <= set(by_ticket)
    assert by_ticket[t1]["resolution_type"] == "PUBLIC"
    assert by_ticket[t1]["decision_reason"] == "Strong potential."
    assert by_ticket[t1]["decided_at"] is not None
    assert by_ticket[t2]["resolution_type"] == "GOVERNMENT"
    assert by_ticket[t2]["decision_reason"] == "Departmental matter."
    assert by_ticket[t2]["decided_at"] is not None


def test_transparency_excludes_unapproved(db):
    owner = make_user(db)
    utok = public_token(db, owner)
    pending = client.post(f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
                          headers=authz(utok)).json()["ticket"]
    personal = client.post(f"{PUB}/problems", json=dict(PERSONAL_PROBLEM),
                           headers=authz(utok)).json()["ticket"]
    tickets = [i["ticket"] for i in
               client.get(f"{PUB}/problems/transparency").json()["items"]]
    assert pending not in tickets
    assert personal not in tickets


def test_transparency_filters(db):
    t1, t2 = seed_decided(db)
    r = client.get(f"{PUB}/problems/transparency?resolution=PUBLIC")
    assert {i["ticket"] for i in r.json()["items"]} == {t1}
    r = client.get(f"{PUB}/problems/transparency?resolution=GOVERNMENT")
    assert {i["ticket"] for i in r.json()["items"]} == {t2}
    r = client.get(f"{PUB}/problems/transparency?category=Water")
    assert {t1, t2} <= {i["ticket"] for i in r.json()["items"]}
    r = client.get(f"{PUB}/problems/transparency?severity=Low")
    assert r.json()["items"] == []
    r = client.get(f"{PUB}/problems/transparency?q=nonexistent-xyz")
    assert r.json()["items"] == []
    assert client.get(
        f"{PUB}/problems/transparency?resolution=BOGUS").status_code == 422
    assert client.get(
        f"{PUB}/problems/transparency?status=BOGUS").status_code == 422


def test_transparency_stats(db):
    t1, t2 = seed_decided(db)
    r = client.get(f"{PUB}/problems/transparency/stats")
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["total_approved"] == 2
    assert stats["challenges"] == 1
    assert stats["issues"] == 1
    assert stats["open_challenges"] == 1
    assert stats["resolved"] == 0


def test_transparency_exposes_no_private_fields(db):
    seed_decided(db)
    import json as _json

    raw = _json.dumps(
        client.get(f"{PUB}/problems/transparency").json()).lower()
    for forbidden in ("owner", "email", "info_request", "decided_by",
                      "password", "actor"):
        assert forbidden not in raw, forbidden


def test_government_issue_still_blocks_solutions(db):
    owner = make_user(db)
    solver = make_user(db)
    official = make_official(db)
    t = client.post(f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
                    headers=authz(public_token(db, owner))).json()["ticket"]
    gtok = gov_token(db, official)
    assert client.post(f"/api/v1/government/requests/{t}/mark-government-issue",
                       json={"reason": "Internal handling."},
                       headers=authz(gtok)).status_code == 200
    r = client.post(
        f"{PUB}/problems/{t}/solutions",
        data={"title": "Trying anyway solution",
              "short_description": "A solution attempt that must be refused.",
              "expected_impact": "None, must be refused."},
        files={"file": ("plan.pdf", b"%PDF-1.4 probe", "application/pdf")},
        headers=authz(public_token(db, solver)))
    assert r.status_code == 422, (r.status_code, r.text)
