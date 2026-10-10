"""Orchestrates AI review runs: provider call, validated persistence,
decision application. Failures never corrupt problem state."""

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_review import (
    AIReview,
    AIReviewSimilar,
    ProblemClassification,
    ProblemTag,
    ReviewDecision,
    Tag,
)
from app.models.problem import Problem, ProblemStatus, ProblemVersion
from app.services.ai.provider import AIProviderError, AIReviewInput


def _candidates(db: Session, problem: Problem, limit: int = 30) -> list[dict]:
    rows = (
        db.execute(
            select(Problem.ticket, Problem.title, Problem.category, Problem.description)
            .where(Problem.id != problem.id)
            .where(Problem.status.in_([
                ProblemStatus.OPEN.value,
                ProblemStatus.UNDER_REVIEW.value,
                # G2: unresolved government-routing states still describe real
                # problems, so similar pending work is detected. Internal-only:
                # candidate membership never makes a problem publicly visible.
                ProblemStatus.GOV_REVIEW_PENDING.value,
                ProblemStatus.MORE_INFORMATION_REQUIRED.value,
            ]))
            .order_by(Problem.created_at.desc())
            .limit(limit)
        )
        .all()
    )
    return [
        {"ticket": t, "title": ti, "category": c, "description": (d or "")[:2000]}
        for t, ti, c, d in rows
    ]


def _apply_approved(db: Session, problem: Problem, version: ProblemVersion, out) -> None:
    from app.services import government_review_service

    db.query(ProblemTag).filter(ProblemTag.problem_id == problem.id).delete()
    db.query(ProblemClassification).filter(
        ProblemClassification.problem_id == problem.id
    ).delete()
    db.add(
        ProblemClassification(
            problem_id=problem.id,
            version_id=version.id,
            category=out.checks.category,
            area=out.checks.geo_context.value,
            scope=out.scope.value,
            affected_group=out.checks.affected_group,
            problem_type=out.checks.problem_type,
            tech_areas=json.dumps(out.tech_areas),
        )
    )
    for raw_tag in out.checks.tags:
        name = raw_tag.strip().lower()[:40]
        if len(name) < 2:
            continue
        tag = db.execute(select(Tag).where(Tag.name == name)).scalars().first()
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        db.add(ProblemTag(problem_id=problem.id, tag_id=tag.id))
    # G2: AI approval means "eligible for government routing review", never
    # public publication. This creates (or recycles) the PENDING
    # GovernmentReview with a fresh 24h window, mirrors Problem.status, and
    # records the audit event. commit=False joins run_review's transaction so
    # the AI review row, classification, review state and audit event commit
    # atomically.
    government_review_service.ensure_pending_review(db, problem, commit=False)


def run_review(db: Session, problem: Problem, version: ProblemVersion,
               provider_override=None) -> AIReview:
    from app.services.ai.providers.openrouter import resolve_provider

    if provider_override is not None:
        provider, provider_name, model_name = provider_override, "test-stub", "test-stub"
    else:
        provider, provider_name, model_name = resolve_provider(db)
    number = (
        db.execute(
            select(func.count())
            .select_from(AIReview)
            .where(AIReview.problem_id == problem.id)
        ).scalar_one()
        + 1
    )
    payload = AIReviewInput(
        ticket=problem.ticket,
        version_number=version.version_number,
        title=version.title,
        category=version.category,
        location=version.location,
        description=version.description,
        affected_group=version.affected_group,
        severity=version.severity,
        desired_solution_type=version.desired_solution_type,
        skills=version.skills,
        supporting_info=version.supporting_info,
        candidates=_candidates(db, problem),
    )
    try:
        out = provider.review(payload)
    except AIProviderError as exc:
        review = AIReview(
            problem_id=problem.id,
            version_id=version.id,
            review_number=number,
            provider=provider_name,
            model=model_name,
            status="FAILED",
            error_detail=str(exc)[:500],
        )
        db.add(review)
        db.commit()
        db.refresh(review)
        return review

    review = AIReview(
        problem_id=problem.id,
        version_id=version.id,
        review_number=number,
        provider=provider_name,
        model=model_name,
        status="COMPLETED",
        decision=out.decision.value,
        reason=out.reason,
        missing_info=json.dumps(out.missing_info),
        understandable=out.checks.understandable,
        sufficient_info=out.checks.sufficient_info,
        solvable=out.checks.solvable,
        duplicate_status=out.checks.duplicate_status.value,
        problem_type=out.checks.problem_type,
        affected_group=out.checks.affected_group,
        geo_context=out.checks.geo_context.value,
        category=out.checks.category,
        scope=out.scope.value,
        tech_areas=json.dumps(out.tech_areas),
        tags_suggested=json.dumps(out.checks.tags),
    )
    db.add(review)
    db.flush()
    ticket_to_id = {
        t: i
        for t, i in db.execute(
            select(Problem.ticket, Problem.id)
        ).all()
    }
    for ref in out.similar:
        pid = ticket_to_id.get(ref.ticket)
        if pid is None:
            continue
        db.add(
            AIReviewSimilar(
                review_id=review.id,
                problem_id=pid,
                relation=ref.relation.value,
                score=0.0,
            )
        )
    if out.decision.value == ReviewDecision.APPROVED.value:
        _apply_approved(db, problem, version, out)
    elif out.decision.value == ReviewDecision.NEEDS_INFORMATION.value:
        problem.status = ProblemStatus.REVISION_REQUIRED.value
        db.add(problem)
    else:
        problem.status = ProblemStatus.REJECTED.value
        db.add(problem)
    db.commit()
    db.refresh(review)
    # G7: flush any notification intent queued inside this transaction
    # (e.g. the pending-review email from an approval that joined this
    # commit). Delivery failures only record FAILED; the review stands.
    try:
        from app.services import notification_service

        notification_service.deliver_for_problem(db, problem.id)
    except Exception:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "notification flush failed ticket=%s", problem.ticket
        )
    return review


def latest_review(db: Session, problem: Problem) -> AIReview | None:
    return (
        db.execute(
            select(AIReview)
            .where(AIReview.problem_id == problem.id)
            .order_by(AIReview.review_number.desc())
        )
        .scalars()
        .first()
    )
