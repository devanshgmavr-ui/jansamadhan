"""Contributions and the account dashboard. All data is real database rows."""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.contribution import Contribution, ContributionStatus
from app.models.problem import Problem
from app.models.solution import Solution
from app.models.user import AccountType, User
from app.schemas.contribution import ContributionCreate, ContributionUpdate
from app.services import auth_service


def _resolve_problem(db: Session, ticket: str | None) -> Problem | None:
    if not ticket:
        return None
    problem = db.execute(
        select(Problem).where(Problem.ticket == ticket)
    ).scalars().first()
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Related problem not found."
        )
    return problem


def _resolve_solution(db: Session, ticket: str | None, problem: Problem | None):
    if not ticket:
        return None
    solution = db.execute(
        select(Solution).where(Solution.ticket == ticket)
    ).scalars().first()
    if solution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Related solution not found."
        )
    if problem is not None and solution.problem_id != problem.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Solution does not belong to the given problem.",
        )
    return solution


def create_contribution(
    db: Session, author: User, data: ContributionCreate
) -> Contribution:
    if not data.problem_ticket and not data.solution_ticket:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A related problem or solution ticket is required.",
        )
    problem = _resolve_problem(db, data.problem_ticket)
    solution = _resolve_solution(db, data.solution_ticket, problem)
    if solution is not None and problem is None:
        problem = db.get(Problem, solution.problem_id)
    row = Contribution(
        user_id=author.id,
        problem_id=problem.id if problem else None,
        solution_id=solution.id if solution else None,
        type=data.type,
        description=data.description.strip(),
        status=ContributionStatus.PENDING.value,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _can_view(db: Session, row: Contribution, viewer: User) -> bool:
    if row.user_id == viewer.id:
        return True
    if row.problem_id is not None:
        problem = db.get(Problem, row.problem_id)
        if problem is not None and problem.owner_id == viewer.id:
            return True
    return False


def get_contribution(db: Session, viewer: User, cid) -> Contribution:
    from uuid import UUID

    try:
        uid = cid if isinstance(cid, UUID) else UUID(str(cid))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contribution not found."
        )
    row = db.get(Contribution, uid)
    if row is None or not _can_view(db, row, viewer):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contribution not found."
        )
    return row


def update_contribution(
    db: Session, author: User, cid, data: ContributionUpdate
) -> Contribution:
    row = get_contribution(db, author, cid)
    if row.user_id != author.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the contributor can edit this contribution.",
        )
    if row.status != ContributionStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only pending contributions can be edited.",
        )
    changes = data.model_dump(exclude_unset=True)
    if not any(v is not None for v in changes.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No updatable fields provided.",
        )
    if changes.get("type"):
        row.type = changes["type"]
    if changes.get("description"):
        row.description = changes["description"].strip()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_contribution(db: Session, author: User, cid) -> None:
    row = get_contribution(db, author, cid)
    if row.user_id != author.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the contributor can delete this contribution.",
        )
    if row.status != ContributionStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only pending contributions can be deleted.",
        )
    db.delete(row)
    db.commit()


def set_status(db: Session, actor: User, cid, new_status: str) -> Contribution:
    row = get_contribution(db, actor, cid)
    if row.problem_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only problem-linked contributions can be moderated.",
        )
    problem = db.get(Problem, row.problem_id)
    if problem is None or problem.owner_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the problem owner can accept or decline contributions.",
        )
    if row.status != ContributionStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Contribution is already decided.",
        )
    row.status = new_status
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_mine(db: Session, user: User, skip: int = 0, limit: int = 20):
    total = db.execute(
        select(func.count()).select_from(Contribution).where(Contribution.user_id == user.id)
    ).scalar_one()
    rows = (
        db.execute(
            select(Contribution)
            .where(Contribution.user_id == user.id)
            .order_by(Contribution.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def list_for_problem(db: Session, owner: User, ticket: str):
    problem = db.execute(
        select(Problem).where(Problem.ticket == ticket)
    ).scalars().first()
    if problem is None or problem.owner_id != owner.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found."
        )
    rows = (
        db.execute(
            select(Contribution)
            .where(Contribution.problem_id == problem.id)
            .order_by(Contribution.created_at.desc())
        )
        .scalars()
        .all()
    )
    return problem, list(rows)


def ticket_of(db: Session, row: Contribution) -> tuple[str | None, str | None]:
    pt = db.get(Problem, row.problem_id).ticket if row.problem_id else None
    st = db.get(Solution, row.solution_id).ticket if row.solution_id else None
    return pt, st


def dashboard(db: Session, user: User) -> dict:
    problems_total = db.execute(
        select(func.count()).select_from(Problem).where(Problem.owner_id == user.id)
    ).scalar_one()
    solutions_total = db.execute(
        select(func.count()).select_from(Solution).where(Solution.submitter_id == user.id)
    ).scalar_one()
    contrib_total = db.execute(
        select(func.count()).select_from(Contribution).where(Contribution.user_id == user.id)
    ).scalar_one()
    accepted = db.execute(
        select(func.count())
        .select_from(Contribution)
        .where(
            Contribution.user_id == user.id,
            Contribution.status == ContributionStatus.ACCEPTED.value,
        )
    ).scalar_one()
    recent_problems = (
        db.execute(
            select(Problem).where(Problem.owner_id == user.id)
            .order_by(Problem.created_at.desc()).limit(5)
        )
        .scalars()
        .all()
    )
    recent_solutions = (
        db.execute(
            select(Solution).where(Solution.submitter_id == user.id)
            .order_by(Solution.created_at.desc()).limit(5)
        )
        .scalars()
        .all()
    )
    recent_contribs, _ = list_mine(db, user, 0, 5)
    from app.services import collaboration_service

    collabs = collaboration_service.my_collaborations(db, user)
    profile = auth_service.serialize_profile(db, user)
    skills = None
    if user.account_type == AccountType.STUDENT and profile:
        skills = profile.get("skills")
    elif user.account_type == AccountType.INDIVIDUAL and profile:
        skills = profile.get("skills")
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "account_type": user.account_type.value,
            "is_email_verified": user.is_email_verified,
            "is_phone_verified": user.is_phone_verified,
            "is_active": user.is_active,
        },
        "profile": profile,
        "counts": {
            "problems": problems_total,
            "solutions": solutions_total,
            "contributions": contrib_total,
            "contributions_accepted": accepted,
            "collaborations": len(collabs),
        },
        "recent_problems": [
            {"ticket": p.ticket, "title": p.title, "status": p.status,
             "created_at": p.created_at.isoformat()}
            for p in recent_problems
        ],
        "recent_solutions": [
            {"ticket": s.ticket,
             "title": s.title, "status": s.status,
             "created_at": s.created_at.isoformat()}
            for s in recent_solutions
        ],
        "recent_contributions": [
            {"id": str(c.id), "type": c.type, "status": c.status,
             "created_at": c.created_at.isoformat()}
            for c in recent_contribs
        ],
        "collaborations": collabs,
        "skills": skills,
    }
