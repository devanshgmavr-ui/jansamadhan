from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.database import get_db
from app.models.problem import Problem
from app.models.user import User
from app.schemas.problem import (
    AttachmentOut,
    DiscoveryItem,
    DiscoveryOut,
    HistoryOut,
    ProblemCreate,
    ProblemListOut,
    ProblemOut,
    ProblemUpdate,
    PublicProblemOut,
    ReviewOut,
    SimilarOut,
    TrackOut,
    TransparencyItem,
    TransparencyOut,
    TransparencyStats,
    VersionOut,
)
from app.services import discovery_service, problem_service
from app.services.ai import problem_review_service

router = APIRouter(prefix="/problems", tags=["problems"])
users_router = APIRouter(prefix="/users", tags=["users"])


def _to_out(db: Session, problem: Problem) -> ProblemOut:
    files = problem_service.attachments_of(db, problem)
    return ProblemOut(
        ticket=problem.ticket,
        title=problem.title,
        category=problem.category,
        location=problem.location,
        description=problem.description,
        affected_group=problem.affected_group,
        severity=problem.severity,
        desired_solution_type=problem.desired_solution_type,
        skills=problem.skills,
        supporting_info=problem.supporting_info,
        status=problem.status,
        current_version=problem.current_version,
        created_at=problem.created_at,
        updated_at=problem.updated_at,
        attachments=[
            AttachmentOut(
                id=f.id,
                original_name=f.original_name,
                mime_type=f.mime_type,
                size_bytes=f.size_bytes,
                created_at=f.created_at,
            )
            for f in files
        ],
        government_review=problem_service.government_info_for(db, problem),
    )


