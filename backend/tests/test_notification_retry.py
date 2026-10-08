"""Notification retry runner tests (Task 2). No real Brevo credentials:
the service default sender is monkeypatched with a recorder. The runner
uses its own real session against the scratch DB. Scratch DB only."""

import pytest
from sqlalchemy import func, select

from app.models.government import Notification, NotificationStatus
from app.models.problem import Problem
from app.models.user import User
from app.services import notification_service as n
from scripts import notification_retry as runner
from tests.conftest import make_problem, make_user
from tests.test_notifications import Recorder


@pytest.fixture()
def sender(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(n, "_default_sender", rec)
    return rec


@pytest.fixture()
def failing_sender(monkeypatch):
    rec = Recorder(fail=True)
    monkeypatch.setattr(n, "_default_sender", rec)
    return rec


def _fail_one(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    row = db.execute(
        select(Notification).where(Notification.problem_id == problem.id)
    ).scalars().one()
    row.status = NotificationStatus.FAILED.value
    row.attempts = 1
    db.add(row)
    db.commit()
    return problem.id


def _row(db, problem_id):
    db.expire_all()
    return db.execute(
        select(Notification).where(Notification.problem_id == problem_id)
    ).scalars().one()


def _problem(db, problem_id):
    db.expire_all()
    return db.get(Problem, problem_id)


def test_runner_empty_success(db, sender, capsys):
    assert runner.main(100) == 0
    assert "attempted=0 sent=0 failed=0" in capsys.readouterr().out
    assert sender.sent == []


def test_runner_retries_failed(db, sender):
    problem_id = _fail_one(db)
    sender.sent.clear()  # creation-time send is not part of the retry
    assert runner.main(100) == 0
    row = _row(db, problem_id)
    assert row.status == NotificationStatus.SENT.value
    assert row.attempts == 2
    assert len(sender.sent) == 1
    owner_email = db.get(User, _problem(db, problem_id).owner_id).email
    assert sender.sent[0]["to"] == owner_email


def test_runner_does_not_resend_sent(db, sender):
    owner = make_user(db)
    make_problem(db, owner)  # SENT immediately via fixture sender
    attempts_before = db.execute(
        select(func.sum(Notification.attempts))).scalar_one()
    sender.sent.clear()
    assert runner.main(100) == 0
    assert sender.sent == []
    assert db.execute(
        select(func.sum(Notification.attempts))).scalar_one() == attempts_before


def test_runner_records_failure(db, failing_sender, capsys):
    owner = make_user(db)
    problem = make_problem(db, owner)  # delivery fails -> FAILED
    assert runner.main(100) == 0  # runner itself still succeeds
    assert "attempted=1 sent=0 failed=1" in capsys.readouterr().out
    row = _row(db, problem.id)
    assert row.status == NotificationStatus.FAILED.value
    assert row.attempts == 2
    # Workflow state is untouched by the mail failure.
    assert _problem(db, problem.id).status == "GOV_REVIEW_PENDING"


def test_runner_idempotent(db, sender):
    _fail_one(db)
    sender.sent.clear()  # creation-time send is not part of the retry
    assert runner.main(100) == 0
    assert runner.main(100) == 0
    assert len(sender.sent) == 1


def test_runner_no_secrets_in_output(db, sender, capsys):
    from app.core.config import settings

    _fail_one(db)
    assert runner.main(100) == 0
    out = capsys.readouterr().out
    for secret in (settings.BREVO_API_KEY, settings.SUPABASE_SERVICE_ROLE_KEY,
                   settings.JWT_SECRET_KEY, settings.DATABASE_URL):
        if secret:
            assert secret not in out


def test_runner_db_unreachable_exit_2(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(runner, "SessionLocal", boom)
    assert runner.main(100) == 2


def test_runner_run_failure_exit_2(monkeypatch):
    def boom(db_session, *, limit):
        raise RuntimeError("service down")

    monkeypatch.setattr(n, "retry_failed", boom)
    assert runner.main(100) == 2
