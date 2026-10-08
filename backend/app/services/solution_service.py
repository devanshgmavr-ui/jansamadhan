"""Solution submission, ownership enforcement, lifecycle and visibility."""

import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.problem import Problem
from app.models.solution import SOLUTION_TRANSITIONS, Solution, SolutionStatus
from app.models.user import User
from app.schemas.solution import SolutionUpdate
from app.services import storage
from app.services.discovery_service import PUBLIC_STATUSES

TICKET_PREFIX = "JS-SOL"

SOLUTION_TRACK_STAGES = [
    ("submitted", "Submitted"),
    ("initial_review", "Initial Review"),
    ("under_evaluation", "Under Evaluation"),
    ("shortlisted", "Shortlisted"),
    ("collaboration_formed", "Collaboration Formed"),
    ("development", "Development"),
    ("prototype", "Prototype"),
    ("pilot", "Pilot"),
    ("implemented", "Implemented"),
    ("impact_recorded", "Impact Recorded"),
]

_STAGE_INDEX = {s.value: i for i, (s, _) in enumerate(
    [(SolutionStatus.SUBMITTED, ""), (SolutionStatus.INITIAL_REVIEW, ""),
     (SolutionStatus.UNDER_EVALUATION, ""), (SolutionStatus.SHORTLISTED, ""),
     (SolutionStatus.COLLABORATION_FORMED, ""), (SolutionStatus.DEVELOPMENT, ""),
     (SolutionStatus.PROTOTYPE, ""), (SolutionStatus.PILOT, ""),
     (SolutionStatus.IMPLEMENTED, ""), (SolutionStatus.IMPACT_RECORDED, "")]
)}


def _utcnow_year() -> int:
    return datetime.now(timezone.utc).year


def generate_solution_ticket(db: Session) -> str:
    year = _utcnow_year()
    for _ in range(20):
        ticket = f"{TICKET_PREFIX}-{year}-{secrets.randbelow(1000000):06d}"
        if not db.execute(select(Solution.id).where(Solution.ticket == ticket)).first():
            return ticket
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not generate a unique ticket. Please retry.",
    )


def _problem_or_404(db: Session, problem_ticket: str) -> Problem:
    problem = db.execute(
        select(Problem).where(Problem.ticket == problem_ticket)
    ).scalars().first()
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found."
        )
    return problem


def submit_solution(
    db: Session,
    submitter: User,
    problem_ticket: str,
    *,
    title: str,
    short_description: str,
    skills: str | None,
    expected_impact: str,
    contributors: str | None,
    estimated_resources: str | None,
    pdf: UploadFile,
) -> Solution:
    problem = _problem_or_404(db, problem_ticket)
    # CRITICAL OWNERSHIP RULE: backend-enforced, never frontend-only.
    if problem.owner_id == submitter.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Problem owners cannot submit solutions to their own problem.",
        )
    if problem.status not in PUBLIC_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This problem is not open for solutions.",
        )
    content = pdf.file.read()
    original = storage.sanitize_original_name(pdf.filename)
    ext = storage.validate_solution_pdf(original, content)
    for _ in range(3):
        ticket = generate_solution_ticket(db)
        # Upload first: a storage failure leaves the database untouched.
        stored = storage.get_solution_provider().save(
            ext=ext, content=content,
            namespace=storage.NAMESPACE_SOLUTION_PDFS, ticket=ticket,
        )
        solution = Solution(
            ticket=ticket,
            problem_id=problem.id,
            submitter_id=submitter.id,
            title=title.strip(),
            short_description=short_description.strip(),
            skills=(skills.strip() or None) if skills else None,
            expected_impact=expected_impact.strip(),
            contributors=(contributors.strip() or None) if contributors else None,
            estimated_resources=(estimated_resources.strip() or None)
            if estimated_resources
            else None,
            pdf_stored_name=stored,
            pdf_original_name=original,
            pdf_mime_type="application/pdf",
            pdf_size_bytes=len(content),
            status=SolutionStatus.SUBMITTED.value,
        )
        db.add(solution)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # Never leave an orphan object behind.
            storage.get_solution_provider().delete(
                namespace=storage.NAMESPACE_SOLUTION_PDFS,
                ticket=ticket, stored_name=stored,
            )
            continue
        db.refresh(solution)
        return solution
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Could not submit the solution. Please retry.",
    )


