"""G7 notification tests: content, recipient, delivery, failure isolation,
idempotency, retry. Scratch DB only."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.government import GovernmentAction, Notification
from app.models.problem import ProblemStatus
from app.services import government_review_service as g
from app.services import notification_service as n
from tests.conftest import make_official, make_problem, make_user


class Recorder:
    """Fake mail sender: records payloads, optionally fails."""

    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    def __call__(self, *, to, subject, body):
        if self.fail:
            from app.services.brevo_provider import BrevoDeliveryError

            raise BrevoDeliveryError("SMTP down.")
        self.sent.append({"to": to, "subject": subject, "body": body})


@pytest.fixture()
def sender(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(n, "_default_sender", rec)
    return rec


def _intents(db, problem):
    return (
        db.execute(
            select(Notification)
            .where(Notification.problem_id == problem.id)
            .order_by(Notification.created_at.asc())
        )
        .scalars()
        .all()
    )


def test_pending_approval_queues_intent(db, sender):
    owner = make_user(db)
    problem = make_problem(db, owner)
    rows = _intents(db, problem)
    assert len(rows) == 1
    assert rows[0].type == "GOV_REVIEW_PENDING"
    assert rows[0].status == "SENT"
    assert rows[0].recipient == owner.email
    assert rows[0].ticket == problem.ticket
    assert len(sender.sent) == 1
    assert sender.sent[0]["to"] == owner.email


def test_all_five_types_have_intents(db, sender):
    owner = make_user(db)
    official = make_official(db)

    p1 = make_problem(db, owner)
    p2 = make_problem(db, owner)
    g.apply_decision(
        db, p2, to_status="MORE_INFORMATION_REQUIRED",
        actor_id=official.id, info_request="Share the ward please.",
    )
    p3 = make_problem(db, owner)
    g.apply_decision(
        db, p3, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
    )
    p4 = make_problem(db, owner)
    g.apply_decision(
        db, p4, to_status="GOVERNMENT_ISSUE", actor_id=official.id,
        reason="Departmental matter.",
    )
    p5 = make_problem(db, owner)
    review = g.get_for_problem(db, p5.id)
    review.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    review.sla_due_at = review.pending_since + timedelta(hours=24)
    db.add(review)
    db.commit()
    g.sweep_expired(db, now=datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc))

    got = {}
    for p in (p1, p2, p3, p4, p5):
        for row in _intents(db, p):
            got.setdefault(row.type, []).append(row)
    assert set(got) == {
        "GOV_REVIEW_PENDING",
        "MORE_INFORMATION_REQUIRED",
        "ASSIGNED_TO_PUBLIC",
        "GOVERNMENT_ISSUE",
        "AUTO_ESCALATED",
    }
    assert all(r.status == "SENT" for rows in got.values() for r in rows)


def test_content_wording_links_and_no_secrets(db, sender, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "FRONTEND_URL", "https://staging.example")
    owner = make_user(db)
    problem = make_problem(db, owner)
    assert len(sender.sent) == 1
    payload = sender.sent[0]
    assert problem.ticket in payload["subject"]
    assert problem.ticket in payload["body"]
    assert "https://staging.example/problems/" + problem.ticket in payload["body"]
    assert "localhost" not in payload["subject"] + payload["body"]
    assert "127.0.0.1" not in payload["subject"] + payload["body"]
    for secret in ("password", "otp", "jwt", "api-key", "Bearer", "accepted responsibility"):
        assert secret.lower() not in (payload["subject"] + payload["body"]).lower()


def test_escalation_copy_denies_acceptance(db, sender):
    owner = make_user(db)
    problem = make_problem(db, owner)
    review = g.get_for_problem(db, problem.id)
    review.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    review.sla_due_at = review.pending_since + timedelta(hours=24)
    db.add(review)
    db.commit()
    g.sweep_expired(db, now=datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc))
    bodies = [m["body"] for m in sender.sent if "escalat" in m["subject"].lower()]
    assert len(bodies) == 1
    assert "No department has accepted responsibility" in bodies[0]


def test_more_info_email_carries_reason_and_edit_link(db, sender):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    sender.sent.clear()
    g.apply_decision(
        db, problem, to_status="MORE_INFORMATION_REQUIRED",
        actor_id=official.id, info_request="Share the exact ward.",
    )
    last = sender.sent[-1]
    assert "Share the exact ward." in last["body"]
    assert f"/problems/{problem.ticket}/edit" in last["body"]


def test_failed_delivery_records_failed_without_rollback(db, monkeypatch):
    rec = Recorder(fail=True)
    monkeypatch.setattr(n, "_default_sender", rec)
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    # Approval intent already FAILED above; now the decision must still commit.
    g.apply_decision(
        db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
    )
    assert problem.status == ProblemStatus.OPEN.value
    assert g.get_for_problem(db, problem.id).status == "ASSIGNED_TO_PUBLIC"
    rows = {r.type: r for r in _intents(db, problem)}
    assert rows["ASSIGNED_TO_PUBLIC"].status == "FAILED"
    assert rows["ASSIGNED_TO_PUBLIC"].attempts >= 1
    assert "password" not in (rows["ASSIGNED_TO_PUBLIC"].error_detail or "").lower()


def test_idempotent_rerun_creates_no_duplicate_intent(db, sender):
    owner = make_user(db)
    problem = make_problem(db, owner)
    assert len(_intents(db, problem)) == 1
    g.ensure_pending_review(db, problem)
    g.ensure_pending_review(db, problem)
    assert len(_intents(db, problem)) == 1
    assert len(sender.sent) == 1


def test_repeat_sweep_creates_no_duplicate_escalation_intent(db, sender):
    owner = make_user(db)
    problem = make_problem(db, owner)
    review = g.get_for_problem(db, problem.id)
    review.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    review.sla_due_at = review.pending_since + timedelta(hours=24)
    db.add(review)
    db.commit()
    moment = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)
    g.sweep_expired(db, now=moment)
    g.sweep_expired(db, now=moment)
    auto = [r for r in _intents(db, problem) if r.type == "AUTO_ESCALATED"]
    assert len(auto) == 1
    assert auto[0].status == "SENT"


def test_retry_failed_respects_bound(db, monkeypatch):
    rec = Recorder(fail=True)
    monkeypatch.setattr(n, "_default_sender", rec)
    owner = make_user(db)
    problem = make_problem(db, owner)
    row = _intents(db, problem)[0]
    assert row.status == "FAILED"

    rec.fail = False
    out = n.retry_failed(db, sender=rec)
    assert out["sent"] == 1
    db.refresh(row)
    assert row.status == "SENT"
    assert row.sent_at is not None

    # Exhausted intents are never retried again.
    row.status = "FAILED"
    row.attempts = 3
    db.add(row)
    db.commit()
    out = n.retry_failed(db)
    assert out["attempted"] == 0


def test_one_intent_per_audit_event(db, sender):
    owner = make_user(db)
    problem = make_problem(db, owner)
    audits = (
        db.execute(
            select(func.count()).select_from(GovernmentAction).where(
                GovernmentAction.problem_id == problem.id
            )
        ).scalar_one()
    )
    intents = (
        db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.problem_id == problem.id
            )
        ).scalar_one()
    )
    assert audits == 1
    assert intents == 1
