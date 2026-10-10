"""Government-issue implementation tracking (Phase 3).

Officials append progress updates (closed stage vocabulary) with optional
documents/images. Citizens read the timeline through the public
transparency detail endpoint. Updates are append-only.
"""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.execution import (
    ImplementationAttachment,
    ImplementationStage,
    ImplementationUpdate,
)
from app.models.problem import Problem
from app.services import storage

STAGES = tuple(s.value for s in ImplementationStage)


def _announce_implementation(db: Session, problem: Problem,
                             update: ImplementationUpdate,
                             first: bool) -> None:
    """Phase 4: audit + owner email on implementation start (first update)
    and on completion (COMPLETED/CLOSED stage)."""
    from app.services import government_review_service, notification_service

    action = None
    if first:
        action = "IMPLEMENTATION_STARTED"
    if update.stage in ("COMPLETED", "CLOSED"):
        action = "IMPLEMENTATION_COMPLETED"
    if action is None:
        return
    audit = government_review_service.record_event(
        db, problem, action=action, actor_id=update.created_by,
        actor_type="GOVERNMENT_OFFICIAL", reason=update.title,
    )
    db.commit()
    notification_service.queue_for_audit(db, problem=problem, audit=audit)
    db.commit()
    try:
        notification_service.deliver_for_problem(db, problem.id)
    except Exception:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "implementation notification flush failed ticket=%s",
            problem.ticket,
        )


def _issue_or_404(db: Session, problem_ticket: str) -> Problem:
    problem = db.execute(
        select(Problem).where(Problem.ticket == problem_ticket)
    ).scalars().first()
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found."
        )
    if problem.status != "GOVERNMENT_ISSUE":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Implementation tracking applies to government issues only.",
        )
    return problem


def create_update(
    db: Session,
    official,
    problem_ticket: str,
    *,
    stage: str,
    title: str,
    description: str | None,
    files: list | None = None,
) -> ImplementationUpdate:
    problem = _issue_or_404(db, problem_ticket)
    if stage not in STAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown stage. Allowed: {sorted(STAGES)}.",
        )
    update = ImplementationUpdate(
        problem_id=problem.id,
        stage=stage,
        title=title.strip(),
        description=(description.strip() or None) if description else None,
        created_by=official.id,
    )
    db.add(update)
    db.flush()
    first = (
        db.execute(
            select(func.count())
            .select_from(ImplementationUpdate)
            .where(ImplementationUpdate.problem_id == problem.id)
        ).scalar_one()
        == 1
    )
    provider = storage.get_solution_provider()
    saved: list[str] = []
    try:
        for upload in files or []:
            content = upload.file.read()
            original = storage.sanitize_original_name(upload.filename)
            ext = storage.validate_attachment(
                original, content, upload.content_type, db
            )
            stored = provider.save(
                ext=ext, content=content,
                namespace=storage.NAMESPACE_IMPLEMENTATION_ATTACHMENTS,
                ticket=problem.ticket,
            )
            saved.append(stored)
            db.add(ImplementationAttachment(
                update_id=update.id,
                stored_name=stored,
                original_name=original,
                mime_type=storage.sniff_mime(ext, upload.content_type),
                size_bytes=len(content),
            ))
        db.commit()
    except Exception:
        db.rollback()
        for stored in saved:
            try:
                provider.delete(
                    namespace=storage.NAMESPACE_IMPLEMENTATION_ATTACHMENTS,
                    ticket=problem.ticket, stored_name=stored,
                )
            except Exception:
                pass
        raise
    db.refresh(update)
    _announce_implementation(db, problem, update, first=first)
    return update


def list_updates(db: Session, problem_id) -> list[ImplementationUpdate]:
    return (
        db.execute(
            select(ImplementationUpdate)
            .where(ImplementationUpdate.problem_id == problem_id)
            .order_by(ImplementationUpdate.created_at.asc())
        )
        .scalars()
        .all()
    )


def attachments_for(db: Session, update_ids: list) -> dict:
    """Batched attachments map for a page of updates (no N+1)."""
    if not update_ids:
        return {}
    rows = (
        db.execute(
            select(ImplementationAttachment)
            .where(ImplementationAttachment.update_id.in_(update_ids))
            .order_by(ImplementationAttachment.created_at.asc())
        )
        .scalars()
        .all()
    )
    out: dict = {}
    for row in rows:
        out.setdefault(row.update_id, []).append(row)
    return out


def read_attachment(db: Session, attachment_id) -> tuple:
    from uuid import UUID

    try:
        aid = attachment_id if isinstance(attachment_id, UUID) else UUID(str(attachment_id))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found."
        )
    record = db.get(ImplementationAttachment, aid)
    if record is None or record.update_id != update_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found."
        )
    update = db.get(ImplementationUpdate, update_id)
    problem = db.get(Problem, update.problem_id) if update else None
    ticket = problem.ticket if problem else "?"
    content = storage.get_solution_provider().read_bytes(
        namespace=storage.NAMESPACE_IMPLEMENTATION_ATTACHMENTS,
        ticket=ticket, stored_name=record.stored_name,
    )
    return record, content


def count_for_problems(db: Session, problem_ids: list) -> dict:
    rows = db.execute(
        select(ImplementationUpdate.problem_id, func.count())
        .where(ImplementationUpdate.problem_id.in_(problem_ids))
        .group_by(ImplementationUpdate.problem_id)
    ).all() if problem_ids else []
    return {pid: n for pid, n in rows}
