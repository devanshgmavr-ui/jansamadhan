from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_optional_user
from app.db.database import get_db
from app.models.solution import Solution
from app.models.user import User
from app.schemas.solution import (
    SolutionListOut,
    SolutionOut,
    SolutionStatusUpdate,
    SolutionTrackOut,
    SolutionUpdate,
)
from app.services import solution_service
from app.services import storage as storage_svc

router = APIRouter(tags=["solutions"])
problems_router = APIRouter(prefix="/problems", tags=["solutions"])
users_router = APIRouter(prefix="/users", tags=["solutions"])


def _to_out(
    db: Session, solution: Solution, viewer: User | None = None
) -> SolutionOut:
    return SolutionOut(
        ticket=solution.ticket,
        problem_ticket=solution_service.problem_ticket_of(db, solution),
        title=solution.title,
        short_description=solution.short_description,
        skills=solution.skills,
        expected_impact=solution.expected_impact,
        contributors=solution.contributors,
        estimated_resources=solution.estimated_resources,
        pdf_name=solution.pdf_original_name,
        pdf_size_bytes=solution.pdf_size_bytes,
        status=solution.status,
        submitter_account_type=solution_service.submitter_label(db, solution),
        mine=viewer is not None and viewer.id == solution.submitter_id,
        created_at=solution.created_at,
        updated_at=solution.updated_at,
    )


def _to_list(db: Session, solution: Solution) -> SolutionListOut:
    return SolutionListOut(
        ticket=solution.ticket,
        problem_ticket=solution_service.problem_ticket_of(db, solution),
        title=solution.title,
        status=solution.status,
        created_at=solution.created_at,
        updated_at=solution.updated_at,
    )


@problems_router.post("/{ticket}/solutions", response_model=SolutionOut, status_code=201)
def submit_solution(
    ticket: str,
    title: str = Form(min_length=5, max_length=200),
    short_description: str = Form(min_length=20, max_length=2000),
    skills: str | None = Form(default=None, max_length=500),
    expected_impact: str = Form(min_length=10, max_length=2000),
    contributors: str | None = Form(default=None, max_length=500),
    estimated_resources: str | None = Form(default=None, max_length=500),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The problem link comes from the URL path and cannot be overridden."""
    solution = solution_service.submit_solution(
        db,
        user,
        ticket,
        title=title,
        short_description=short_description,
        skills=skills,
        expected_impact=expected_impact,
        contributors=contributors,
        estimated_resources=estimated_resources,
        pdf=file,
    )
    return _to_out(db, solution, user)


@problems_router.get("/{ticket}/solutions")
def problem_solutions(
    ticket: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    rows, total, problem = solution_service.list_for_problem(
        db, ticket, viewer, skip=skip, limit=limit
    )
    return {
        "problem_ticket": problem.ticket,
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [_to_list(db, s) for s in rows],
    }


@router.get("/solutions", response_model=dict)
def browse_solutions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Public solution listing (solutions of public problems only)."""
    rows, total = solution_service.list_public(db, skip=skip, limit=limit)
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [_to_list(db, s) for s in rows],
    }


@router.get("/solutions/{ticket}", response_model=SolutionOut)
def get_solution(
    ticket: str,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    return _to_out(db, solution_service.get_solution(db, ticket, viewer), viewer)


@router.put("/solutions/{ticket}", response_model=SolutionOut)
def edit_solution(
    ticket: str,
    data: SolutionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _to_out(db, solution_service.update_solution(db, user, ticket, data), user)


@router.patch("/solutions/{ticket}/status", response_model=SolutionOut)
def change_solution_status(
    ticket: str,
    data: SolutionStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _to_out(db, solution_service.transition_status(db, user, ticket, data.status), user)


@router.get("/solutions/{ticket}/track", response_model=SolutionTrackOut)
def track_solution(
    ticket: str,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    solution = solution_service.get_solution(db, ticket, viewer)
    stages = []
    current = solution_service._STAGE_INDEX.get(solution.status, 0)
    for i, (key, label) in enumerate(solution_service.SOLUTION_TRACK_STAGES):
        state = "done" if i < current else ("current" if i == current else "pending")
        stages.append({"key": key, "label": label, "state": state})
    return SolutionTrackOut(
        ticket=solution.ticket,
        problem_ticket=solution_service.problem_ticket_of(db, solution),
        title=solution.title,
        status=solution.status,
        created_at=solution.created_at,
        updated_at=solution.updated_at,
        stages=stages,
    )


@router.get("/solutions/{ticket}/download")
def download_solution(
    ticket: str,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    solution = solution_service.get_solution(db, ticket, viewer)
    content = storage_svc.get_solution_provider().read_bytes(
        namespace=storage_svc.NAMESPACE_SOLUTION_PDFS,
        ticket=solution.ticket, stored_name=solution.pdf_stored_name,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{solution.pdf_original_name}"'
        },
    )


@users_router.get("/me/solutions")
def my_solutions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows, total = solution_service.list_mine(db, user, skip=skip, limit=limit)
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [_to_list(db, s) for s in rows],
    }
