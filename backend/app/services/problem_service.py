"""Problem submission, versioning, tracking and attachments."""

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.problem import Problem, ProblemAttachment, ProblemStatus, ProblemVersion
from app.models.user import User
from app.schemas.problem import ProblemCreate, ProblemUpdate, TrackOut, TrackStage
from app.services import storage


def _auto_review(db: Session, problem: Problem, version_number: int) -> None:
    """Best-effort AI review of a version. Never breaks submission flow."""
    try:
        from app.services.ai import problem_review_service

        version = (
            db.execute(
                select(ProblemVersion)
                .where(
                    ProblemVersion.problem_id == problem.id,
                    ProblemVersion.version_number == version_number,
                )
            )
            .scalars()
            .first()
        )
        if version is not None:
            problem_review_service.run_review(db, problem, version)
    except Exception:
        db.rollback()

TICKET_PREFIX = "JS-PS"
TICKET_DIGITS = 6
MAX_TICKET_ATTEMPTS = 20

# Stage 4 lifecycle view. Only the first two stages can be reached now;
# later stages are shown as pending and are never faked as complete.
# G2 inserts the government-review gate between classification and public
# opening. TrackOut additionally carries the owner-only government_review
# snapshot so the Track page reflects official decisions; public surfaces
# never receive it. Frontend renders stages generically.
TRACK_STAGES = [
    ("submitted", "Submitted"),
    ("ai_review", "AI Review"),
    ("classified", "Classified"),
    ("government_review", "Government Review"),
    ("open", "Open for Solutions"),
    ("collaboration", "Collaboration"),
    ("development", "Development"),
    ("pilot", "Pilot"),
    ("implemented", "Implemented"),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_ticket(db: Session) -> str:
    year = _utcnow().year
    for _ in range(MAX_TICKET_ATTEMPTS):
        ticket = f"{TICKET_PREFIX}-{year}-{secrets.randbelow(10**TICKET_DIGITS):06d}"
        exists = db.execute(select(Problem.id).where(Problem.ticket == ticket)).first()
        if not exists:
            return ticket
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a unique ticket. Please retry.",
    )


def _snapshot(problem: Problem, by: User, note: str | None) -> ProblemVersion:
    return ProblemVersion(
        problem_id=problem.id,
        version_number=problem.current_version,
        title=problem.title,
        category=problem.category,
        location=problem.location,
        description=problem.description,
        affected_group=problem.affected_group,
        severity=problem.severity,
        desired_solution_type=problem.desired_solution_type,
        skills=problem.skills,
        supporting_info=problem.supporting_info,
        submitted_by=by.id,
        revision_note=note,
    )


def create_problem(db: Session, owner: User, data: ProblemCreate) -> Problem:
    for _ in range(3):
        ticket = generate_ticket(db)
        problem = Problem(
            ticket=ticket,
            owner_id=owner.id,
            title=data.title.strip(),
            category=data.category.strip(),
            location=data.location.strip(),
            description=data.description.strip(),
            affected_group=data.affected_group.strip(),
            severity=data.severity,
            desired_solution_type=data.desired_solution_type.strip(),
            skills=(data.skills.strip() or None) if data.skills else None,
            supporting_info=(data.supporting_info.strip() or None)
            if data.supporting_info
            else None,
            status=ProblemStatus.UNDER_REVIEW.value,
            current_version=1,
        )
        db.add(problem)
        db.flush()
        db.add(_snapshot(problem, owner, note="Initial submission"))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue  # ticket collision under concurrency: regenerate
        db.refresh(problem)
        _auto_review(db, problem, 1)
        db.refresh(problem)
        return problem
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not submit the problem. Please retry.",
    )


def get_owned(db: Session, owner: User, ticket: str) -> Problem:
    """Owner-only lookup. Non-owners (and unknown tickets) get 404 so the
    ticket alone never leaks another user's problem (IDOR-safe)."""
    problem = db.execute(select(Problem).where(Problem.ticket == ticket)).scalars().first()
    if problem is None or problem.owner_id != owner.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found."
        )
    return problem


