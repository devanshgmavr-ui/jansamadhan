"""G4 contract tests: owner-only government_review block on ProblemOut.

Runs against the isolated scratch database (conftest guard applies).
"""

from fastapi.testclient import TestClient

from app.main import app
from app.models.problem import ProblemStatus
from app.services import government_review_service as g
from tests.conftest import make_official, make_problem, make_user

client = TestClient(app, raise_server_exceptions=False)


def _owner_token(db, owner):
    from app.core import security

    return security.create_access_token(owner.id)


def test_owner_detail_carries_routing_snapshot(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db,
        problem,
        to_status="MORE_INFORMATION_REQUIRED",
        actor_id=official.id,
        info_request="Share the exact ward and household count.",
    )
    r = client.get(
        f"/api/v1/problems/{problem.ticket}",
        headers={"Authorization": f"Bearer {_owner_token(db, owner)}"},
    )
    assert r.status_code == 200, r.text
    gov = r.json()["government_review"]
    assert gov["review_status"] == "MORE_INFORMATION_REQUIRED"
    assert "household count" in (gov["info_request"] or "")
    assert gov["sla_due_at"] is not None
    assert gov["pending_since"] is not None
    assert gov["expired"] is False


def test_owner_detail_pending_has_no_info_request(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    assert problem.status == ProblemStatus.GOV_REVIEW_PENDING.value
    r = client.get(
        f"/api/v1/problems/{problem.ticket}",
        headers={"Authorization": f"Bearer {_owner_token(db, owner)}"},
    )
    assert r.status_code == 200, r.text
    gov = r.json()["government_review"]
    assert gov["review_status"] == "PENDING"
    assert gov["info_request"] is None


def test_public_surfaces_never_carry_routing_snapshot(db):
    from app.schemas.problem import DiscoveryItem, PublicProblemOut

    assert "government_review" not in PublicProblemOut.model_fields
    assert "government_review" not in DiscoveryItem.model_fields

    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
    )
    pub = client.get(f"/api/v1/problems/{problem.ticket}/public")
    assert pub.status_code == 200, pub.text
    assert "government_review" not in pub.json()
    disc = client.get("/api/v1/problems?page=1&limit=5")
    assert disc.status_code == 200
    for item in disc.json()["items"]:
        assert "government_review" not in item
