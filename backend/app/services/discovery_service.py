"""Public problem discovery: server-side search, filters, pagination.

Only problems in public lifecycle states are ever returned. No AI
recommendation is involved; ordering is newest/updated/text-match only."""

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.ai_review import ProblemClassification, ProblemTag, Tag
from app.models.government import GovernmentAction, GovernmentReview
from app.models.problem import Problem, ProblemStatus

PUBLIC_STATUSES = (
    ProblemStatus.OPEN.value,
    ProblemStatus.COLLABORATION.value,
    ProblemStatus.IN_DEVELOPMENT.value,
    ProblemStatus.PILOT.value,
    ProblemStatus.IMPLEMENTED.value,
)

# Phase 2 transparency: every government-approved complaint is publicly
# listed. Government issues stay out of solution discovery (see
# PUBLIC_STATUSES) but appear here for monitoring, without solution flows.
TRANSPARENCY_STATUSES = PUBLIC_STATUSES + (
    ProblemStatus.GOVERNMENT_ISSUE.value,
)

TRANSPARENCY_RESOLUTIONS = ("PUBLIC", "GOVERNMENT")

MAX_LIMIT = 50


def _base_query():
    return select(Problem).where(Problem.status.in_(PUBLIC_STATUSES))


def search_problems(
    db: Session,
    *,
    q: str | None = None,
    category: str | None = None,
    location: str | None = None,
    area: str | None = None,
    scope: str | None = None,
    affected_group: str | None = None,
    technology: str | None = None,
    problem_type: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    sort: str = "newest",
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Problem], int]:
    if status is not None and status not in PUBLIC_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only public problem statuses can be listed.",
        )
    stmt = _base_query()
    if status:
        stmt = stmt.where(Problem.status == status)
    if category:
        stmt = stmt.where(Problem.category.ilike(f"%{category.strip()}%"))
    if location:
        stmt = stmt.where(Problem.location.ilike(f"%{location.strip()}%"))
    if affected_group:
        stmt = stmt.where(Problem.affected_group.ilike(f"%{affected_group.strip()}%"))

    need_class = any([area, scope, technology, problem_type])
    if need_class:
        stmt = stmt.join(
            ProblemClassification,
            ProblemClassification.problem_id == Problem.id,
        )
        if area:
            stmt = stmt.where(ProblemClassification.area == area.strip())
        if scope:
            stmt = stmt.where(ProblemClassification.scope == scope.strip())
        if problem_type:
            stmt = stmt.where(
                ProblemClassification.problem_type.ilike(f"%{problem_type.strip()}%")
            )
        if technology:
            stmt = stmt.where(
                ProblemClassification.tech_areas.ilike(f"%{technology.strip()}%")
            )
    if tag:
        stmt = (
            stmt.join(ProblemTag, ProblemTag.problem_id == Problem.id)
            .join(Tag, Tag.id == ProblemTag.tag_id)
            .where(Tag.name == tag.strip().lower())
        )
    if q:
        like = f"%{q.strip()}%"
        tag_ids = select(ProblemTag.problem_id).join(Tag).where(Tag.name.ilike(like))
        stmt = stmt.where(
            or_(
                Problem.title.ilike(like),
                Problem.description.ilike(like),
                Problem.category.ilike(like),
                Problem.location.ilike(like),
                Problem.affected_group.ilike(like),
                Problem.id.in_(tag_ids),
            )
        )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar_one()
    if sort == "updated":
        stmt = stmt.order_by(Problem.updated_at.desc())
    elif sort == "relevance" and q:
        like = f"%{q.strip()}%"
        stmt = stmt.order_by(
            Problem.title.ilike(like).desc(), Problem.created_at.desc()
        )
    else:
        stmt = stmt.order_by(Problem.created_at.desc())
    limit = min(max(limit, 1), MAX_LIMIT)
    page = max(page, 1)
    rows = db.execute(stmt.offset((page - 1) * limit).limit(limit)).scalars().all()
    return list(rows), total


def tags_for(db: Session, problem_ids: list) -> dict:
    """Single-query tag map for a page of problems (no N+1)."""
    if not problem_ids:
        return {}
    rows = (
        db.execute(
            select(ProblemTag.problem_id, Tag.name)
            .join(Tag, Tag.id == ProblemTag.tag_id)
            .where(ProblemTag.problem_id.in_(problem_ids))
            .order_by(Tag.name.asc())
        )
        .all()
    )
    out: dict = {}
    for pid, name in rows:
        out.setdefault(pid, []).append(name)
    return out


