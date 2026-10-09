"""Phase 3 execution tests: solution review/selection, solution
attachments, implementation updates, transparency detail + timeline.
Scratch DB only."""

import pytest
from fastapi.testclient import TestClient

from app.core import gov_revocation, ratelimit, security
from app.main import app
from tests.conftest import (
    APPROVABLE_PROBLEM,
    make_official,
    make_user,
)

client = TestClient(app, raise_server_exceptions=False)

PUB = "/api/v1"
GOV = "/api/v1/government"
PDF = b"%PDF-1.4 phase3 probe"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


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


def make_open(db):
    owner = make_user(db)
    official = make_official(db)
    utok = public_token(db, owner)
    ticket = client.post(f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
                         headers=authz(utok)).json()["ticket"]
    gtok = gov_token(db, official)
    r = client.post(f"{GOV}/requests/{ticket}/assign-public", json={},
                    headers=authz(gtok))
    assert r.status_code == 200, r.text
    return owner, official, ticket


def make_issue(db):
    owner = make_user(db)
    official = make_official(db)
    utok = public_token(db, owner)
    ticket = client.post(f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
                         headers=authz(utok)).json()["ticket"]
    gtok = gov_token(db, official)
    r = client.post(f"{GOV}/requests/{ticket}/mark-government-issue",
                    json={"reason": "Internal handling."},
                    headers=authz(gtok))
    assert r.status_code == 200, r.text
    return owner, official, ticket


def submit_solution(db, solver, ticket, **extra):
    form = {"title": "Solar purifier pilot unit",
            "short_description": "Community RO plant for the ward area.",
            "expected_impact": "Clean water for 300 families."}
    form.update(extra)
    return client.post(
        f"{PUB}/problems/{ticket}/solutions", data=form,
        files={"file": ("plan.pdf", PDF, "application/pdf")},
        headers=authz(public_token(db, solver)))


def test_solution_submit_extended_fields_and_review_flow(db):
    owner, official, ticket = make_open(db)
    solver = make_user(db)
    r = submit_solution(db, solver, ticket,
                        implementation_plan="Phase 1: survey. Phase 2: build.",
                        estimated_cost="Rs. 2,00,000",
                        estimated_timeline="6 months")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["implementation_plan"].startswith("Phase 1")
    assert body["estimated_cost"] == "Rs. 2,00,000"
    assert body["estimated_timeline"] == "6 months"
    assert body["review_status"] == "SUBMITTED"
    assert body["is_selected"] is False
    stok = body["ticket"]

    # Public token cannot review; gov token cannot submit (covered
    # elsewhere). Official reviews:
    gtok = gov_token(db, official)
    r = client.post(f"{GOV}/solutions/{stok}/review",
                    json={"decision": "REJECTED", "reason": ""},
                    headers=authz(gtok))
    assert r.status_code == 422  # reason required
    r = client.post(f"{GOV}/solutions/{stok}/review",
                    json={"decision": "BOGUS", "reason": "x"},
                    headers=authz(gtok))
    assert r.status_code == 422
    r = client.post(f"{GOV}/solutions/{stok}/review",
                    json={"decision": "APPROVED", "reason": "Solid plan."},
                    headers=authz(gtok))
    assert r.status_code == 200, r.text
    assert r.json()["review_status"] == "APPROVED"

    # Selection requires APPROVED; exactly one winner per problem.
    solver2 = make_user(db)
    s2 = submit_solution(db, solver2, ticket).json()["ticket"]
    r = client.post(f"{GOV}/solutions/{s2}/select", headers=authz(gtok))
    assert r.status_code == 422  # not approved yet
    assert client.post(f"{GOV}/solutions/{stok}/select",
                       headers=authz(gtok)).status_code == 200
    assert client.post(f"{GOV}/solutions/{s2}/review",
                       json={"decision": "APPROVED"},
                       headers=authz(gtok)).status_code == 200
    assert client.post(f"{GOV}/solutions/{s2}/select",
                       headers=authz(gtok)).status_code == 200
    first = client.get(f"{PUB}/solutions/{stok}",
                       headers=authz(public_token(db, solver))).json()
    second = client.get(f"{PUB}/solutions/{s2}",
                        headers=authz(public_token(db, solver2))).json()
    assert first["is_selected"] is False
    assert second["is_selected"] is True
    assert second["review_status"] == "SELECTED"
    # Rejected/selected rows are kept, never deleted: both still readable.
    assert first["review_status"] == "APPROVED"


