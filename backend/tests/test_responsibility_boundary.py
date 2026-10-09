"""AI / Government Portal responsibility-boundary tests.

Public side owns submission + AI screening; the Government Portal only
consumes screening data and routes manually. Officials cannot submit,
cannot bypass screening, and nothing auto-decides routing. Scratch DB only.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import json as _json

from app.core import gov_revocation, ratelimit, security
from app.main import app
from app.models.government import GovernmentReview
from app.models.problem import Problem
from tests.conftest import (
    APPROVABLE_PROBLEM,
    PERSONAL_PROBLEM,
    make_official,
    make_user,
)

client = TestClient(app, raise_server_exceptions=False)

GOV = "/api/v1/government"
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


def submit(db, user, payload):
    return client.post(f"{PUB}/problems", json=payload,
                       headers=authz(public_token(db, user)))


# 1/2. public submit -> AI screening -> GOV_REVIEW_PENDING -----------------------
def test_public_submit_runs_ai_screening_then_pending(db):
    owner = make_user(db)
    r = submit(db, owner, dict(APPROVABLE_PROBLEM))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ticket"].startswith("JS-PS-")
    assert body["status"] == "GOV_REVIEW_PENDING"
    rev = client.get(f"{PUB}/problems/{body['ticket']}/reviews",
                     headers=authz(public_token(db, owner)))
    assert rev.status_code == 200, rev.text
    assert rev.json()
    assert rev.json()[0]["decision"] == "APPROVED"
    assert rev.json()[0]["provider"] in ("mock", "openrouter")
    review = db.execute(
        select(GovernmentReview).where(
            GovernmentReview.problem_id == db.execute(
                select(Problem.id).where(Problem.ticket == body["ticket"])
            ).scalar_one()
        )
    ).scalars().one_or_none()
    assert review is not None and review.status == "PENDING"


# 3. personal problem -> rejected, never reaches government -----------------------
def test_personal_problem_rejected_before_government(db):
    owner = make_user(db)
    r = submit(db, owner, dict(PERSONAL_PROBLEM))
    assert r.status_code == 201, r.text
    body = r.json()
    rev = client.get(f"{PUB}/problems/{body['ticket']}/reviews",
                     headers=authz(public_token(db, owner)))
    assert rev.status_code == 200, rev.text
    assert rev.json()[0]["decision"] == "NOT_SOCIETAL"
    assert body["status"] != "GOV_REVIEW_PENDING"
    pid = db.execute(
        select(Problem.id).where(Problem.ticket == body["ticket"])
    ).scalar_one()
    assert db.execute(
        select(GovernmentReview).where(GovernmentReview.problem_id == pid)
    ).scalars().one_or_none() is None


# AI never names departments/authorities -------------------------------------------
def test_ai_output_names_no_department_or_authority(db):
    owner = make_user(db)
    r = submit(db, owner, dict(APPROVABLE_PROBLEM))
    raw = r.text.lower()
    for word in ("department", "ministry", "authority", "municipal corporation"):
        assert word not in raw, word


# 4. official sees pending -----------------------------------------------------------
def test_official_sees_pending_in_queue(db):
    owner = make_user(db)
    official = make_official(db)
    r = submit(db, owner, dict(APPROVABLE_PROBLEM))
    ticket = r.json()["ticket"]
    q = client.get(f"{GOV}/requests?status=PENDING&page=1&page_size=10",
                   headers=authz(gov_token(db, official)))
    assert q.status_code == 200, q.text
    assert ticket in [i["ticket"] for i in q.json()["items"]]


# 5/6/19. officials cannot submit or bypass --------------------------------------------
@pytest.mark.parametrize("method,path,body", [
    ("POST", f"{PUB}/problems", APPROVABLE_PROBLEM),
    ("PUT", f"{PUB}/problems/JS-PS-2026-000001", {"title": "Hijack attempt here"}),
    ("POST", f"{PUB}/problems/JS-PS-2026-000001/solutions", {"title": "x", "description": "y" * 60}),
    ("POST", f"{PUB}/contributions", {"problem_ticket": "JS-PS-2026-000001", "content": "spam spam"}),
    ("POST", f"{PUB}/collaborations", {"title": "x", "description": "y"}),
    ("POST", f"{GOV}/requests", APPROVABLE_PROBLEM),
])
def test_government_token_cannot_submit_or_bypass(db, method, path, body):
    owner = make_user(db)
    make_problem_ticket = submit(db, owner, dict(APPROVABLE_PROBLEM)).json()["ticket"]
    path = path.replace("JS-PS-2026-000001", make_problem_ticket)
    official = make_official(db)
    r = client.request(method, path, json=body,
                       headers=authz(gov_token(db, official)))
    # 401 = recognised route, rejected identity; 404/405 = no such side door.
    assert r.status_code in (401, 404, 405), (method, path, r.status_code)
    if "/government" not in path:
        assert r.status_code == 401, (method, path, r.status_code)


# 12/13/14. info request -> owner revises -> same ticket, fresh window ------------------
def test_rereview_returns_to_pending_same_ticket(db):
    owner = make_user(db)
    official = make_official(db)
    ticket = submit(db, owner, dict(APPROVABLE_PROBLEM)).json()["ticket"]
    gtok = gov_token(db, official)
    utok = public_token(db, owner)
    r = client.post(f"{GOV}/requests/{ticket}/request-information",
                    json={"reason": "Which ward exactly?"},
                    headers=authz(gtok))
    assert r.status_code == 200, r.text
    assert client.get(f"{PUB}/problems/{ticket}",
                      headers=authz(utok)).json()["status"] == \
        "MORE_INFORMATION_REQUIRED"
    before = db.execute(
        select(GovernmentReview.sla_due_at).join(
            Problem, Problem.id == GovernmentReview.problem_id)
        .where(Problem.ticket == ticket)).scalar_one()
    revised = dict(APPROVABLE_PROBLEM)
    revised["location"] = "Ward 12, Shanti Nagar"
    r = client.put(f"{PUB}/problems/{ticket}", json=revised,
                   headers=authz(utok))
    assert r.status_code == 200, r.text
    assert r.json()["ticket"] == ticket  # stable ticket
    assert r.json()["status"] == "GOV_REVIEW_PENDING"
    after = db.execute(
        select(GovernmentReview.sla_due_at).join(
            Problem, Problem.id == GovernmentReview.problem_id)
        .where(Problem.ticket == ticket)).scalar_one()
    assert after > before  # fresh 24h window


# track carries the persisted government decision -----------------------------------
def _track(db, user, ticket):
    from app.core import security

    token = security.create_access_token(user.id)
    r = client.get(f"{PUB}/problems/{ticket}/track",
                   headers=authz(token))
    assert r.status_code == 200, r.text
    return r.json()


def test_track_reflects_routing_decision(db):
    owner = make_user(db)
    official = make_official(db)
    ticket = submit(db, owner, dict(APPROVABLE_PROBLEM)).json()["ticket"]
    before = _track(db, owner, ticket)
    assert before["status"] == "GOV_REVIEW_PENDING"
    assert before["government_review"]["review_status"] == "PENDING"
    gtok = gov_token(db, official)
    r = client.post(f"{GOV}/requests/{ticket}/assign-public", json={},
                    headers=authz(gtok))
    assert r.status_code == 200, r.text
    after = _track(db, owner, ticket)
    assert after["status"] == "OPEN"
    assert after["government_review"]["review_status"] == "ASSIGNED_TO_PUBLIC"
    assert after["updated_at"] >= before["updated_at"]
    gov_stage = [s for s in after["stages"] if s["key"] == "government_review"]
    assert gov_stage and gov_stage[0]["state"] == "done"
    open_stage = [s for s in after["stages"] if s["key"] == "open"]
    assert open_stage and open_stage[0]["state"] == "current"


def test_track_shows_information_request(db):
    owner = make_user(db)
    official = make_official(db)
    ticket = submit(db, owner, dict(APPROVABLE_PROBLEM)).json()["ticket"]
    gtok = gov_token(db, official)
    r = client.post(f"{GOV}/requests/{ticket}/request-information",
                    json={"reason": "Which ward exactly?"},
                    headers=authz(gtok))
    assert r.status_code == 200, r.text
    body = _track(db, owner, ticket)
    assert body["status"] == "MORE_INFORMATION_REQUIRED"
    assert body["government_review"]["review_status"] == \
        "MORE_INFORMATION_REQUIRED"
    assert body["government_review"]["info_request"] == "Which ward exactly?"


def test_track_exposes_no_internal_fields(db):
    owner = make_user(db)
    official = make_official(db)
    ticket = submit(db, owner, dict(APPROVABLE_PROBLEM)).json()["ticket"]
    gtok = gov_token(db, official)
    client.post(f"{GOV}/requests/{ticket}/request-information",
                json={"reason": "Which ward exactly?"},
                headers=authz(gtok))
    raw = _json.dumps(_track(db, owner, ticket)).lower()
    for forbidden in ("decided_by", "actor", "password", "official_id",
                      "internal", "note"):
        assert forbidden not in raw, forbidden
    for allowed in ("review_status", "info_request", "pending_since",
                    "sla_due_at"):
        assert allowed in raw, allowed


def test_track_without_routing_has_null_snapshot(db):
    owner = make_user(db)
    r = submit(db, owner, dict(PERSONAL_PROBLEM))
    body = _track(db, owner, r.json()["ticket"])
    assert body["government_review"] is None


# Phase 1 decision classification --------------------------------------------------
def test_assign_public_records_public_resolution(db):
    owner = make_user(db)
    official = make_official(db)
    ticket = submit(db, owner, dict(APPROVABLE_PROBLEM)).json()["ticket"]
    gtok = gov_token(db, official)
    r = client.post(f"{GOV}/requests/{ticket}/assign-public",
                    json={"reason": "Strong community potential."},
                    headers=authz(gtok))
    assert r.status_code == 200, r.text
    body = _track(db, owner, ticket)
    assert body["government_review"]["resolution_type"] == "PUBLIC"
    assert body["government_review"]["decision_reason"] == \
        "Strong community potential."


def test_government_issue_records_government_resolution(db):
    owner = make_user(db)
    official = make_official(db)
    ticket = submit(db, owner, dict(APPROVABLE_PROBLEM)).json()["ticket"]
    gtok = gov_token(db, official)
    r = client.post(f"{GOV}/requests/{ticket}/mark-government-issue",
                    json={"reason": "Needs departmental handling."},
                    headers=authz(gtok))
    assert r.status_code == 200, r.text
    body = _track(db, owner, ticket)
    assert body["status"] == "GOVERNMENT_ISSUE"
    assert body["government_review"]["resolution_type"] == "GOVERNMENT"
    assert body["government_review"]["decision_reason"] == \
        "Needs departmental handling."


def test_pending_has_no_resolution_type(db):
    owner = make_user(db)
    ticket = submit(db, owner, dict(APPROVABLE_PROBLEM)).json()["ticket"]
    body = _track(db, owner, ticket)
    assert body["government_review"]["resolution_type"] is None
    assert body["government_review"]["decision_reason"] is None


# 20. escalation claims no acceptance -----------------------------------------------------
def test_escalation_never_claims_acceptance(db):
    from datetime import datetime, timezone
    from app.services import government_review_service as g

    owner = make_user(db)
    official = make_official(db)
    ticket = submit(db, owner, dict(APPROVABLE_PROBLEM)).json()["ticket"]
    problem = db.execute(
        select(Problem).where(Problem.ticket == ticket)).scalars().one()
    review = g.get_for_problem(db, problem.id)
    review.pending_since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    review.sla_due_at = datetime(2020, 1, 2, tzinfo=timezone.utc)
    db.add(review)
    db.commit()
    gtok = gov_token(db, official)
    r = client.post(f"{GOV}/requests/sweep-escalations", headers=authz(gtok))
    assert r.status_code == 200, r.text
    assert ticket in r.json()["escalated_tickets"]
    db.refresh(problem)
    assert problem.status != "OPEN"  # still not public
    assert problem.status == "AUTO_ESCALATED"  # queue escalation, not acceptance
    h = client.get(f"{GOV}/requests/{ticket}/history",
                   headers=authz(gtok)).json()
    assert h[-1]["action"] == "AUTO_ESCALATED"