def update_problem(
    db: Session, owner: User, ticket: str, data: ProblemUpdate
) -> Problem:
    problem = get_owned(db, owner, ticket)
    changes = data.model_dump(exclude_unset=True, exclude={"revision_note"})
    if not any(v is not None for v in changes.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No updatable fields provided.",
        )
    for field, value in changes.items():
        if value is None:
            continue
        setattr(problem, field, value.strip() if isinstance(value, str) else value)
    # Ticket never changes on revision. Problems awaiting review go back
    # through AI review for the new version. G2: MORE_INFORMATION_REQUIRED
    # rejoins the same path so a user's answer is AI re-reviewed; approval
    # then recycles the GovernmentReview row into a fresh PENDING cycle.
    needs_review = problem.status in (
        ProblemStatus.UNDER_REVIEW.value,
        ProblemStatus.REVISION_REQUIRED.value,
        ProblemStatus.MORE_INFORMATION_REQUIRED.value,
    )
    was_awaiting_info = (
        problem.status == ProblemStatus.MORE_INFORMATION_REQUIRED.value
    )
    problem.current_version += 1
    db.add(problem)
    db.flush()
    db.add(_snapshot(problem, owner, note=data.revision_note))
    if needs_review:
        problem.status = ProblemStatus.UNDER_REVIEW.value
        db.add(problem)
    db.commit()
    db.refresh(problem)
    if was_awaiting_info:
        from app.services import government_review_service

        government_review_service.record_information_provided(
            db,
            problem,
            response_text=data.revision_note,
        )
        db.refresh(problem)
    if needs_review:
        _auto_review(db, problem, problem.current_version)
        db.refresh(problem)
    return problem


def government_info_for(db: Session, problem: Problem) -> dict | None:
    """Owner-only government-routing snapshot for ProblemOut (G4).

    Returns None when the problem has no GovernmentReview row (legacy or
    pre-routing records). Must only be attached to owner-scoped responses:
    get_owned/submit/update paths. Never to public discovery/detail.
    """
    from app.services import government_review_service

    review = government_review_service.get_for_problem(db, problem.id)
    if review is None:
        return None
    return {
        "review_status": review.status,
        "info_request": review.info_request,
        "pending_since": review.pending_since,
        "sla_due_at": review.sla_due_at,
        "expired": government_review_service.is_expired(review),
        "escalation_flag": review.escalation_flag,
    }


