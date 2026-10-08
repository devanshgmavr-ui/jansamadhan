"""G8 security + authorization tests: token isolation, JWT edge cases,
ownership/IDOR, routing authz, state-machine abuse, files, mass
assignment, errors, rate limits. Scratch DB only (conftest isolation)."""

from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core import gov_revocation, ratelimit, security
from app.core.config import settings
from app.main import app
from app.models.government import GovernmentAction, Notification
from app.models.problem import ProblemStatus
from app.services import government_review_service as g
from tests.conftest import make_official, make_problem, make_user

client = TestClient(app, raise_server_exceptions=False)
GOV = "/api/v1/government"


@pytest.fixture(autouse=True)
def _reset_state():
    ratelimit.reset_login_attempts()
    gov_revocation.clear()
    yield
    ratelimit.reset_login_attempts()
    gov_revocation.clear()


def authz(token):
    return {"Authorization": f"Bearer {token}"}


def public_token_for(db, user):
    return security.create_access_token(user.id)


def gov_token_for(db, official):
    return security.create_government_token(official.id)


def gov_login(db, official, password="Stag1ng-Official"):
    return client.post(
        f"{GOV}/auth/login",
        json={"employee_id": official.employee_id, "password": password},
    )


def seed_routed(db):
    owner = make_user(db)
    official = make_official(db)
    pending = make_problem(db, owner)
    return owner, official, pending


# ---- §3 token isolation -------------------------------------------------------
def test_public_token_rejected_everywhere_government(db):
    owner, official, pending = seed_routed(db)
    pub = public_token_for(db, owner)
    for method, path, body in [
        ("GET", f"{GOV}/auth/me", None),
        ("GET", f"{GOV}/dashboard", None),
        ("GET", f"{GOV}/requests", None),
        ("GET", f"{GOV}/requests/{pending.ticket}", None),
        ("GET", f"{GOV}/requests/{pending.ticket}/history", None),
        ("POST", f"{GOV}/requests/{pending.ticket}/assign-public", {}),
        ("POST", f"{GOV}/requests/sweep-escalations", None),
    ]:
        r = client.request(method, path, json=body, headers=authz(pub))
        assert r.status_code == 401, (method, path, r.status_code)


def test_government_token_rejected_by_public_endpoints(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    gov = gov_token_for(db, official)
    for method, path, body in [
        ("GET", "/api/v1/auth/me", None),
        ("GET", "/api/v1/users/me/problems", None),
        ("GET", f"/api/v1/problems/{problem.ticket}", None),
        ("PUT", f"/api/v1/problems/{problem.ticket}", {"title": "Hijacked title here"}),
    ]:
        r = client.request(method, path, json=body, headers=authz(gov))
        assert r.status_code == 401, (method, path, r.status_code)


def test_type_enforced_despite_valid_signature(db):
    owner = make_user(db)
    official = make_official(db)
    # Valid-signature public token presented to government: still 401.
    assert (
        client.get(f"{GOV}/auth/me", headers=authz(public_token_for(db, owner))).status_code
        == 401
    )
    # Valid-signature government token never resolves to a public user.
    assert (
        client.get("/api/v1/auth/me", headers=authz(gov_token_for(db, official))).status_code
        == 401
    )


# ---- §5 government JWT edge cases ----------------------------------------------
def _gov_claims(official, **over):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(official.id),
        "type": "government",
        "jti": "edge-case-jti",
        "iat": now,
        "exp": now + timedelta(minutes=30),
    }
    claims.update(over)
    return claims


