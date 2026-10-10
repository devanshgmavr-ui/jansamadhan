"""Administrator analytics (Phase 4, Part B). Bulk grouped queries only;
no N+1. Read-only."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.execution import ImplementationUpdate
from app.models.government import GovernmentReview
from app.models.problem import Problem, ProblemStatus
from app.models.solution import Solution
from app.models.user import User


def _status_counts(db: Session) -> dict:
    rows = db.execute(
        select(Problem.status, func.count()).group_by(Problem.status)
    ).all()
    return {s: n for s, n in rows}


def overview(db: Session) -> dict:
    counts = _status_counts(db)
    total = sum(counts.values())
    pending_ai = counts.get(ProblemStatus.UNDER_REVIEW.value, 0) + counts.get(
        ProblemStatus.REVISION_REQUIRED.value, 0)
    gov_pending = counts.get(ProblemStatus.GOV_REVIEW_PENDING.value, 0) + counts.get(
        ProblemStatus.MORE_INFORMATION_REQUIRED.value, 0) + counts.get(
        ProblemStatus.AUTO_ESCALATED.value, 0)
    challenges = sum(counts.get(s, 0) for s in (
        ProblemStatus.OPEN.value, ProblemStatus.COLLABORATION.value,
        ProblemStatus.IN_DEVELOPMENT.value, ProblemStatus.PILOT.value,
        ProblemStatus.IMPLEMENTED.value))
    issues = counts.get(ProblemStatus.GOVERNMENT_ISSUE.value, 0)
    rejected = counts.get(ProblemStatus.REJECTED.value, 0)
    completed = counts.get(ProblemStatus.IMPLEMENTED.value, 0)
    solutions_submitted = db.execute(
        select(func.count()).select_from(Solution)).scalar_one()
    solutions_selected = db.execute(
        select(func.count()).select_from(Solution).where(
            Solution.is_selected.is_(True))).scalar_one()
    active_impl = db.execute(
        select(func.count(func.distinct(
            ImplementationUpdate.problem_id)))).scalar_one()
    avg_seconds = db.execute(
        select(func.avg(func.extract(
            "epoch", GovernmentReview.decided_at - GovernmentReview.pending_since,
        ))).where(GovernmentReview.decided_at.is_not(None))).scalar()
    month_rows = db.execute(
        select(func.date_trunc("month", Problem.created_at).label("month"),
               func.count())
        .group_by("month").order_by("month").limit(12)).all()
    cat_rows = db.execute(
        select(Problem.category, func.count()).group_by(Problem.category)
        .order_by(func.count().desc()).limit(10)).all()
    loc_rows = db.execute(
        select(Problem.location, func.count()).where(Problem.location.is_not(None))
        .group_by(Problem.location).order_by(func.count().desc()).limit(10)).all()
    org_rows = db.execute(
        select(User.account_type, func.count()).join(
            Solution, Solution.submitter_id == User.id)
        .group_by(User.account_type)).all()
    solved_rows = db.execute(
        select(Problem.category, func.count())
        .where(Problem.status == ProblemStatus.IMPLEMENTED.value)
        .group_by(Problem.category)
        .order_by(func.count().desc()).limit(10)).all()
    return {
        "total_complaints": total,
        "pending_ai_review": pending_ai,
        "government_review_pending": gov_pending,
        "public_challenges": challenges,
        "government_issues": issues,
        "solutions_submitted": solutions_submitted,
        "solutions_selected": solutions_selected,
        "implementations_active": active_impl,
        "completed_projects": completed,
        "rejected_complaints": rejected,
        "average_resolution_seconds": float(avg_seconds) if avg_seconds else None,
        "monthly_trend": [
            {"month": m.isoformat() if hasattr(m, "isoformat") else str(m), "count": n}
            for m, n in month_rows],
        "top_categories": [{"category": c, "count": n} for c, n in cat_rows],
        "top_locations": [{"location": loc, "count": n} for loc, n in loc_rows],
        "solver_account_types": [{"account_type": str(a), "count": n} for a, n in org_rows],
        "most_solved_categories": [{"category": c, "count": n} for c, n in solved_rows],
    }