@router.post("", response_model=ProblemOut, status_code=201)
def submit_problem(
    data: ProblemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem = problem_service.create_problem(db, user, data)
    return _to_out(db, problem)


@users_router.get("/me/problems")
def my_problems(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows, total = problem_service.list_mine(db, user, skip=skip, limit=limit)
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [
            ProblemListOut(
                ticket=p.ticket,
                title=p.title,
                category=p.category,
                status=p.status,
                current_version=p.current_version,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in rows
        ],
    }


@router.get("/transparency", response_model=TransparencyOut)
def transparency_listing(
    resolution: str | None = Query(default=None, max_length=20),
    category: str | None = Query(default=None, max_length=100),
    severity: str | None = Query(default=None, max_length=30),
    location: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=30),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1, le=1000),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Public transparency dashboard feed (Phase 2). No authentication.
    Only government-approved complaints (public challenges + government
    issues); rejected/pending/private complaints never appear. Newest
    approval first. Must stay registered before /{ticket}."""
    items, total = discovery_service.transparency_search(
        db,
        resolution=resolution,
        category=category,
        severity=severity,
        location=location,
        status=status,
        q=q,
        page=page,
        limit=limit,
    )
    pages = (total + limit - 1) // limit if total else 0
    return TransparencyOut(
        total=total, page=page, limit=limit, pages=pages,
        items=[TransparencyItem(**item) for item in items],
    )


@router.get("/transparency/stats", response_model=TransparencyStats)
def transparency_statistics(db: Session = Depends(get_db)):
    """Dynamic dashboard counters (Phase 2). Single grouped count query.
    Must stay registered before /{ticket}."""
    return TransparencyStats(**discovery_service.transparency_stats(db))


@router.get("/{ticket}", response_model=ProblemOut)
def get_problem(
    ticket: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _to_out(db, problem_service.get_owned(db, user, ticket))


@router.put("/{ticket}", response_model=ProblemOut)
def revise_problem(
    ticket: str,
    data: ProblemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem = problem_service.update_problem(db, user, ticket, data)
    return _to_out(db, problem)


@router.get("/{ticket}/history", response_model=HistoryOut)
def problem_history(
    ticket: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem, versions = problem_service.history(db, user, ticket)
    return HistoryOut(
        ticket=problem.ticket,
        current_version=problem.current_version,
        versions=[
            VersionOut(
                version_number=v.version_number,
                title=v.title,
                category=v.category,
                location=v.location,
                description=v.description,
                affected_group=v.affected_group,
                severity=v.severity,
                desired_solution_type=v.desired_solution_type,
                skills=v.skills,
                supporting_info=v.supporting_info,
                revision_note=v.revision_note,
                created_at=v.created_at,
            )
            for v in versions
        ],
    )


@router.get("/{ticket}/track", response_model=TrackOut)
def track_problem(
    ticket: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return problem_service.track(db, user, ticket)


@router.post("/{ticket}/attachments", response_model=AttachmentOut, status_code=201)
def upload_attachment(
    ticket: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    record = problem_service.add_attachment(db, user, ticket, file)
    return AttachmentOut(
        id=record.id,
        original_name=record.original_name,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        created_at=record.created_at,
    )


@router.get("/{ticket}/attachments/{attachment_id}/download")
def download_attachment(
    ticket: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    record, content = problem_service.get_attachment(db, user, ticket, attachment_id)
    return Response(
        content=content,
        media_type=record.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{record.original_name}"'
        },
    )


@router.delete("/{ticket}/attachments/{attachment_id}", status_code=204)
def delete_attachment(
    ticket: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem_service.delete_attachment(db, user, ticket, attachment_id)
    return None


def _review_out(db: Session, review) -> ReviewOut:
    import json as _json

    def _list(raw) -> list:
        try:
            val = _json.loads(raw) if raw else []
            return val if isinstance(val, list) else []
        except Exception:
            return []

    similar = (
        db.query(problem_review_service.AIReviewSimilar)
        .filter(problem_review_service.AIReviewSimilar.review_id == review.id)
        .all()
    )
    tickets = {}
    if similar:
        rows = (
            db.query(problem_review_service.Problem.ticket, problem_review_service.Problem.id)
            .filter(
                problem_review_service.Problem.id.in_([s.problem_id for s in similar])
            )
            .all()
        )
        tickets = {pid: t for t, pid in rows}
    version_number = (
        db.query(problem_review_service.ProblemVersion.version_number)
        .filter(problem_review_service.ProblemVersion.id == review.version_id)
        .scalar()
    )
    return ReviewOut(
        review_number=review.review_number,
        version_number=version_number or 0,
        provider=review.provider,
        model=review.model,
        status=review.status,
        decision=review.decision,
        reason=review.reason,
        missing_info=_list(review.missing_info),
        understandable=review.understandable,
        sufficient_info=review.sufficient_info,
        solvable=review.solvable,
        duplicate_status=review.duplicate_status,
        problem_type=review.problem_type,
        affected_group=review.affected_group,
        geo_context=review.geo_context,
        category=review.category,
        scope=review.scope,
        tech_areas=_list(review.tech_areas),
        tags=_list(review.tags_suggested),
        similar=[
            SimilarOut(ticket=tickets.get(s.problem_id, "?"), relation=s.relation)
            for s in similar
        ],
        error_detail=review.error_detail,
        created_at=review.created_at,
    )


@router.post("/{ticket}/review", response_model=ReviewOut)
def request_review(
    ticket: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Owner-only. Idempotent per version: returns the existing COMPLETED
    review when the current version was already reviewed."""
    from sqlalchemy import select as _select

    problem = problem_service.get_owned(db, user, ticket)
    existing = (
        db.query(problem_review_service.AIReview)
        .filter(
            problem_review_service.AIReview.problem_id == problem.id,
            problem_review_service.AIReview.status == "COMPLETED",
        )
        .order_by(problem_review_service.AIReview.review_number.desc())
        .first()
    )
    if existing is not None:
        current_version_id = db.execute(
            _select(problem_review_service.ProblemVersion.id).where(
                problem_review_service.ProblemVersion.problem_id == problem.id,
                problem_review_service.ProblemVersion.version_number
                == problem.current_version,
            )
        ).scalar_one_or_none()
        if current_version_id is not None and existing.version_id == current_version_id:
            return _review_out(db, existing)
    version = db.execute(
        _select(problem_review_service.ProblemVersion).where(
            problem_review_service.ProblemVersion.problem_id == problem.id,
            problem_review_service.ProblemVersion.version_number
            == problem.current_version,
        )
    ).scalars().first()
    review = problem_review_service.run_review(db, problem, version)
    return _review_out(db, review)


@router.get("/{ticket}/reviews", response_model=list[ReviewOut])
def list_reviews(
    ticket: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem = problem_service.get_owned(db, user, ticket)
    rows = (
        db.query(problem_review_service.AIReview)
        .filter(problem_review_service.AIReview.problem_id == problem.id)
        .order_by(problem_review_service.AIReview.review_number.asc())
        .all()
    )
    return [_review_out(db, r) for r in rows]


@router.get("", response_model=DiscoveryOut)
def discover_problems(
    q: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=100),
    location: str | None = Query(default=None, max_length=200),
    area: str | None = Query(default=None, max_length=30),
    scope: str | None = Query(default=None, max_length=30),
    affected_group: str | None = Query(default=None, max_length=120),
    technology: str | None = Query(default=None, max_length=60),
    problem_type: str | None = Query(default=None, max_length=60),
    tag: str | None = Query(default=None, max_length=40),
    status: str | None = Query(default=None, max_length=30),
    sort: str = Query(default="newest", pattern="^(newest|updated|relevance)$"),
    page: int = Query(default=1, ge=1, le=1000),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Public discovery. No authentication required. Only public problems."""
    import json as _json

    rows, total = discovery_service.search_problems(
        db,
        q=q,
        category=category,
        location=location,
        area=area,
        scope=scope,
        affected_group=affected_group,
        technology=technology,
        problem_type=problem_type,
        tag=tag,
        status=status,
        sort=sort,
        page=page,
        limit=limit,
    )
    ids = [p.id for p in rows]
    tags = discovery_service.tags_for(db, ids)
    classes = discovery_service.classification_for(db, ids)
    items = []
    for p in rows:
        c = classes.get(p.id)
        items.append(
            DiscoveryItem(
                ticket=p.ticket,
                title=p.title,
                category=p.category,
                location=p.location,
                affected_group=p.affected_group,
                status=p.status,
                area=c.area if c else None,
                scope=c.scope if c else None,
                problem_type=c.problem_type if c else None,
                tags=tags.get(p.id, []),
                created_at=p.created_at,
            )
        )
    pages = (total + limit - 1) // limit if total else 0
    return DiscoveryOut(total=total, page=page, limit=limit, pages=pages, items=items)


@router.get("/{ticket}/public", response_model=PublicProblemOut)
def get_public_problem(ticket: str, db: Session = Depends(get_db)):
    """Public detail. No authentication required. Private problems get 404."""
    import json as _json

    problem = discovery_service.get_public(db, ticket)
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found."
        )
    tags = discovery_service.tags_for(db, [problem.id]).get(problem.id, [])
    classes = discovery_service.classification_for(db, [problem.id])
    c = classes.get(problem.id)
    techs = []
    if c and c.tech_areas:
        try:
            techs = _json.loads(c.tech_areas) or []
        except Exception:
            techs = []
    return PublicProblemOut(
        ticket=problem.ticket,
        title=problem.title,
        description=problem.description,
        category=problem.category,
        location=problem.location,
        affected_group=problem.affected_group,
        severity=problem.severity,
        desired_solution_type=problem.desired_solution_type,
        skills=problem.skills,
        status=problem.status,
        area=c.area if c else None,
        scope=c.scope if c else None,
        problem_type=c.problem_type if c else None,
        tech_areas=techs,
        tags=tags,
        created_at=problem.created_at,
        updated_at=problem.updated_at,
    )
