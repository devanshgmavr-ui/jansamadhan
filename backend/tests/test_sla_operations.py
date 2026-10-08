"""G6 SLA operations: non-pending immunity, ticket/audit integrity, and
concurrent-sweep safety. Runs against the isolated scratch database."""

import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.db.database import SessionLocal
from app.models.government import GovernmentAction, GovernmentReview
from app.models.problem import Problem, ProblemStatus
from app.services import government_review_service as g
from tests.conftest import make_official, make_problem, make_user

STALE = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
LATE = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)


def _backdate(db, problem, since=STALE):
    review = g.get_for_problem(db, problem.id)
    review.pending_since = since
    review.sla_due_at = since + timedelta(hours=24)
    db.add(review)
    db.commit()
    return review


def _audit_actions(db, problem):
    return (
        db.execute(
            select(GovernmentAction.action).where(
                GovernmentAction.problem_id == problem.id
            )
        )
        .scalars()
        .all()
    )


# T10: information-waiting reviews never expire --------------------------------
def test_more_information_review_does_not_escalate(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db, problem, to_status="MORE_INFORMATION_REQUIRED",
        actor_id=official.id, info_request="Share the ward.",
    )
    _backdate(db, problem)
    assert g.sweep_expired(db, now=LATE) == []
    assert g.get_for_problem(db, problem.id).status == "MORE_INFORMATION_REQUIRED"
    assert "AUTO_ESCALATED" not in _audit_actions(db, problem)


# T11: assigned problems never expire -------------------------------------------
def test_assigned_problem_does_not_escalate(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
    )
    _backdate(db, problem)
    assert g.sweep_expired(db, now=LATE) == []
    assert g.get_for_problem(db, problem.id).status == "ASSIGNED_TO_PUBLIC"
    assert problem.status == ProblemStatus.OPEN.value


# T12: government-issue problems never expire ------------------------------------
def test_government_issue_does_not_escalate(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db, problem, to_status="GOVERNMENT_ISSUE", actor_id=official.id,
        reason="Departmental matter.",
    )
    _backdate(db, problem)
    assert g.sweep_expired(db, now=LATE) == []
    assert g.get_for_problem(db, problem.id).status == "GOVERNMENT_ISSUE"


# T16: escalation preserves ticket -----------------------------------------------
def test_escalation_audit_carries_original_ticket(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    _backdate(db, problem)
    g.sweep_expired(db, now=LATE)
    rows = (
        db.execute(
            select(GovernmentAction).where(
                GovernmentAction.problem_id == problem.id,
                GovernmentAction.action == "AUTO_ESCALATED",
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].ticket == problem.ticket
    assert problem.ticket.startswith("JS-PS-")


# T15: concurrent sweeps cannot duplicate -----------------------------------------
def test_concurrent_sweep_escalates_exactly_once(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    problem_id = problem.id
    _backdate(db, problem)
    db.close()

    barrier = threading.Barrier(2, timeout=30)
    errors = []

    def attempt():
        session = SessionLocal()
        try:
            target = session.get(Problem, problem_id)
            barrier.wait(timeout=30)
            g.escalate_if_expired(session, target, now=LATE)
        except Exception as exc:  # noqa: BLE001 - collected and asserted
            errors.append(exc)
        finally:
            session.close()

    workers = [threading.Thread(target=attempt, daemon=True) for _ in range(2)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=60)
    assert not [w for w in workers if w.is_alive()]
    assert errors == []

    check = SessionLocal()
    try:
        count = check.execute(
            select(func.count())
            .select_from(GovernmentAction)
            .where(
                GovernmentAction.problem_id == problem_id,
                GovernmentAction.action == "AUTO_ESCALATED",
            )
        ).scalar_one()
        assert count == 1
        review = g.get_for_problem(check, problem_id)
        assert review.status == "AUTO_ESCALATED"
    finally:
        check.close()


# Scheduler interface: the standalone runner works against the DB ------------------
def test_sweep_script_escalates_and_reports(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    _backdate(db, problem)
    db.close()

    script = Path(__file__).resolve().parents[1] / "scripts" / "sla_sweep.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--limit", "50"],
        cwd=str(script.parents[1]),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "escalated=1" in proc.stdout

    check = SessionLocal()
    try:
        assert g.get_for_problem(check, problem.id).status == "AUTO_ESCALATED"
    finally:
        check.close()