def _encode(claims, key=None):
    return pyjwt.encode(claims, key or settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.mark.parametrize("path", [f"{GOV}/auth/me", f"{GOV}/dashboard"])
def test_government_jwt_edge_cases(db, path):
    owner = make_user(db)
    official = make_official(db)
    now = datetime.now(timezone.utc)
    cases = {
        "random": "garbage.token.value",
        "wrong-secret": _encode(_gov_claims(official, jti="w1"), key="wrong-secret"),
        "missing-type": _encode({k: v for k, v in _gov_claims(official, jti="w2").items() if k != "type"}),
        "missing-sub": _encode({k: v for k, v in _gov_claims(official, jti="w3").items() if k != "sub"}),
        "missing-jti": _encode({k: v for k, v in _gov_claims(official).items() if k != "jti"}),
        "tampered": _encode(_gov_claims(official, jti="w4"))[:-2] + "xx",
        "expired": _encode({
            "sub": str(official.id), "type": "government", "jti": "w5",
            "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1),
        }),
        "public-type": public_token_for(db, owner),
    }
    for name, token in cases.items():
        r = client.get(path, headers=authz(token))
        assert r.status_code == 401, (name, path, r.status_code)
        assert "traceback" not in r.text.lower()


def test_missing_token_is_rejected_without_crash(db):
    assert client.get(f"{GOV}/auth/me").status_code in (401, 403)
    assert client.get("/api/v1/auth/me").status_code in (401, 403)


def test_government_logout_is_safe_and_repeatable(db):
    official = make_official(db)
    r = gov_login(db, official)
    token = r.json()["access_token"]
    assert client.get(f"{GOV}/auth/me", headers=authz(token)).status_code == 200
    assert client.post(f"{GOV}/auth/logout", headers=authz(token)).status_code == 200
    assert client.get(f"{GOV}/auth/me", headers=authz(token)).status_code == 401
    # Second logout with the dead token: rejected safely, never 500.
    assert client.post(f"{GOV}/auth/logout", headers=authz(token)).status_code == 401


# ---- §6 public JWT edge cases -----------------------------------------------------
def test_public_jwt_edge_cases(db):
    owner = make_user(db)
    now = datetime.now(timezone.utc)
    good = public_token_for(db, owner)
    assert client.get("/api/v1/auth/me", headers=authz(good)).status_code == 200
    bad_claims = {"sub": str(owner.id), "jti": "p1", "iat": now,
                  "exp": now + timedelta(minutes=30)}
    cases = [
        "garbage",
        _encode({**bad_claims, "type": "government"}),
        _encode({k: v for k, v in {**bad_claims, "type": "access"}.items() if k != "jti"}),
        _encode({k: v for k, v in {**bad_claims, "type": "access"}.items() if k != "sub"}),
        _encode({"sub": str(owner.id), "type": "access", "jti": "p2",
                 "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)}),
        _encode({**bad_claims, "type": "access"}, key="wrong-secret"),
    ]
    for token in cases:
        r = client.get("/api/v1/auth/me", headers=authz(token))
        assert r.status_code == 401, token[:30]
        assert "traceback" not in r.text.lower()


def test_logged_out_public_token_rejected(db):
    from app.core.security import hash_password
    from app.models.user import User

    email = "g8login@example.com"
    row = User(email=email, account_type="individual", password_hash=hash_password("LoginPass123"),
               is_email_verified=True, is_active=True)
    db.add(row)
    db.commit()
    r = client.post("/api/v1/auth/login", json={"identifier": email, "password": "LoginPass123"})
    assert r.status_code == 200, r.text
    access, refresh = r.json()["access_token"], r.json()["refresh_token"]
    assert client.get("/api/v1/auth/me", headers=authz(access)).status_code == 200
    assert client.post("/api/v1/auth/logout", json={"refresh_token": refresh},
                       headers=authz(access)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=authz(access)).status_code == 401


# ---- §7 refresh rotation ------------------------------------------------------------
def test_refresh_rotation_and_reuse_detection(db):
    from app.core.security import hash_password
    from app.models.user import User

    email = "g8refresh@example.com"
    db.add(User(email=email, account_type="individual", password_hash=hash_password("RefreshPass123"),
                is_email_verified=True, is_active=True))
    db.commit()
    tokens = client.post("/api/v1/auth/login",
                         json={"identifier": email, "password": "RefreshPass123"}).json()
    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200, r1.text
    # Old refresh is dead even though the new one from the same chain works.
    assert client.post("/api/v1/auth/refresh",
                       json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]})
    assert r2.status_code == 200
    # Logout kills the latest refresh too.
    latest = r2.json()
    client.post("/api/v1/auth/logout", json={"refresh_token": latest["refresh_token"]},
                headers=authz(latest["access_token"]))
    assert client.post("/api/v1/auth/refresh",
                       json={"refresh_token": latest["refresh_token"]}).status_code == 401
    # Expired refresh cannot mint access.
    now = datetime.now(timezone.utc)
    expired = _encode({"sub": "00000000-0000-0000-0000-000000000000", "type": "refresh",
                       "jti": "dead", "iat": now - timedelta(days=8),
                       "exp": now - timedelta(days=1)})
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": expired}).status_code == 401


# ---- §8/§21 problem ownership + IDOR ----------------------------------------------------
def test_cross_user_problem_access_denied(db):
    owner = make_user(db)
    stranger = make_user(db)
    problem = make_problem(db, owner)
    t = problem.ticket
    stranger_h = authz(public_token_for(db, stranger))
    assert client.get(f"/api/v1/problems/{t}", headers=stranger_h).status_code == 404
    assert client.put(f"/api/v1/problems/{t}", json={"title": "Hijacked title here"},
                      headers=stranger_h).status_code == 404
    assert client.get(f"/api/v1/problems/{t}/history", headers=stranger_h).status_code == 404
    assert client.get(f"/api/v1/problems/{t}/track", headers=stranger_h).status_code == 404
    assert client.get(f"/api/v1/problems/{t}/reviews", headers=stranger_h).status_code == 404
    # Owner unaffected.
    assert client.get(f"/api/v1/problems/{t}",
                      headers=authz(public_token_for(db, owner))).status_code == 200


# ---- §9 self-solution (backend-enforced) -----------------------------------------------
def test_self_solution_rule_end_to_end(db):
    import io

    owner = make_user(db)
    solver = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id)

    def attempt(token):
        return client.post(
            f"/api/v1/problems/{problem.ticket}/solutions",
            files={"file": ("plan.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
            data={"title": "A solver plan", "short_description": "Detailed enough plan here.",
                  "expected_impact": "Good impact here."},
            headers=authz(token),
        )

    assert attempt(public_token_for(db, owner)).status_code == 403
    good = attempt(public_token_for(db, solver))
    assert good.status_code == 201, good.text
    assert good.json()["ticket"].startswith("JS-SOL-")


# ---- §10 solution ownership ---------------------------------------------------------------
def test_solution_edit_restricted_to_submitter(db):
    import io

    owner = make_user(db)
    solver = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id)
    r = client.post(
        f"/api/v1/problems/{problem.ticket}/solutions",
        files={"file": ("plan.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        data={"title": "Solver plan one", "short_description": "Detailed enough plan here.",
              "expected_impact": "Good impact here."},
        headers=authz(public_token_for(db, solver)),
    )
    ticket = r.json()["ticket"]
    assert client.put(f"/api/v1/solutions/{ticket}", json={"title": "Owner rewrite attempt"},
                      headers=authz(public_token_for(db, owner))).status_code == 404
    assert client.put(f"/api/v1/solutions/{ticket}", json={"title": "Stranger rewrite"},
                      headers=authz(public_token_for(db, make_user(db)))).status_code == 404
    ok = client.put(f"/api/v1/solutions/{ticket}", json={"title": "Solver revision two"},
                    headers=authz(public_token_for(db, solver)))
    assert ok.status_code == 200 and ok.json()["title"] == "Solver revision two"


# ---- §11 contribution authz ------------------------------------------------------------------
def test_contribution_cross_user_denied(db):
    owner = make_user(db)
    other = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id)
    body = {"problem_ticket": problem.ticket, "type": "RESEARCH",
            "description": "A serious research contribution here."}
    r = client.post("/api/v1/contributions", json=body,
                    headers=authz(public_token_for(db, other)))
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert client.put(f"/api/v1/contributions/{cid}",
                        json={"description": "Owner edit by author ok here indeed."},
                        headers=authz(public_token_for(db, other))).status_code == 200
    assert client.put(
        f"/api/v1/contributions/{cid}",
        json={"description": "Malicious edit by non-author here."},
        headers=authz(public_token_for(db, owner))).status_code in (401, 403, 404)
    assert client.delete(f"/api/v1/contributions/{cid}",
                         headers=authz(public_token_for(db, owner))).status_code in (401, 403, 404)


# ---- §12 collaboration authz ---------------------------------------------------------------------
def test_collaboration_nonmember_denied(db):
    import io

    owner = make_user(db)
    solver = make_user(db)
    outsider = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id)
    r = client.post(
        f"/api/v1/problems/{problem.ticket}/solutions",
        files={"file": ("plan.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf")},
        data={"title": "Solver plan one", "short_description": "Detailed enough plan here.",
              "expected_impact": "Good impact here."},
        headers=authz(public_token_for(db, solver)),
    )
    sol_ticket = r.json()["ticket"]
    c = client.post("/api/v1/collaborations",
                    json={"problem_ticket": problem.ticket, "solution_ticket": sol_ticket,
                          "title": "Build team", "description": "A team to build the solution here."},
                    headers=authz(public_token_for(db, owner)))
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    out_h = authz(public_token_for(db, outsider))
    assert client.get(f"/api/v1/collaborations/{cid}", headers=out_h).status_code == 404
    assert client.post(f"/api/v1/collaborations/{cid}/projects",
                       json={"title": "Rogue project", "description": "Hijack attempt project here."},
                       headers=out_h).status_code in (401, 403, 404)
    proj = client.post(f"/api/v1/collaborations/{cid}/projects",
                       json={"title": "Real project", "description": "Owner creates the project here."},
                       headers=authz(public_token_for(db, owner)))
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]
    # Denied (422 here: milestone ownership preconditions fail for
    # non-members — denial, not access, is the invariant under test).
    assert client.post(f"/api/v1/projects/{pid}/milestones",
                       json={"title": "Rogue milestone", "description": "Hijack milestone here."},
                       headers=out_h).status_code in (401, 403, 404, 422)


