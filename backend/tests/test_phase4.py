"""Phase 4 tests: execution notifications, analytics, exports, audit,
settings, user notification history, extended search. Scratch DB only."""

import pytest
from fastapi.testclient import TestClient

from app.core import gov_revocation, ratelimit, security
from app.main import app
from app.services import notification_service as n
from tests.conftest import (
    APPROVABLE_PROBLEM,
    make_official,
    make_user,
)
from tests.test_notifications import Recorder

client = TestClient(app, raise_server_exceptions=False)

PUB = "/api/v1"
GOV = "/api/v1/government"
PDF = b"%PDF-1.4 phase4 probe"


@pytest.fixture(autouse=True)
def _reset_state():
    ratelimit.reset_login_attempts()
    gov_revocation.clear()
    yield
    ratelimit.reset_login_attempts()
    gov_revocation.clear()


@pytest.fixture()
def sender(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(n, "_default_sender", rec)
    return rec


def authz(token):
    return {"Authorization": f"Bearer {token}"}


def public_token(db, user):
    return security.create_access_token(user.id)


def gov_token(db, official):
    return security.create_government_token(official.id)


def make_open(db):
    owner = make_user(db)
    official = make_official(db)
    utok = public_token(db, owner)
    ticket = client.post(f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
                         headers=authz(utok)).json()["ticket"]
    gtok = gov_token(db, official)
    assert client.post(f"{GOV}/requests/{ticket}/assign-public", json={},
                       headers=authz(gtok)).status_code == 200
    return owner, official, ticket


def test_solution_lifecycle_notifications(db, sender):
    owner, official, ticket = make_open(db)
    solver = make_user(db)
    stok = public_token(db, solver)
    r = client.post(
        f"{PUB}/problems/{ticket}/solutions",
        data={"title": "Solar purifier pilot unit",
              "short_description": "Community RO plant for the ward area.",
              "expected_impact": "Clean water for 300 families."},
        files={"file": ("plan.pdf", PDF, "application/pdf")},
        headers=authz(stok))
    assert r.status_code == 201, r.text
    assert any("solution received" in s["subject"].lower()
               for s in sender.sent), sender.sent
    gtok = gov_token(db, official)
    sol = r.json()["ticket"]
    assert client.post(f"{GOV}/solutions/{sol}/review",
                       json={"decision": "APPROVED"},
                       headers=authz(gtok)).status_code == 200
    assert any("solution approved" in s["subject"].lower()
               for s in sender.sent)
    assert client.post(f"{GOV}/solutions/{sol}/select",
                       headers=authz(gtok)).status_code == 200
    assert any("winner" in s["subject"].lower() for s in sender.sent)
    # Rejected solutions are kept and the solver is told.
    solver2 = make_user(db)
    s2 = client.post(
        f"{PUB}/problems/{ticket}/solutions",
        data={"title": "Second attempt solution here",
              "short_description": "Another community approach, described.",
              "expected_impact": "Some impact for the ward."},
        files={"file": ("plan.pdf", PDF, "application/pdf")},
        headers=authz(public_token(db, solver2))).json()["ticket"]
    assert client.post(f"{GOV}/solutions/{s2}/review",
                       json={"decision": "REJECTED", "reason": "Too vague."},
                       headers=authz(gtok)).status_code == 200
    assert any("not approved" in s["subject"].lower() for s in sender.sent)
    assert client.get(f"{PUB}/solutions/{s2}",
                      headers=authz(public_token(db, solver2))).status_code == 200


def test_implementation_notifications(db, sender):
    owner = make_user(db)
    official = make_official(db)
    utok = public_token(db, owner)
    ticket = client.post(f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
                         headers=authz(utok)).json()["ticket"]
    gtok = gov_token(db, official)
    assert client.post(f"{GOV}/requests/{ticket}/mark-government-issue",
                       json={"reason": "Internal handling."},
                       headers=authz(gtok)).status_code == 200
    assert client.post(f"{GOV}/requests/{ticket}/implementation",
                       data={"stage": "INVESTIGATION_STARTED",
                             "title": "Survey begun"},
                       headers=authz(gtok)).status_code == 201
    assert any("implementation started" in s["subject"].lower()
               for s in sender.sent)
    assert client.post(f"{GOV}/requests/{ticket}/implementation",
                       data={"stage": "COMPLETED", "title": "Works done"},
                       headers=authz(gtok)).status_code == 201
    assert any("implementation completed" in s["subject"].lower()
               for s in sender.sent)


def test_analytics_overview(db, sender):
    make_open(db)
    r = client.get(f"{GOV}/analytics/overview",
                   headers=authz(gov_token(db, make_official(db))))
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("total_complaints", "public_challenges", "government_issues",
                "solutions_submitted", "monthly_trend", "top_categories",
                "top_locations"):
        assert key in body, key
    assert body["total_complaints"] >= 1
    # Public tokens cannot read analytics.
    owner = make_user(db)
    assert client.get(f"{GOV}/analytics/overview",
                      headers=authz(public_token(db, owner))).status_code == 401


def test_export_csv_and_pdf(db, sender):
    make_open(db)
    gtok = gov_token(db, make_official(db))
    r = client.get(f"{GOV}/requests/export?report=complaints&format=csv",
                   headers=authz(gtok))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("ticket,")
    r = client.get(f"{GOV}/requests/export?report=solutions&format=pdf",
                   headers=authz(gtok))
    assert r.status_code == 200, r.text[:100]
    assert r.content.startswith(b"%PDF-1.4")
    r = client.get(f"{GOV}/requests/export?report=bogus",
                   headers=authz(gtok))
    assert r.status_code == 422


def test_audit_search_and_settings(db, sender):
    owner, official, ticket = make_open(db)
    gtok = gov_token(db, official)
    r = client.get(f"{GOV}/audit?action=ASSIGNED_TO_PUBLIC",
                   headers=authz(gtok))
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 1
    r = client.get(f"{GOV}/audit?ticket={ticket}", headers=authz(gtok))
    assert all(i["ticket"] == ticket for i in r.json()["items"])
    r = client.get(f"{GOV}/settings", headers=authz(gtok))
    assert r.status_code == 200
    keys = {i["key"] for i in r.json()["items"]}
    assert "AI_PROVIDER" in keys and "ATTACHMENT_MAX_MB" in keys
    r = client.put(f"{GOV}/settings/ATTACHMENT_MAX_MB", json={"value": "1"},
                   headers=authz(gtok))
    assert r.status_code == 200 and r.json()["customized"] is True
    r = client.put(f"{GOV}/settings/NOPE", json={"value": "1"},
                   headers=authz(gtok))
    assert r.status_code == 422


def test_user_notification_history_isolated(db, sender):
    owner = make_user(db)
    other = make_user(db)
    client.post(f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
                headers=authz(public_token(db, owner)))
    mine = client.get(f"{PUB}/users/me/notifications",
                      headers=authz(public_token(db, owner))).json()
    theirs = client.get(f"{PUB}/users/me/notifications",
                        headers=authz(public_token(db, other))).json()
    assert mine["total"] >= 1
    assert theirs["total"] == 0
    own_tickets = {p["ticket"] for p in client.get(
        f"{PUB}/users/me/problems",
        headers=authz(public_token(db, owner))).json()["items"]}
    assert {n["ticket"] for n in mine["items"]} <= own_tickets


def test_transparency_search_sort_and_dates(db, sender):
    make_open(db)
    r = client.get(f"{PUB}/problems/transparency?sort=oldest")
    assert r.status_code == 200, r.text
    r = client.get(f"{PUB}/problems/transparency?date_from=2020-01-01&sort=updated")
    assert r.status_code == 200, r.text
    assert r.json()["total"] >= 1