def test_solution_attachments_roundtrip(db):
    owner, official, ticket = make_open(db)
    solver = make_user(db)
    stok = submit_solution(db, solver, ticket).json()["ticket"]
    h = authz(public_token(db, solver))
    r = client.post(f"{PUB}/solutions/{stok}/attachments",
                    files={"file": ("diagram.png", PNG, "image/png")},
                    headers=h)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    r = client.get(f"{PUB}/solutions/{stok}/attachments", headers=h)
    assert r.status_code == 200 and len(r.json()) == 1
    dl = client.get(f"{PUB}/solutions/{stok}/attachments/{aid}/download",
                    headers=h)
    assert dl.status_code == 200 and dl.content == PNG
    stranger = make_user(db)
    sh = authz(public_token(db, stranger))
    assert client.delete(f"{PUB}/solutions/{stok}/attachments/{aid}",
                         headers=sh).status_code == 404
    assert client.delete(f"{PUB}/solutions/{stok}/attachments/{aid}",
                         headers=h).status_code == 204
    assert client.get(f"{PUB}/solutions/{stok}/attachments/{aid}/download",
                      headers=h).status_code == 404


def test_issue_implementation_lifecycle(db):
    owner, official, ticket = make_issue(db)
    gtok = gov_token(db, official)
    # Non-issues rejected; unknown stages rejected.
    r = client.post(f"{GOV}/requests/{ticket}/implementation",
                    data={"stage": "BOGUS_STAGE", "title": "X" * 10},
                    headers=authz(gtok))
    assert r.status_code == 422
    r = client.post(f"{GOV}/requests/{ticket}/implementation",
                    data={"stage": "INVESTIGATION_STARTED",
                          "title": "Site survey begun",
                          "description": "Team visited Ward 7."},
                    files={"files": ("photo.png", PNG, "image/png")},
                    headers=authz(gtok))
    assert r.status_code == 201, r.text
    assert r.json()["stage"] == "INVESTIGATION_STARTED"
    assert len(r.json()["attachments"]) == 1
    r = client.post(f"{GOV}/requests/{ticket}/implementation",
                    data={"stage": "WORK_IN_PROGRESS",
                          "title": "Pipes being laid"},
                    headers=authz(gtok))
    assert r.status_code == 201, r.text
    r = client.get(f"{GOV}/requests/{ticket}/implementation",
                   headers=authz(gtok))
    assert r.status_code == 200
    assert [u["stage"] for u in r.json()["items"]] == [
        "INVESTIGATION_STARTED", "WORK_IN_PROGRESS"]


def test_transparency_detail_flows(db):
    owner, official, ticket = make_open(db)
    solver = make_user(db)
    stok = submit_solution(db, solver, ticket).json()["ticket"]
    gtok = gov_token(db, official)
    client.post(f"{GOV}/solutions/{stok}/review",
                json={"decision": "APPROVED"}, headers=authz(gtok))
    client.post(f"{GOV}/solutions/{stok}/select", headers=authz(gtok))

    r = client.get(f"{PUB}/problems/transparency/{ticket}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["resolution_type"] == "PUBLIC"
    assert body["solution_count"] == 1
    assert body["selected_solution"]["ticket"] == stok
    kinds = [e["kind"] for e in body["timeline"]]
    assert kinds[0] == "submitted"
    assert "ai_review" in kinds and "government" in kinds
    assert "solution_selected" in kinds

    _, _, iticket = make_issue(db)
    r = client.post(f"{GOV}/requests/{iticket}/implementation",
                    data={"stage": "SURVEY_COMPLETED",
                          "title": "Survey done"},
                    headers=authz(gtok))
    assert r.status_code == 201, r.text
    r = client.get(f"{PUB}/problems/transparency/{iticket}")
    assert r.status_code == 200, r.text
    ibody = r.json()
    assert ibody["resolution_type"] == "GOVERNMENT"
    assert len(ibody["implementation_updates"]) == 1
    assert any(e["kind"] == "implementation" for e in ibody["timeline"])

    # Pending and unknown tickets stay invisible.
    pending = client.post(
        f"{PUB}/problems", json=dict(APPROVABLE_PROBLEM),
        headers=authz(public_token(db, owner))).json()["ticket"]
    assert client.get(f"{PUB}/problems/transparency/{pending}").status_code == 404
    assert client.get(
        f"{PUB}/problems/transparency/JS-PS-2026-000000").status_code == 404
    # No internal actor identity leaks into the public timeline.
    import json as _json
    raw = _json.dumps(body).lower()
    assert "employee" not in raw and "decided_by" not in raw