# ---- §13 government routing authz ------------------------------------------------------------------
def test_government_routing_denied_to_public(db):
    owner, official, pending = seed_routed(db)
    pub = authz(public_token_for(db, owner))
    assert client.get(f"{GOV}/dashboard", headers=pub).status_code == 401
    assert client.get(f"{GOV}/requests", headers=pub).status_code == 401
    assert client.get(f"{GOV}/requests/{pending.ticket}", headers=pub).status_code == 401
    assert client.get(f"{GOV}/requests/{pending.ticket}/history", headers=pub).status_code == 401
    assert client.post(f"{GOV}/requests/{pending.ticket}/assign-public", json={},
                       headers=pub).status_code == 401
    assert client.post(f"{GOV}/requests/{pending.ticket}/mark-government-issue",
                       json={"reason": "I decide."}, headers=pub).status_code == 401
    assert client.post(f"{GOV}/requests/{pending.ticket}/request-information",
                       json={"reason": "Tell me."}, headers=pub).status_code == 401
    assert client.post(f"{GOV}/requests/sweep-escalations", headers=pub).status_code == 401
    # No state changed, no audit, no notification.
    assert pending.status == ProblemStatus.GOV_REVIEW_PENDING.value
    assert g.get_for_problem(db, pending.id).status == "PENDING"
    assert db.execute(select(func.count()).select_from(GovernmentAction)).scalar_one() == 1
    assert db.execute(select(func.count()).select_from(Notification)).scalar_one() == 1


