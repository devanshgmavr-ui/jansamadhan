"""G2 pure unit tests: state machine, SLA math, visibility sets, audit design.

No database required. Deterministic; no network, no clock dependence
(timestamps are passed explicitly wherever behavior is time-sensitive).
"""

import pytest
from fastapi import HTTPException

from app.models.government import (
    GovernmentAction,
    GovernmentActionType,
    GovernmentReview,
    GovernmentReviewStatus,
    GovernmentUser,
)
from app.models.problem import ProblemStatus
from app.services import government_review_service as g
from app.services.discovery_service import PUBLIC_STATUSES


# A. Problem status values -------------------------------------------------
def test_new_problem_statuses_exist_and_approved_retained():
    assert ProblemStatus.GOV_REVIEW_PENDING.value == "GOV_REVIEW_PENDING"
    assert ProblemStatus.MORE_INFORMATION_REQUIRED.value == "MORE_INFORMATION_REQUIRED"
    assert ProblemStatus.GOVERNMENT_ISSUE.value == "GOVERNMENT_ISSUE"
    assert ProblemStatus.AUTO_ESCALATED.value == "AUTO_ESCALATED"
    assert ProblemStatus.APPROVED.value == "APPROVED"  # legacy retained
    assert ProblemStatus.OPEN.value == "OPEN"


# B. Legal edges ------------------------------------------------------------
@pytest.mark.parametrize(
    "frm,to",
    [
        ("PENDING", "ASSIGNED_TO_PUBLIC"),
        ("PENDING", "GOVERNMENT_ISSUE"),
        ("PENDING", "MORE_INFORMATION_REQUIRED"),
        ("PENDING", "AUTO_ESCALATED"),
        ("AUTO_ESCALATED", "ASSIGNED_TO_PUBLIC"),
        ("AUTO_ESCALATED", "GOVERNMENT_ISSUE"),
        ("AUTO_ESCALATED", "MORE_INFORMATION_REQUIRED"),
        ("MORE_INFORMATION_REQUIRED", "PENDING"),
    ],
)
def test_legal_transitions_accepted(frm, to):
    g.assert_transition(frm, to)  # must not raise


# N. Illegal edges ----------------------------------------------------------
@pytest.mark.parametrize(
    "frm,to",
    [
        ("ASSIGNED_TO_PUBLIC", "PENDING"),
        ("ASSIGNED_TO_PUBLIC", "GOVERNMENT_ISSUE"),
        ("GOVERNMENT_ISSUE", "PENDING"),
        ("GOVERNMENT_ISSUE", "ASSIGNED_TO_PUBLIC"),
        ("PENDING", "OPEN"),  # must route via ASSIGNED_TO_PUBLIC
        ("PENDING", "PENDING"),  # recycle path only, not a transition
        ("MORE_INFORMATION_REQUIRED", "OPEN"),
        ("MORE_INFORMATION_REQUIRED", "ASSIGNED_TO_PUBLIC"),
        ("AUTO_ESCALATED", "PENDING"),  # recycle path only
        ("AUTO_ESCALATED", "AUTO_ESCALATED"),
        ("BOGUS", "PENDING"),
        ("PENDING", "BOGUS"),
    ],
)
def test_illegal_transitions_rejected(frm, to):
    with pytest.raises(HTTPException) as exc:
        g.assert_transition(frm, to)
    assert exc.value.status_code == 422


# Mapping -------------------------------------------------------------------
def test_review_to_problem_mapping():
    assert g.review_to_problem_status("PENDING") == "GOV_REVIEW_PENDING"
    assert g.review_to_problem_status("MORE_INFORMATION_REQUIRED") == (
        "MORE_INFORMATION_REQUIRED"
    )
    assert g.review_to_problem_status("GOVERNMENT_ISSUE") == "GOVERNMENT_ISSUE"
    assert g.review_to_problem_status("AUTO_ESCALATED") == "AUTO_ESCALATED"
    # Assign-to-public reuses OPEN so the public lifecycle continues unchanged.
    assert g.review_to_problem_status("ASSIGNED_TO_PUBLIC") == "OPEN"
    with pytest.raises(HTTPException):
        g.review_to_problem_status("BOGUS")