def _visible(db: Session, solution: Solution, viewer: User | None) -> bool:
    problem = db.get(Problem, solution.problem_id)
    if problem is not None and problem.status in PUBLIC_STATUSES:
        return True
    if viewer is None:
        return False
    return viewer.id in (solution.submitter_id, problem.owner_id if problem else None)


def get_solution(db: Session, ticket: str, viewer: User | None) -> Solution:
    solution = db.execute(
        select(Solution).where(Solution.ticket == ticket)
    ).scalars().first()
    if solution is None or not _visible(db, solution, viewer):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Solution not found."
        )
    return solution


def list_for_problem(
    db: Session, problem_ticket: str, viewer: User | None,
    skip: int = 0, limit: int = 20,
) -> tuple[list[Solution], int, Problem]:
    problem = _problem_or_404(db, problem_ticket)
    if problem.status not in PUBLIC_STATUSES:
        if viewer is None or viewer.id not in (
            problem.owner_id,
        ):
            # Non-public problems: only the owner may list solutions here.
            # (A submitter sees their own via /users/me/solutions.)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found."
            )
    total = db.execute(
        select(func.count()).select_from(Solution).where(Solution.problem_id == problem.id)
    ).scalar_one()
    rows = (
        db.execute(
            select(Solution)
            .where(Solution.problem_id == problem.id)
            .order_by(Solution.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(rows), total, problem


def list_public(db: Session, skip: int = 0, limit: int = 20) -> tuple[list[Solution], int]:
    total = db.execute(
        select(func.count())
        .select_from(Solution)
        .join(Problem, Problem.id == Solution.problem_id)
        .where(Problem.status.in_(PUBLIC_STATUSES))
    ).scalar_one()
    rows = (
        db.execute(
            select(Solution)
            .join(Problem, Problem.id == Solution.problem_id)
            .where(Problem.status.in_(PUBLIC_STATUSES))
            .order_by(Solution.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def list_mine(db: Session, user: User, skip: int = 0, limit: int = 20) -> tuple[list[Solution], int]:
    total = db.execute(
        select(func.count()).select_from(Solution).where(Solution.submitter_id == user.id)
    ).scalar_one()
    rows = (
        db.execute(
            select(Solution)
            .where(Solution.submitter_id == user.id)
            .order_by(Solution.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def update_solution(
    db: Session, submitter: User, ticket: str, data: SolutionUpdate
) -> Solution:
    solution = db.execute(
        select(Solution).where(Solution.ticket == ticket)
    ).scalars().first()
    if solution is None or solution.submitter_id != submitter.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Solution not found."
        )
    if solution.status != SolutionStatus.SUBMITTED.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only solutions in SUBMITTED state can be edited.",
        )
    changes = data.model_dump(exclude_unset=True)
    if not any(v is not None for v in changes.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No updatable fields provided.",
        )
    for field, value in changes.items():
        if value is None:
            continue
        setattr(solution, field, value.strip())
    # Ticket, problem link, PDF and status never change via this endpoint.
    db.add(solution)
    db.commit()
    db.refresh(solution)
    return solution


def transition_status(
    db: Session, actor: User, ticket: str, new_status: str
) -> Solution:
    """Only the parent problem's owner may advance lifecycle state, and only
    along the allowed transition map."""
    solution = db.execute(
        select(Solution).where(Solution.ticket == ticket)
    ).scalars().first()
    if solution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Solution not found."
        )
    problem = db.get(Problem, solution.problem_id)
    if problem is None or problem.owner_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem owner can change solution status.",
        )
    allowed = SOLUTION_TRANSITIONS.get(solution.status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid transition from {solution.status}. Allowed: {allowed or 'none'}.",
        )
    solution.status = new_status
    db.add(solution)
    db.commit()
    db.refresh(solution)
    return solution


def submitter_label(db: Session, solution: Solution) -> str:
    user = db.get(User, solution.submitter_id)
    return user.account_type.value if user else "unknown"


def problem_ticket_of(db: Session, solution: Solution) -> str:
    problem = db.get(Problem, solution.problem_id)
    return problem.ticket if problem else "?"