# ---- §14 state-machine abuse --------------------------------------------------------------------------
def test_illegal_routing_rejected_without_side_effects(db):
    owner, official, pending = seed_routed(db)
    token = gov_token_for(db, official)
    h = authz(token)
    # MORE_INFORMATION_REQUIRED -> assign-public is illegal.
    g.apply_decision(db, pending, to_status="MORE_INFORMATION_REQUIRED",
                     actor_id=official.id, info_request="Share the ward.")
    audits_before = db.execute(select(func.count()).select_from(GovernmentAction)).scalar_one()
    intents_before = db.execute(select(func.count()).select_from(Notification)).scalar_one()
    r = client.post(f"{GOV}/requests/{pending.ticket}/assign-public", json={}, headers=h)
    assert r.status_code == 422, r.status_code
    assert pending.status == ProblemStatus.MORE_INFORMATION_REQUIRED.value
    assert g.get_for_problem(db, pending.id).status == "MORE_INFORMATION_REQUIRED"
    assert db.execute(select(func.count()).select_from(GovernmentAction)).scalar_one() == audits_before
    assert db.execute(select(func.count()).select_from(Notification)).scalar_one() == intents_before
    # Terminal GOVERNMENT_ISSUE cannot be re-routed.
    p2 = make_problem(db, owner)
    g.apply_decision(db, p2, to_status="GOVERNMENT_ISSUE", actor_id=official.id,
                     reason="Departmental matter.")
    r2 = client.post(f"{GOV}/requests/{p2.ticket}/request-information",
                     json={"reason": "One more thing."}, headers=h)
    assert r2.status_code == 422
    assert p2.status == ProblemStatus.GOVERNMENT_ISSUE.value