# E. SLA math ----------------------------------------------------------------
def test_sla_due_exactly_24_hours():
    from datetime import datetime, timedelta, timezone

    start = datetime(2026, 10, 6, 10, 0, tzinfo=timezone.utc)
    assert g.sla_due_for(start) == start + timedelta(hours=24)
    assert g.sla_due_for(start) == datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)


# F/I. Expiry predicate (in-memory rows, no DB) -------------------------------
def _mem_review(status, pending_since, sla_due_at):
    return GovernmentReview(
        problem_id="00000000-0000-0000-0000-000000000000",
        status=status,
        pending_since=pending_since,
        sla_due_at=sla_due_at,
    )


def test_expired_pending_detected():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 7, 11, 0, tzinfo=timezone.utc)
    start = now - timedelta(hours=25)
    assert g.is_expired(_mem_review("PENDING", start, start + timedelta(hours=24)), now)


def test_non_expired_pending_untouched():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc)
    start = now - timedelta(hours=1)
    assert not g.is_expired(
        _mem_review("PENDING", start, start + timedelta(hours=24)), now
    )


def test_non_pending_never_expired():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 9, 11, 0, tzinfo=timezone.utc)
    start = now - timedelta(days=3)
    for status in (
        "ASSIGNED_TO_PUBLIC",
        "GOVERNMENT_ISSUE",
        "MORE_INFORMATION_REQUIRED",
        "AUTO_ESCALATED",
    ):
        assert not g.is_expired(
            _mem_review(status, start, start + timedelta(hours=24)), now
        )


# O. Visibility sets ----------------------------------------------------------
def test_pending_family_excluded_from_public():
    assert g.NON_PUBLIC_GOVERNMENT_STATUSES == frozenset(
        {
            "GOV_REVIEW_PENDING",
            "MORE_INFORMATION_REQUIRED",
            "GOVERNMENT_ISSUE",
            "AUTO_ESCALATED",
        }
    )
    assert g.NON_PUBLIC_GOVERNMENT_STATUSES.isdisjoint(set(PUBLIC_STATUSES))
    for value in (
        ProblemStatus.GOV_REVIEW_PENDING.value,
        ProblemStatus.MORE_INFORMATION_REQUIRED.value,
        ProblemStatus.GOVERNMENT_ISSUE.value,
        ProblemStatus.AUTO_ESCALATED.value,
    ):
        assert value not in PUBLIC_STATUSES
    assert ProblemStatus.OPEN.value in PUBLIC_STATUSES


# T/U. Audit vocabulary + append-only design ------------------------------------
def test_action_vocabulary_closed():
    assert {m.value for m in GovernmentActionType} == {
        "GOV_REVIEW_CREATED",
        "ASSIGNED_TO_PUBLIC",
        "MARKED_GOVERNMENT_ISSUE",
        "REQUESTED_INFORMATION",
        "INFORMATION_PROVIDED",
        "REOPENED_FOR_GOVERNMENT_REVIEW",
        "AUTO_ESCALATED",
    }


def test_audit_surface_is_append_only():
    mutators = [
        name
        for name in dir(g)
        if callable(getattr(g, name))
        and ("audit" in name.lower() or "action" in name.lower())
        and any(
            verb in name.lower() for verb in ("update", "delete", "remove", "edit")
        )
    ]
    assert mutators == []
    assert GovernmentAction.__table__.columns["actor_id"].nullable is True


def test_model_constraints_declared():
    review_cols = GovernmentReview.__table__.columns
    assert review_cols["problem_id"].unique is True
    assert review_cols["pending_since"].nullable is False
    assert review_cols["sla_due_at"].nullable is False
    assert review_cols["decided_by"].nullable is True
    assert GovernmentUser.__table__.columns["employee_id"].unique is True
    assert GovernmentUser.__table__.columns["employee_id"].nullable is False
    assert "email" not in GovernmentUser.__table__.columns
    assert GovernmentUser.__table__.columns["password_hash"].nullable is False