def classification_for(db: Session, problem_ids: list) -> dict:
    if not problem_ids:
        return {}
    rows = (
        db.execute(
            select(ProblemClassification).where(
                ProblemClassification.problem_id.in_(problem_ids)
            )
        )
        .scalars()
        .all()
    )
    return {c.problem_id: c for c in rows}


def get_public(db: Session, ticket: str) -> Problem | None:
    problem = db.execute(
        select(Problem).where(Problem.ticket == ticket)
    ).scalars().first()
    if problem is None or problem.status not in PUBLIC_STATUSES:
        return None
    return problem


def transparency_search(
    db: Session,
    *,
    resolution: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    location: str | None = None,
    status: str | None = None,
    q: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict], int]:
    """Public transparency listing: every approved complaint (public
    challenges + government issues). Only decided, public-safe fields are
    returned; rejected/pending/private complaints never appear. One data
    query + one batched reason query (no N+1). Newest approval first."""
    from app.services import government_review_service

    if resolution is not None and resolution not in TRANSPARENCY_RESOLUTIONS:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resolution must be PUBLIC or GOVERNMENT.",
        )
    if status is not None and status not in TRANSPARENCY_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only approved problem statuses can be listed.",
        )
    stmt = (
        select(Problem, GovernmentReview.decided_at)
        .outerjoin(
            GovernmentReview,
            GovernmentReview.problem_id == Problem.id,
        )
        .where(Problem.status.in_(TRANSPARENCY_STATUSES))
    )
    if resolution == "PUBLIC":
        stmt = stmt.where(Problem.status.in_(PUBLIC_STATUSES))
    elif resolution == "GOVERNMENT":
        stmt = stmt.where(
            Problem.status == ProblemStatus.GOVERNMENT_ISSUE.value
        )
    if status:
        stmt = stmt.where(Problem.status == status)
    if category:
        stmt = stmt.where(Problem.category.ilike(f"%{category.strip()}%"))
    if severity:
        stmt = stmt.where(Problem.severity.ilike(f"%{severity.strip()}%"))
    if location:
        stmt = stmt.where(Problem.location.ilike(f"%{location.strip()}%"))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Problem.title.ilike(like),
                Problem.description.ilike(like),
                Problem.category.ilike(like),
                Problem.location.ilike(like),
            )
        )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar_one()
    stmt = stmt.order_by(
        GovernmentReview.decided_at.desc().nulls_last(),
        Problem.created_at.desc(),
    )
    limit = min(max(limit, 1), MAX_LIMIT)
    page = max(page, 1)
    pairs = db.execute(stmt.offset((page - 1) * limit).limit(limit)).all()
    ids = [p.id for p, _ in pairs]
    reasons: dict = {}
    if ids:
        # new_status stores review statuses; only terminal decisions carry
        # the public remark.
        terminal = ("ASSIGNED_TO_PUBLIC", "GOVERNMENT_ISSUE")
        for action in (
            db.execute(
                select(GovernmentAction)
                .where(
                    GovernmentAction.problem_id.in_(ids),
                    GovernmentAction.new_status.in_(terminal),
                )
                .order_by(GovernmentAction.created_at.desc())
            )
            .scalars()
            .all()
        ):
            if action.problem_id not in reasons and (action.reason or "").strip():
                reasons[action.problem_id] = action.reason
    items = []
    for problem, decided_at in pairs:
        items.append(
            {
                "ticket": problem.ticket,
                "title": problem.title,
                "category": problem.category,
                "location": problem.location,
                "severity": problem.severity,
                "status": problem.status,
                "decided_at": decided_at,
                "resolution_type": (
                    "PUBLIC"
                    if problem.status in PUBLIC_STATUSES
                    else government_review_service.resolution_type_for(
                        problem.status
                    )
                ),
                "decision_reason": reasons.get(problem.id),
                "created_at": problem.created_at,
            }
        )
    return items, total


def transparency_stats(db: Session) -> dict:
    """Single grouped count over transparency statuses (no N+1). Resolved
    means IMPLEMENTED; open challenges means status OPEN."""
    rows = db.execute(
        select(Problem.status, func.count())
        .where(Problem.status.in_(TRANSPARENCY_STATUSES))
        .group_by(Problem.status)
    ).all()
    counts = {status: n for status, n in rows}
    challenges = sum(counts.get(s, 0) for s in PUBLIC_STATUSES)
    issues = counts.get(ProblemStatus.GOVERNMENT_ISSUE.value, 0)
    return {
        "total_approved": challenges + issues,
        "challenges": challenges,
        "issues": issues,
        "open_challenges": counts.get(ProblemStatus.OPEN.value, 0),
        "resolved": counts.get(ProblemStatus.IMPLEMENTED.value, 0),
    }
