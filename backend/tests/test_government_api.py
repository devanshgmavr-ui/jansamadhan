"""G3 API tests: government auth, isolation, endpoints, actions, audit, SLA.

HTTP-level tests via TestClient against the isolated scratch database
(jansamadhan_g2test; conftest guard + per-test truncation apply).
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core import gov_revocation, ratelimit
from app.core import security
from app.main import app
from app.models.problem import ProblemStatus
from app.services import government_review_service as g
from tests.conftest import make_official, make_problem, make_user

client = TestClient(app, raise_server_exceptions=False)

GOV = "/api/v1/government"


@pytest.fixture(autouse=True)
def _reset_single_process_state():
    ratelimit.reset_login_attempts()
    gov_revocation.clear()
    yield
    ratelimit.reset_login_attempts()
    gov_revocation.clear()


def gov_login(employee_id, password="Stag1ng-Official"):
    return client.post(
        f"{GOV}/auth/login",
        json={"employee_id": employee_id, "password": password},
    )


def gov_token_for(db, official):
    return gov_login(official.employee_id).json()["access_token"]


def authz(token):
    return {"Authorization": f"Bearer {token}"}


def seed_states(db):
    """One pending problem per owner; returns dict of tickets."""
    owner = make_user(db)
    official = make_official(db)
    tickets = {}
    for label in ("pending", "public", "issue", "info"):
        p = make_problem(db, owner)
        tickets[label] = p.ticket
    db.flush()
    problems = {}
    from sqlalchemy import select
    from app.models.problem import Problem

    for label, ticket in tickets.items():
        problems[label] = (
            db.execute(select(Problem).where(Problem.ticket == ticket))
            .scalars()
            .one()
        )
    g.apply_decision(
        db, problems["public"], to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
    )
    g.apply_decision(
        db, problems["issue"], to_status="GOVERNMENT_ISSUE", actor_id=official.id,
        reason="Departmental matter.",
    )
    g.apply_decision(
        db, problems["info"], to_status="MORE_INFORMATION_REQUIRED",
        actor_id=official.id, info_request="Share the exact ward please.",
    )
    return owner, official, problems


# ---- authentication ----------------------------------------------------------
def test_gov_login_me_logout_roundtrip(db):
    official = make_official(db)
    r = gov_login(official.employee_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert set(body) == {"access_token", "token_type"}  # no refresh, no extras

    me = client.get(f"{GOV}/auth/me", headers=authz(body["access_token"]))
    assert me.status_code == 200, me.text
    assert me.json()["employee_id"] == official.employee_id
    assert "password_hash" not in me.json()

    out = client.post(f"{GOV}/auth/logout", headers=authz(body["access_token"]))
    assert out.status_code == 200
    again = client.get(f"{GOV}/auth/me", headers=authz(body["access_token"]))
    assert again.status_code == 401  # revoked server-side, not client-only


def test_gov_login_rejects_bad_credentials_generically(db):
    official = make_official(db)
    for employee_id, password in [
        (official.employee_id, "Wrong-Pass-1"),
        ("GOV-NOBODY-0000", "Whatever-1"),
    ]:
        r = gov_login(employee_id, password)
        assert r.status_code == 401
        assert r.json()["detail"] == "Invalid credentials."


def test_gov_login_rejects_inactive_official(db):
    official = make_official(db)
    official.is_active = False
    db.add(official)
    db.commit()
    r = gov_login(official.employee_id)
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid credentials."  # existence hidden


def test_gov_login_throttled(db):
    make_official(db)
    for _ in range(5):
        assert gov_login("ghost@example.test", "bad-pass-1").status_code == 401
    blocked = gov_login("ghost@example.test", "bad-pass-1")
    assert blocked.status_code == 429


def test_gov_expired_token_rejected(db):
    import jwt

    official = make_official(db)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(official.id),
            "type": "government",
            "jti": "test-expired-jti",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        "dummy",
        algorithm="HS256",
    )
    # Wrong-secret token must fail regardless of expiry handling path.
    assert client.get(f"{GOV}/auth/me", headers=authz(token)).status_code == 401

    from app.core.config import settings

    token = jwt.encode(
        {
            "sub": str(official.id),
            "type": "government",
            "jti": "test-expired-jti-2",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(seconds=1),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert client.get(f"{GOV}/auth/me", headers=authz(token)).status_code == 401


def test_gov_invalid_token_rejected(db):
    assert client.get(f"{GOV}/auth/me").status_code in (401, 403)
    bad = client.get(f"{GOV}/auth/me", headers=authz("not-a-token"))
    assert bad.status_code == 401


def test_gov_inactive_token_holder_rejected(db):
    official = make_official(db)
    token = security.create_government_token(official.id)
    official.is_active = False
    db.add(official)
    db.commit()
    assert client.get(f"{GOV}/auth/me", headers=authz(token)).status_code == 403


# ---- isolation (TEST 1..7) ----------------------------------------------------
def test_public_token_rejected_by_government_api(db):
    owner = make_user(db)
    public_token = security.create_access_token(owner.id)
    assert client.get(f"{GOV}/auth/me", headers=authz(public_token)).status_code == 401
    assert client.get(f"{GOV}/dashboard", headers=authz(public_token)).status_code == 401
    problem = make_problem(db, owner)
    r = client.post(
        f"{GOV}/requests/{problem.ticket}/assign-public",
        json={},
        headers=authz(public_token),
    )
    assert r.status_code == 401


def test_government_token_rejected_by_public_dependency(db):
    official = make_official(db)
    token = gov_token_for(db, official)
    r = client.get("/api/v1/auth/me", headers=authz(token))
    assert r.status_code == 401


def test_problem_owner_cannot_self_route(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    public_token = security.create_access_token(owner.id)
    for action, payload in [
        ("assign-public", {}),
        ("mark-government-issue", {"reason": "I want this."}),
        ("request-information", {"reason": "Tell me more."}),
    ]:
        r = client.post(
            f"{GOV}/requests/{problem.ticket}/{action}",
            json=payload,
            headers=authz(public_token),
        )
        assert r.status_code in (401, 403), (action, r.status_code)


# ---- dashboard -----------------------------------------------------------------
def test_dashboard_counts(db):
    owner, official, problems = seed_states(db)
    token = gov_token_for(db, official)
    assert client.get(f"{GOV}/dashboard").status_code == 401
    assert (
        client.get(
            f"{GOV}/dashboard", headers=authz(security.create_access_token(owner.id))
        ).status_code
        == 401
    )
    r = client.get(f"{GOV}/dashboard", headers=authz(token))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "pending": 1,
        "attention": 0,
        "government_issue": 1,
        "assigned_to_public": 1,
        "more_information_required": 1,
    }


# ---- queue ------------------------------------------------------------------------
def test_queue_filter_pagination_and_expired_flag(db):
    from datetime import timedelta

    owner, official, problems = seed_states(db)
    stale = g.get_for_problem(db, problems["pending"].id)
    stale.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    stale.sla_due_at = stale.pending_since + timedelta(hours=24)
    db.add(stale)
    db.commit()
    token = gov_token_for(db, official)

    r = client.get(f"{GOV}/requests", headers=authz(token))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 4 and body["pages"] == 1
    by_ticket = {i["ticket"]: i for i in body["items"]}
    assert by_ticket[problems["pending"].ticket]["expired"] is True
    assert by_ticket[problems["public"].ticket]["expired"] is False
    # Actionable first: expired pending leads.
    assert body["items"][0]["ticket"] == problems["pending"].ticket

    f = client.get(
        f"{GOV}/requests",
        params={"status": "GOVERNMENT_ISSUE"},
        headers=authz(token),
    )
    assert f.status_code == 200
    assert [i["ticket"] for i in f.json()["items"]] == [problems["issue"].ticket]

    bad = client.get(
        f"{GOV}/requests", params={"status": "OPEN"}, headers=authz(token)
    )
    assert bad.status_code == 422

    p1 = client.get(
        f"{GOV}/requests",
        params={"page": 1, "page_size": 2},
        headers=authz(token),
    )
    p2 = client.get(
        f"{GOV}/requests",
        params={"page": 2, "page_size": 2},
        headers=authz(token),
    )
    assert p1.status_code == p2.status_code == 200
    assert len(p1.json()["items"]) == len(p2.json()["items"]) == 2
    assert p1.json()["pages"] == 2


# ---- detail + history ---------------------------------------------------------------
def test_detail_and_history(db):
    owner, official, problems = seed_states(db)
    token = gov_token_for(db, official)
    ticket = problems["pending"].ticket

    d = client.get(f"{GOV}/requests/{ticket}", headers=authz(token))
    assert d.status_code == 200, d.text
    body = d.json()
    assert body["ticket"] == ticket
    assert body["government"]["review_status"] == "PENDING"
    assert body["ai_review"] is not None
    assert body["ai_review"]["decision"] == "APPROVED"
    assert len(body["versions"]) >= 1
    assert len(body["history"]) >= 1
    raw = d.text
    assert "password_hash" not in raw and "jti" not in raw

    h = client.get(f"{GOV}/requests/{ticket}/history", headers=authz(token))
    assert h.status_code == 200
    created = [e["created_at"] for e in h.json()]
    assert created == sorted(created)  # oldest -> newest

    assert client.get(f"{GOV}/requests/JS-PS-0000-000000", headers=authz(token)).status_code == 404


def test_detail_hidden_for_non_government_ticket(db):
    # Legacy-style OPEN problem with no GovernmentReview row: not a request.
    from app.models.government import GovernmentAction, GovernmentReview
    from app.models.problem import ProblemStatus as PS

    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
    )
    # Remove the review row directly to simulate a pre-routing legacy record.
    db.query(GovernmentAction).filter(
        GovernmentAction.problem_id == problem.id
    ).delete()
    db.query(GovernmentReview).filter(
        GovernmentReview.problem_id == problem.id
    ).delete()
    db.commit()

    token = gov_token_for(db, official)
    assert (
        client.get(f"{GOV}/requests/{problem.ticket}", headers=authz(token)).status_code
        == 404
    )
    assert PS.OPEN.value == "OPEN"  # public lifecycle untouched by the above


# ---- actions --------------------------------------------------------------------------
def test_assign_public_end_to_end(db):
    owner, official, problems = seed_states(db)
    token = gov_token_for(db, official)
    ticket = problems["pending"].ticket
    r = client.post(
        f"{GOV}/requests/{ticket}/assign-public", json={}, headers=authz(token)
    )
    assert r.status_code == 200, r.text
    assert r.json()["review_status"] == "ASSIGNED_TO_PUBLIC"
    assert r.json()["problem_status"] == "OPEN"

    h = client.get(f"{GOV}/requests/{ticket}/history", headers=authz(token)).json()
    last = h[-1]
    assert last["action"] == "ASSIGNED_TO_PUBLIC"
    assert last["previous_status"] == "PENDING"
    assert last["actor"]["kind"] == "official"
    assert last["actor"]["employee_id"] == official.employee_id

    # Now publicly discoverable through the unchanged public API.
    pub = client.get(f"/api/v1/problems/{ticket}/public")
    assert pub.status_code == 200


def test_mark_issue_and_request_info(db):
    owner, official, problems = seed_states(db)
    token = gov_token_for(db, official)

    no_reason = client.post(
        f"{GOV}/requests/{problems['pending'].ticket}/mark-government-issue",
        json={"reason": "   "},
        headers=authz(token),
    )
    assert no_reason.status_code == 422

    issue = client.post(
        f"{GOV}/requests/{problems['pending'].ticket}/mark-government-issue",
        json={"reason": "Needs departmental handling."},
        headers=authz(token),
    )
    assert issue.status_code == 200
    assert issue.json()["problem_status"] == "GOVERNMENT_ISSUE"
    pub = client.get(f"/api/v1/problems/{problems['pending'].ticket}/public")
    assert pub.status_code == 404  # never public


def test_illegal_action_transitions_rejected(db):
    owner, official, problems = seed_states(db)
    token = gov_token_for(db, official)
    # MORE_INFORMATION_REQUIRED -> assign-public is not a legal edge.
    r = client.post(
        f"{GOV}/requests/{problems['info'].ticket}/assign-public",
        json={},
        headers=authz(token),
    )
    assert r.status_code == 422
    # GOVERNMENT_ISSUE is terminal.
    r2 = client.post(
        f"{GOV}/requests/{problems['issue'].ticket}/request-information",
        json={"reason": "One more thing."},
        headers=authz(token),
    )
    assert r2.status_code == 422


def test_escalated_can_be_routed_and_sweep_route_order(db):
    owner, official, problems = seed_states(db)
    stale = g.get_for_problem(db, problems["pending"].id)
    stale.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    stale.sla_due_at = stale.pending_since + timedelta(hours=24)
    db.add(stale)
    db.commit()
    token = gov_token_for(db, official)

    # Static sweep route must match as a route (POST works)...
    s = client.post(f"{GOV}/requests/sweep-escalations", headers=authz(token))
    assert s.status_code == 200, s.text
    assert s.json()["escalated"] == 1
    assert s.json()["evaluated"] == 1
    assert s.json()["escalated_tickets"] == [problems["pending"].ticket]
    # ...and must NOT be captured as {ticket} (GET falls through to the
    # ticket lookup, which 404s without touching any state).
    get_sweep = client.get(
        f"{GOV}/requests/sweep-escalations", headers=authz(token)
    )
    assert get_sweep.status_code == 404
    # Repeat sweep: idempotent.
    s2 = client.post(f"{GOV}/requests/sweep-escalations", headers=authz(token))
    assert s2.json()["escalated"] == 0

    # Escalated -> assign-public works through the API.
    r = client.post(
        f"{GOV}/requests/{problems['pending'].ticket}/assign-public",
        json={},
        headers=authz(token),
    )
    assert r.status_code == 200
    assert r.json()["review_status"] == "ASSIGNED_TO_PUBLIC"


def test_system_actor_labelled_on_auto_escalation(db):
    owner, official, problems = seed_states(db)
    stale = g.get_for_problem(db, problems["pending"].id)
    stale.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    stale.sla_due_at = stale.pending_since + timedelta(hours=24)
    db.add(stale)
    db.commit()
    token = gov_token_for(db, official)
    client.post(f"{GOV}/requests/sweep-escalations", headers=authz(token))
    h = client.get(
        f"{GOV}/requests/{problems['pending'].ticket}/history", headers=authz(token)
    ).json()
    auto = [e for e in h if e["action"] == "AUTO_ESCALATED"]
    assert len(auto) == 1
    assert auto[0]["actor"]["kind"] == "system"
    # Must never claim a department accepted responsibility.
    assert "No department has accepted responsibility" in (auto[0]["reason"] or "")


# ---- docs ----------------------------------------------------------------------
def test_openapi_lists_government_contract():
    from app.main import app as live_app

    paths = live_app.openapi()["paths"]
    for p in [
        "/api/v1/government/auth/login",
        "/api/v1/government/auth/logout",
        "/api/v1/government/auth/me",
        "/api/v1/government/dashboard",
        "/api/v1/government/requests",
        "/api/v1/government/requests/sweep-escalations",
        "/api/v1/government/requests/{ticket}",
        "/api/v1/government/requests/{ticket}/history",
        "/api/v1/government/requests/{ticket}/assign-public",
        "/api/v1/government/requests/{ticket}/mark-government-issue",
        "/api/v1/government/requests/{ticket}/request-information",
    ]:
        assert p in paths, p