# ---- §15 reason validation -------------------------------------------------------------------------------
def test_government_issue_reason_required(db):
    owner, official, pending = seed_routed(db)
    h = authz(gov_token_for(db, official))
    audits_before = db.execute(select(func.count()).select_from(GovernmentAction)).scalar_one()
    assert client.post(f"{GOV}/requests/{pending.ticket}/mark-government-issue",
                       json={"reason": ""}, headers=h).status_code == 422
    assert client.post(f"{GOV}/requests/{pending.ticket}/mark-government-issue",
                       json={"reason": "   "}, headers=h).status_code == 422
    assert pending.status == ProblemStatus.GOV_REVIEW_PENDING.value
    assert db.execute(select(func.count()).select_from(GovernmentAction)).scalar_one() == audits_before
    ok = client.post(f"{GOV}/requests/{pending.ticket}/mark-government-issue",
                     json={"reason": "Real reason here."}, headers=h)
    assert ok.status_code == 200


# ---- §16 information-request privacy -------------------------------------------------------------------------
def test_information_request_visibility_rules(db):
    owner = make_user(db)
    stranger = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(db, problem, to_status="MORE_INFORMATION_REQUIRED",
                     actor_id=official.id, info_request="Share the exact ward.")
    t = problem.ticket
    det = client.get(f"/api/v1/problems/{t}", headers=authz(public_token_for(db, owner)))
    assert det.status_code == 200
    assert "Share the exact ward." in (det.json().get("government_review") or {}).get("info_request", "")
    stranger_h = authz(public_token_for(db, stranger))
    assert client.get(f"/api/v1/problems/{t}", headers=stranger_h).status_code == 404
    assert client.get(f"/api/v1/problems/{t}/public").status_code == 404
    assert client.get("/api/v1/problems?page=1&limit=10").json()["items"] == [] or \
        t not in [i["ticket"] for i in client.get("/api/v1/problems?page=1&limit=10").json()["items"]]
    # Stranger cannot answer on the owner's behalf.
    assert client.put(f"/api/v1/problems/{t}", json={"description": "Attacker rewrite of the problem text here."},
                      headers=stranger_h).status_code == 404
    # Owner revision keeps the ticket; strangers still blind afterwards.
    upd = client.put(f"/api/v1/problems/{t}",
                     json={"description": "Borewells in Ward 9 ran dry this season and 200 families queue at tankers daily now.",
                           "revision_note": "Added ward."},
                     headers=authz(public_token_for(db, owner)))
    assert upd.status_code == 200 and upd.json()["ticket"] == t


# ---- §17 history integrity ---------------------------------------------------------------------------------------
def test_history_endpoint_is_read_only(db):
    owner, official, pending = seed_routed(db)
    h = authz(gov_token_for(db, official))
    t = pending.ticket
    assert client.put(f"{GOV}/requests/{t}/history", json={}, headers=h).status_code in (404, 405)
    assert client.patch(f"{GOV}/requests/{t}/history", json={}, headers=h).status_code in (404, 405)
    assert client.delete(f"{GOV}/requests/{t}/history", headers=h).status_code in (404, 405)


