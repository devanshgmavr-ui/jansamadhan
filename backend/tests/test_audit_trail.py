"""G7 audit-trail extras: actor types, history API, append-only surface,
atomicity. Scratch DB only."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models.government import GovernmentAction
from app.models.problem import ProblemStatus
from app.services import government_review_service as g
from tests.conftest import make_official, make_problem, make_user

client = TestClient(app, raise_server_exceptions=False)


def _actions(db, problem):
    return (
        db.execute(
            select(GovernmentAction)
            .where(GovernmentAction.problem_id == problem.id)
            .order_by(GovernmentAction.created_at.asc())
        )
        .scalars()
        .all()
    )


def test_actor_types_recorded_per_event(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db, problem, to_status="MORE_INFORMATION_REQUIRED",
        actor_id=official.id, info_request="Share the ward.",
    )
    from app.schemas.problem import ProblemUpdate
    from app.services import problem_service

    problem_service.update_problem(
        db, owner, problem.ticket,
        ProblemUpdate(description=problem.description + " Extra ward detail here."),
    )
    kinds = {r.action: r.actor_type for r in _actions(db, problem)}
    assert kinds["GOV_REVIEW_CREATED"] == "SYSTEM"
    assert kinds["REQUESTED_INFORMATION"] == "GOVERNMENT_OFFICIAL"
    assert kinds["INFORMATION_PROVIDED"] == "PUBLIC_USER"
    assert kinds["REOPENED_FOR_GOVERNMENT_REVIEW"] == "SYSTEM"
    # No fake official anywhere a human did not act.
    for row in _actions(db, problem):
        if row.actor_type == "GOVERNMENT_OFFICIAL":
            assert row.actor_id == official.id


def test_escalation_audit_is_system_actor(db):
    from datetime import datetime, timedelta, timezone

    owner = make_user(db)
    problem = make_problem(db, owner)
    review = g.get_for_problem(db, problem.id)
    review.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    review.sla_due_at = review.pending_since + timedelta(hours=24)
    db.add(review)
    db.commit()
    g.sweep_expired(db, now=datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc))
    rows = [r for r in _actions(db, problem) if r.action == "AUTO_ESCALATED"]
    assert len(rows) == 1
    assert rows[0].actor_id is None
    assert rows[0].actor_type == "SYSTEM"


def test_history_labels_actor_kinds_without_leaking(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db, problem, to_status="MORE_INFORMATION_REQUIRED",
        actor_id=official.id, info_request="Share the ward.",
    )
    from app.core import security

    token = security.create_government_token(official.id)
    r = client.get(
        f"/api/v1/government/requests/{problem.ticket}/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    kinds = {e["action"]: e["actor"] for e in r.json()}
    assert kinds["GOV_REVIEW_CREATED"]["kind"] == "system"
    assert kinds["REQUESTED_INFORMATION"]["kind"] == "official"
    assert kinds["REQUESTED_INFORMATION"]["employee_id"] == official.employee_id
    raw = r.text
    assert "password_hash" not in raw and "jti" not in raw


def test_no_audit_mutation_routes_exist():
    paths = app.openapi()["paths"]
    history = paths.get("/api/v1/government/requests/{ticket}/history", {})
    assert set(history) == {"get"}, set(history)
    for path, methods in paths.items():
        if "government" in path:
            assert "put" not in methods and "delete" not in methods, path


def test_failed_transition_leaves_no_partial_state(db, monkeypatch):
    owner = make_user(db)
    problem = make_problem(db, owner)
    before = len(_actions(db, problem))

    def boom(*args, **kwargs):
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(g, "_audit", boom)
    with pytest.raises(RuntimeError):
        g.apply_decision(
            db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=owner.id
        )
    db.rollback()
    assert problem.status == ProblemStatus.GOV_REVIEW_PENDING.value
    assert len(_actions(db, problem)) == before
    assert g.get_for_problem(db, problem.id).status == "PENDING"