def list_mine(db: Session, owner: User, skip: int = 0, limit: int = 20) -> tuple[list[Problem], int]:
    total = db.execute(
        select(func.count()).select_from(Problem).where(Problem.owner_id == owner.id)
    ).scalar_one()
    rows = (
        db.execute(
            select(Problem)
            .where(Problem.owner_id == owner.id)
            .order_by(Problem.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def history(db: Session, owner: User, ticket: str) -> tuple[Problem, list[ProblemVersion]]:
    problem = get_owned(db, owner, ticket)
    versions = (
        db.execute(
            select(ProblemVersion)
            .where(ProblemVersion.problem_id == problem.id)
            .order_by(ProblemVersion.version_number.asc())
        )
        .scalars()
        .all()
    )
    return problem, list(versions)


def track(db: Session, owner: User, ticket: str) -> TrackOut:
    problem, versions = history(db, owner, ticket)
    submitted_at = versions[0].created_at if versions else problem.created_at
    current_index = {
        ProblemStatus.UNDER_REVIEW.value: 1,
        ProblemStatus.REVISION_REQUIRED.value: 1,
        ProblemStatus.APPROVED.value: 2,
        # G2 government-routing family: all live inside the Government
        # Review stage. GOVERNMENT_ISSUE is a terminal government-side state;
        # it is shown as reached-and-current there, never as public progress.
        ProblemStatus.GOV_REVIEW_PENDING.value: 3,
        ProblemStatus.MORE_INFORMATION_REQUIRED.value: 3,
        ProblemStatus.AUTO_ESCALATED.value: 3,
        ProblemStatus.GOVERNMENT_ISSUE.value: 3,
        ProblemStatus.OPEN.value: 4,
        ProblemStatus.COLLABORATION.value: 5,
        ProblemStatus.IN_DEVELOPMENT.value: 6,
        ProblemStatus.PILOT.value: 7,
        ProblemStatus.IMPLEMENTED.value: 8,
        ProblemStatus.CLOSED.value: 8,
    }.get(problem.status, 1)
    stages = []
    for i, (key, label) in enumerate(TRACK_STAGES):
        if problem.status == ProblemStatus.REJECTED.value:
            state = "done" if i <= 1 else "pending"
        elif i < current_index:
            state = "done"
        elif i == current_index:
            state = "current"
        else:
            state = "pending"
        stages.append(TrackStage(key=key, label=label, state=state))
    return TrackOut(
        ticket=problem.ticket,
        title=problem.title,
        status=problem.status,
        current_version=problem.current_version,
        submitted_at=submitted_at,
        updated_at=problem.updated_at,
        stages=stages,
        government_review=government_info_for(db, problem),
    )


def attachments_of(db: Session, problem: Problem) -> list[ProblemAttachment]:
    return (
        db.execute(
            select(ProblemAttachment)
            .where(ProblemAttachment.problem_id == problem.id)
            .order_by(ProblemAttachment.created_at.asc())
        )
        .scalars()
        .all()
    )


def add_attachment(
    db: Session, owner: User, ticket: str, upload: UploadFile
) -> ProblemAttachment:
    problem = get_owned(db, owner, ticket)
    content = upload.file.read()
    original = storage.sanitize_original_name(upload.filename)
    ext = storage.validate_attachment(original, content, upload.content_type)
    provider = storage.get_provider()
    # Upload first: a storage failure leaves the database untouched.
    stored = provider.save(
        ext=ext, content=content,
        namespace=storage.NAMESPACE_PROBLEM_ATTACHMENTS, ticket=problem.ticket,
    )
    record = ProblemAttachment(
        problem_id=problem.id,
        stored_name=stored,
        original_name=original,
        mime_type=storage.sniff_mime(ext, upload.content_type),
        size_bytes=len(content),
        uploaded_by=owner.id,
    )
    db.add(record)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Never leave an orphan object behind.
        provider.delete(
            namespace=storage.NAMESPACE_PROBLEM_ATTACHMENTS,
            ticket=problem.ticket, stored_name=stored,
        )
        raise
    db.refresh(record)
    return record


def _locate_attachment(
    db: Session, owner: User, ticket: str, attachment_id
) -> tuple[object, ProblemAttachment]:
    from uuid import UUID

    problem = get_owned(db, owner, ticket)
    try:
        aid = attachment_id if isinstance(attachment_id, UUID) else UUID(str(attachment_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found."
        )
    record = db.get(ProblemAttachment, aid)
    if record is None or record.problem_id != problem.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found."
        )
    return problem, record


def get_attachment(
    db: Session, owner: User, ticket: str, attachment_id
) -> tuple[ProblemAttachment, bytes]:
    problem, record = _locate_attachment(db, owner, ticket, attachment_id)
    content = storage.get_provider().read_bytes(
        namespace=storage.NAMESPACE_PROBLEM_ATTACHMENTS,
        ticket=problem.ticket, stored_name=record.stored_name,
    )
    return record, content


def delete_attachment(db: Session, owner: User, ticket: str, attachment_id) -> None:
    problem, record = _locate_attachment(db, owner, ticket, attachment_id)
    storage.get_provider().delete(
        namespace=storage.NAMESPACE_PROBLEM_ATTACHMENTS,
        ticket=problem.ticket, stored_name=record.stored_name,
    )
    db.delete(record)
    db.commit()
