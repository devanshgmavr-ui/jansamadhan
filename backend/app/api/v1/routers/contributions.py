from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.database import get_db
from app.models.contribution import Contribution
from app.models.user import User
from app.schemas.contribution import (
    ContributionCreate,
    ContributionOut,
    ContributionStatusUpdate,
    ContributionUpdate,
    DashboardOut,
)
from app.services import contribution_service

router = APIRouter(tags=["contributions"])
users_router = APIRouter(prefix="/users", tags=["contributions"])


def _to_out(db: Session, row: Contribution) -> ContributionOut:
    pt, st = contribution_service.ticket_of(db, row)
    return ContributionOut(
        id=row.id,
        type=row.type,
        description=row.description,
        status=row.status,
        problem_ticket=pt,
        solution_ticket=st,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/contributions", response_model=ContributionOut, status_code=201)
def create_contribution(
    data: ContributionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _to_out(db, contribution_service.create_contribution(db, user, data))


@router.get("/contributions/{cid}", response_model=ContributionOut)
def get_contribution(
    cid: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _to_out(db, contribution_service.get_contribution(db, user, cid))


@router.put("/contributions/{cid}", response_model=ContributionOut)
def edit_contribution(
    cid: str,
    data: ContributionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _to_out(db, contribution_service.update_contribution(db, user, cid, data))


@router.delete("/contributions/{cid}", status_code=204)
def remove_contribution(
    cid: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    contribution_service.delete_contribution(db, user, cid)
    return None


@router.patch("/contributions/{cid}/status", response_model=ContributionOut)
def moderate_contribution(
    cid: str,
    data: ContributionStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _to_out(db, contribution_service.set_status(db, user, cid, data.status))


@router.get("/problems/{ticket}/contributions")
def problem_contributions(
    ticket: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    problem, rows = contribution_service.list_for_problem(db, user, ticket)
    return {
        "problem_ticket": problem.ticket,
        "total": len(rows),
        "items": [_to_out(db, r) for r in rows],
    }


@users_router.get("/me/contributions")
def my_contributions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows, total = contribution_service.list_mine(db, user, skip=skip, limit=limit)
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [_to_out(db, r) for r in rows],
    }


@users_router.get("/me/dashboard", response_model=DashboardOut)
def my_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return contribution_service.dashboard(db, user)