def test_malicious_audit_fields_ignored(db):
    owner, official, pending = seed_routed(db)
    h = authz(gov_token_for(db, official))
    r = client.post(f"{GOV}/requests/{pending.ticket}/assign-public",
                    json={"reason": "ok", "actor_id": str(owner.id),
                          "actor_type": "OFFICIAL", "created_at": "2020-01-01T00:00:00Z",
                          "ticket": "JS-PS-2000-000000"},
                    headers=h)
    assert r.status_code == 200, r.text
    rows = db.execute(select(GovernmentAction).where(
        GovernmentAction.problem_id == pending.id,
        GovernmentAction.action == "ASSIGNED_TO_PUBLIC")).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor_id == official.id
    assert rows[0].ticket == pending.ticket


# ---- §18/§19 notification security ------------------------------------------------------------------------------------
def test_notification_recipient_and_links(db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FRONTEND_URL", "https://staging.example")
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(
        db, owner,
        affected_group="Families plus attacker@evil.example.com",
        description="Borewells in our hamlet ran dry each April, forcing 80 households to walk 2 km for water.",
    )
    rows = db.execute(select(Notification).where(
        Notification.problem_id == problem.id)).scalars().all()
    assert len(rows) == 1
    note = rows[0]
    assert note.recipient == owner.email
    assert "attacker@evil" not in note.recipient
    assert note.link.startswith("https://staging.example/problems/" + problem.ticket)
    assert note.link == f"https://staging.example/problems/{problem.ticket}"
    for field in (note.subject, note.body, note.link):
        assert "localhost" not in field and "127.0.0.1" not in field
        lowered = field.lower()
        for secret in ("bearer ", "jwt=", "password", "api-key", "BEGIN ", "-token="):
            assert secret not in lowered, (secret, field[:80])


# ---- §20 file authorization -----------------------------------------------------------------------------------------------
def test_attachment_cross_user_and_traversal_denied(db):
    owner = make_user(db)
    stranger = make_user(db)
    problem = make_problem(db, owner)
    t = problem.ticket
    up = client.post(f"/api/v1/problems/{t}/attachments",
                     files={"file": ("note.txt", b"hello world", "text/plain")},
                     headers=authz(public_token_for(db, owner)))
    assert up.status_code == 201, up.text
    aid = up.json()["id"]
    stranger_h = authz(public_token_for(db, stranger))
    assert client.get(f"/api/v1/problems/{t}/attachments/{aid}/download",
                      headers=stranger_h).status_code == 404
    assert client.delete(f"/api/v1/problems/{t}/attachments/{aid}",
                         headers=stranger_h).status_code == 404
    owner_h = authz(public_token_for(db, owner))
    assert client.get(f"/api/v1/problems/{t}/attachments/{aid}/download",
                      headers=owner_h).status_code == 200
    for evil in ("not-a-uuid", "..%2F..%2Fetc%2Fpasswd", "%2Fetc%2Fpasswd",
                 "....%2F....%2Fsecret.txt"):
        r = client.get(f"/api/v1/problems/{t}/attachments/{evil}/download", headers=owner_h)
        assert r.status_code in (400, 404), (evil, r.status_code)
    # Deleted file is gone.
    assert client.delete(f"/api/v1/problems/{t}/attachments/{aid}", headers=owner_h).status_code == 204
    assert client.get(f"/api/v1/problems/{t}/attachments/{aid}/download",
                      headers=owner_h).status_code == 404


# ---- §22 ticket-privacy brute force ----------------------------------------------------------------------------------------------
def test_pending_ticket_unavailable_to_strangers(db):
    owner = make_user(db)
    stranger = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(db, problem, to_status="MORE_INFORMATION_REQUIRED",
                     actor_id=official.id, info_request="Share the ward.")
    t = problem.ticket
    stranger_h = authz(public_token_for(db, stranger))
    assert client.get(f"/api/v1/problems/{t}", headers=stranger_h).status_code == 404
    pub = client.get(f"/api/v1/problems/{t}/public")
    assert pub.status_code == 404
    assert "GOVERNMENT" not in pub.text.upper() or "not found" in pub.text.lower()
    sols = client.get(f"/api/v1/problems/{t}/solutions", headers=stranger_h)
    assert sols.status_code == 404


# ---- §23 mass assignment ---------------------------------------------------------------------------------------------------------------
def test_server_fields_not_client_assignable(db):
    owner = make_user(db)
    h = authz(public_token_for(db, owner))
    r = client.post("/api/v1/problems", json={
        "title": "Mass assignment probe problem", "category": "Water", "location": "Ward 1",
        "description": "Borewells in our hamlet ran dry each April, forcing 80 households to walk 2 km for water.",
        "affected_group": "Families", "severity": "High",
        "desired_solution_type": "Install a piped supply line",
        "owner_id": str(owner.id), "status": "OPEN", "ticket": "JS-PS-2000-000001",
        "sla_due_at": "2020-01-01T00:00:00Z", "decided_at": "2020-01-01T00:00:00Z",
        "government_review_id": "00000000-0000-0000-0000-000000000000"},
        headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ticket"] != "JS-PS-2000-000001" and body["ticket"].startswith("JS-PS-")
    assert body["status"] != "OPEN"
    t = body["ticket"]
    u = client.put(f"/api/v1/problems/{t}",
                   json={"title": "Edited title here", "status": "OPEN",
                         "ticket": "JS-PS-2000-000002", "owner_id": str(owner.id)},
                   headers=h)
    assert u.status_code == 200, u.text
    assert u.json()["ticket"] == t
    assert u.json()["status"] != "OPEN"


# ---- §24 error handling ------------------------------------------------------------------------------------------------------------------
def test_malformed_requests_fail_safely(db):
    owner = make_user(db)
    h = authz(public_token_for(db, owner))
    cases = [
        ("GET", "/api/v1/problems?page=0&limit=10", None),
        ("GET", "/api/v1/problems?page=1&limit=999", None),
        ("POST", "/api/v1/auth/register",
         {"email": "x@y.com", "password": "Password123", "account_type": "GOVERNMENT",
          "phone": "+919876543210"}),
        ("POST", "/api/v1/problems",
         {"title": "x" * 201, "category": "Water", "location": "W",
          "description": "Borewells in our hamlet ran dry each April, forcing 80 households to walk 2 km for water.",
          "affected_group": "F", "severity": "High", "desired_solution_type": "Fix it"}),
        ("GET", "/api/v1/problems/JS-PS-20--$$/public", None),
    ]
    for method, path, body in cases:
        if method == "GET":
            r = client.get(path, headers=h)
        else:
            r = client.post(path, json=body, headers=h)
        assert r.status_code in (400, 401, 404, 422), (method, path, r.status_code)
        lowered = r.text.lower()
        for leak in ("traceback", "psycopg", "/app/", "select ", ".py\"", "secret"):
            assert leak not in lowered, (method, path, leak)
    raw = client.post("/api/v1/problems", content="{bad json",
                      headers={**h, "Content-Type": "application/json"})
    assert raw.status_code == 422
    assert client.get("/api/v1/problems?q=' OR '1'='1", headers=h).status_code == 200


# ---- §25 rate-limit isolation ----------------------------------------------------------------------------------------------------------------
def test_login_throttle_namespaces_isolated(db):
    from app.core.security import hash_password
    from app.models.user import User

    email = "g8throttle@example.com"
    db.add(User(email=email, account_type="individual", password_hash=hash_password("ThrottlePass123"),
                is_email_verified=True, is_active=True))
    db.commit()
    official = make_official(db)
    # Burn the government namespace.
    for _ in range(5):
        assert gov_login(db, official, password="wrong-pass").status_code == 401
    assert gov_login(db, official, password="wrong-pass").status_code == 429
    # Public namespace on the same IP is unaffected.
    r = client.post("/api/v1/auth/login", json={"identifier": email, "password": "ThrottlePass123"})
    assert r.status_code in (200, 401), r.status_code
    assert r.status_code != 429
    # And vice versa: burn public, government still logs in.
    ratelimit.reset_login_attempts()
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"identifier": email, "password": "nope"})
    assert client.post("/api/v1/auth/login",
                       json={"identifier": email, "password": "nope"}).status_code == 429
    assert gov_login(db, official).status_code == 200