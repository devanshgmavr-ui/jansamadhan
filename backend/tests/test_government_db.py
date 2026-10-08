"""G2 database integration tests against the isolated scratch database
(jansamadhan_g2test, see conftest.py). Never touches shared/dev data:
every test truncates all app tables afterwards.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.government import GovernmentAction, GovernmentReview
from app.models.problem import ProblemStatus
from app.services import government_review_service as g
from tests.conftest import (
    PERSONAL_PROBLEM,
    make_official,
    make_problem,
    make_user,
)


def _audits(db, problem):
    return (
        db.execute(
            select(GovernmentAction)
            .where(GovernmentAction.problem_id == problem.id)
            .order_by(GovernmentAction.created_at.asc())
        )
        .scalars()
        .all()
    )


# C. AI approval -> pending ----------------------------------------------------
def test_ai_approval_creates_pending_review_with_sla_and_audit(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    assert problem.status == ProblemStatus.GOV_REVIEW_PENDING.value

    review = g.get_for_problem(db, problem.id)
    assert review is not None
    assert review.status == "PENDING"
    assert review.sla_due_at - review.pending_since == timedelta(hours=24)
    assert review.escalation_flag is False
    assert (review.sla_due_at - review.pending_since).total_seconds() == 86400

    rows = _audits(db, problem)
    assert len(rows) == 1
    assert rows[0].action == "GOV_REVIEW_CREATED"
    assert rows[0].previous_status is None
    assert rows[0].new_status == "PENDING"
    assert rows[0].actor_id is None
    assert rows[0].ticket == problem.ticket


def test_pending_review_creation_is_idempotent(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    first = g.get_for_problem(db, problem.id)
    again = g.ensure_pending_review(db, problem)
    assert again.id == first.id
    assert again.pending_since == first.pending_since
    assert len(_audits(db, problem)) == 1


def test_terminal_review_cannot_reopen_as_pending(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
    )
    with pytest.raises(HTTPException):
        g.ensure_pending_review(db, problem)


# J. Assign to public ------------------------------------------------------------
def test_assign_to_public_opens_problem(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    review = g.apply_decision(
        db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id,
        reason="Verified civic issue.",
    )
    assert review.status == "ASSIGNED_TO_PUBLIC"
    assert review.decided_by == official.id
    assert review.decided_at is not None
    assert problem.status == ProblemStatus.OPEN.value

    rows = _audits(db, problem)
    last = rows[-1]
    assert last.action == "ASSIGNED_TO_PUBLIC"
    assert last.previous_status == "PENDING"
    assert last.new_status == "ASSIGNED_TO_PUBLIC"
    assert last.actor_id == official.id

    # Reuses OPEN: publicly discoverable through the existing path.
    from app.services import discovery_service

    found, _ = discovery_service.search_problems(db)
    assert problem.ticket in {p.ticket for p in found}
    assert discovery_service.get_public(db, problem.ticket) is not None


def test_decision_requires_official_actor(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    with pytest.raises(HTTPException):
        g.apply_decision(db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=None)


def test_decision_on_missing_review_rejected(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner, **PERSONAL_PROBLEM)
    assert problem.status == ProblemStatus.REJECTED.value
    assert g.get_for_problem(db, problem.id) is None
    with pytest.raises(HTTPException):
        g.apply_decision(
            db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
        )


# K. Government issue --------------------------------------------------------------
def test_mark_government_issue_stays_private(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    review = g.apply_decision(
        db, problem, to_status="GOVERNMENT_ISSUE", actor_id=official.id,
        reason="Requires departmental handling.",
    )
    assert review.status == "GOVERNMENT_ISSUE"
    assert problem.status == ProblemStatus.GOVERNMENT_ISSUE.value

    from app.services import discovery_service

    found, _ = discovery_service.search_problems(db)
    assert problem.ticket not in {p.ticket for p in found}
    assert discovery_service.get_public(db, problem.ticket) is None

    # Owner still sees their own problem (IDOR-safe: another user cannot).
    from app.services import problem_service

    assert problem_service.get_owned(db, owner, problem.ticket).id == problem.id
    stranger = make_user(db)
    with pytest.raises(HTTPException):
        problem_service.get_owned(db, stranger, problem.ticket)


# L. Request information -------------------------------------------------------------
def test_request_information_requires_reason_and_stays_private(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    with pytest.raises(HTTPException):
        g.apply_decision(
            db, problem, to_status="MORE_INFORMATION_REQUIRED",
            actor_id=official.id, info_request="   ",
        )
    review = g.apply_decision(
        db, problem, to_status="MORE_INFORMATION_REQUIRED",
        actor_id=official.id,
        info_request="Please share the exact location and household count.",
    )
    assert review.status == "MORE_INFORMATION_REQUIRED"
    assert problem.status == ProblemStatus.MORE_INFORMATION_REQUIRED.value
    assert "household count" in (review.info_request or "")

    from app.services import discovery_service

    found, _ = discovery_service.search_problems(db)
    assert problem.ticket not in {p.ticket for p in found}


# M. More-information response returns to pending ---------------------------------------
def test_user_response_returns_to_pending_with_new_window(db):
    from app.schemas.problem import ProblemUpdate
    from app.services import problem_service

    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    g.apply_decision(
        db, problem, to_status="MORE_INFORMATION_REQUIRED",
        actor_id=official.id, info_request="Share the exact ward and household count.",
    )
    old_due = g.get_for_problem(db, problem.id).sla_due_at

    updated = problem_service.update_problem(
        db,
        owner,
        problem.ticket,
        ProblemUpdate(
            description=(
                "Borewells in Ward 12 ran dry this summer and 200 families "
                "queue at water tankers daily for drinking water."
            ),
            revision_note="Added exact ward and household count.",
        ),
    )
    assert updated.status == ProblemStatus.GOV_REVIEW_PENDING.value
    review = g.get_for_problem(db, problem.id)
    assert review.status == "PENDING"
    assert review.sla_due_at > old_due
    assert review.escalation_flag is False
    assert "ward" in (review.user_response or "").lower()

    actions = [r.action for r in _audits(db, problem)]
    assert "INFORMATION_PROVIDED" in actions
    assert "REOPENED_FOR_GOVERNMENT_REVIEW" in actions
    # One review row per problem, recycled across cycles.
    count = db.execute(
        select(func.count())
        .select_from(GovernmentReview)
        .where(GovernmentReview.problem_id == problem.id)
    ).scalar_one()
    assert count == 1


# G/H/V. Escalation ---------------------------------------------------------------
def test_expired_pending_escalates_once(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    review = g.get_for_problem(db, problem.id)
    review.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    review.sla_due_at = review.pending_since + timedelta(hours=24)
    db.add(review)
    db.commit()

    moment = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)
    out = g.escalate_if_expired(db, problem, now=moment)
    assert out is not None
    assert out.status == "AUTO_ESCALATED"
    assert out.escalation_flag is True
    assert out.decided_by is None
    assert problem.status == ProblemStatus.AUTO_ESCALATED.value

    rows = _audits(db, problem)
    escalations = [r for r in rows if r.action == "AUTO_ESCALATED"]
    assert len(escalations) == 1
    assert escalations[0].actor_id is None
    assert escalations[0].previous_status == "PENDING"

    # Idempotent: repeated calls change nothing and audit nothing new.
    again = g.escalate_if_expired(db, problem, now=moment)
    assert again.status == "AUTO_ESCALATED"
    assert len(_audits(db, problem)) == len(rows)

    # Escalated problems are not public.
    from app.services import discovery_service

    found, _ = discovery_service.search_problems(db)
    assert problem.ticket not in {p.ticket for p in found}


def test_non_expired_pending_untouched(db):
    owner = make_user(db)
    problem = make_problem(db, owner)
    before = len(_audits(db, problem))
    out = g.escalate_if_expired(db, problem)
    assert out is not None
    assert out.status == "PENDING"
    assert problem.status == ProblemStatus.GOV_REVIEW_PENDING.value
    assert len(_audits(db, problem)) == before


def test_sweep_escalates_only_expired(db):
    owner = make_user(db)
    old = make_problem(db, owner)
    fresh = make_problem(db, owner)
    stale = g.get_for_problem(db, old.id)
    stale.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    stale.sla_due_at = stale.pending_since + timedelta(hours=24)
    db.add(stale)
    db.commit()

    moment = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)
    escalated = g.sweep_expired(db, now=moment)
    assert old.id in escalated
    assert fresh.id not in escalated
    assert g.get_for_problem(db, fresh.id).status == "PENDING"


def test_escalated_problem_can_be_routed(db):
    owner = make_user(db)
    official = make_official(db)
    problem = make_problem(db, owner)
    review = g.get_for_problem(db, problem.id)
    review.pending_since = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    review.sla_due_at = review.pending_since + timedelta(hours=24)
    db.add(review)
    db.commit()
    g.escalate_if_expired(
        db, problem, now=datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)
    )
    out = g.apply_decision(
        db, problem, to_status="GOVERNMENT_ISSUE", actor_id=official.id,
        reason="Requires departmental handling.",
    )
    assert out.status == "GOVERNMENT_ISSUE"
    assert problem.status == ProblemStatus.GOVERNMENT_ISSUE.value


# R. Solution protection --------------------------------------------------------------
def test_solutions_blocked_until_open(db):
    import io

    from fastapi import UploadFile
    from starlette.datastructures import Headers

    from app.services import solution_service

    owner = make_user(db)
    solver = make_user(db)
    problem = make_problem(db, owner)

    def attempt():
        pdf = UploadFile(
            filename="plan.pdf",
            file=io.BytesIO(b"%PDF-1.4 test solution"),
            headers=Headers({"content-type": "application/pdf"}),
        )
        return solution_service.submit_solution(
            db, solver, problem.ticket, title="Fix",
            short_description="Do the thing well.",
            skills=None, expected_impact="Clean water for all",
            contributors=None, estimated_resources=None, pdf=pdf,
        )

    with pytest.raises(HTTPException) as exc:
        attempt()
    assert exc.value.status_code == 422

    official = make_official(db)
    g.apply_decision(
        db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
    )
    solution = attempt()
    assert solution.ticket.startswith("JS-SOL-")


# S. Duplicate candidates ------------------------------------------------------------
def test_pending_problems_are_duplicate_candidates(db):
    from app.services.ai import problem_review_service

    owner = make_user(db)
    first = make_problem(db, owner)
    assert first.status == ProblemStatus.GOV_REVIEW_PENDING.value
    second = make_problem(db, owner)
    names = [c["ticket"] for c in problem_review_service._candidates(db, second)]
    assert first.ticket in names


# Tracking ----------------------------------------------------------------------------
def test_track_distinguishes_government_states(db):
    from app.services import problem_service

    owner = make_user(db)
    problem = make_problem(db, owner)
    track = problem_service.track(db, owner, problem.ticket)
    keys = [s.key for s in track.stages]
    assert "government_review" in keys
    current = [s for s in track.stages if s.state == "current"]
    assert len(current) == 1 and current[0].key == "government_review"

    official = make_official(db)
    g.apply_decision(
        db, problem, to_status="ASSIGNED_TO_PUBLIC", actor_id=official.id
    )
    track2 = problem_service.track(db, owner, problem.ticket)
    current2 = [s for s in track2.stages if s.state == "current"]
    assert len(current2) == 1 and current2[0].key == "open"
