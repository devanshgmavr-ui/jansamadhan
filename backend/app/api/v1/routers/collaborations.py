from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.collaboration import (
    CollabCreate,
    CollabOut,
    CollabStatusUpdate,
    ImpactUpsert,
    JoinRequest,
    MemberOut,
    MemberPatch,
    MilestoneCreate,
    MilestoneUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectStatusUpdate,
    UpdateCreate,
)
from app.services import collaboration_service

router = APIRouter(tags=["collaborations"])
users_router = APIRouter(prefix="/users", tags=["collaborations"])


@router.post("/collaborations", response_model=CollabOut, status_code=201)
def create_collaboration(
    data: CollabCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = collaboration_service.create_collaboration(
        db, user, data.problem_ticket, data.solution_ticket, data.title, data.description
    )
    return CollabOut(id=c.id, title=c.title, status=c.status)


@router.get("/collaborations/{cid}", response_model=dict)
def get_collaboration(
    cid: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return collaboration_service.detail(db, user, cid)


@router.post("/collaborations/{cid}/join", response_model=MemberOut, status_code=201)
def join_collaboration(
    cid: str,
    data: JoinRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    m = collaboration_service.request_join(db, user, cid, data.role)
    return MemberOut(id=m.id, role=m.role, status=m.status)


@router.patch("/collaborations/{cid}/members/{mid}", response_model=MemberOut)
def moderate_member(
    cid: str,
    mid: str,
    data: MemberPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    m = collaboration_service.moderate_member(db, user, cid, mid, data.status)
    return MemberOut(id=m.id, role=m.role, status=m.status)


@router.post("/collaborations/{cid}/leave", response_model=dict)
def leave_collaboration(
    cid: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    collaboration_service.leave(db, user, cid)
    return {"message": "Left the collaboration."}


@router.patch("/collaborations/{cid}/status", response_model=CollabOut)
def change_collab_status(
    cid: str,
    data: CollabStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    c = collaboration_service.set_collab_status(db, user, cid, data.status)
    return CollabOut(id=c.id, title=c.title, status=c.status)


@router.post("/collaborations/{cid}/projects", response_model=ProjectOut, status_code=201)
def create_project(
    cid: str,
    data: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = collaboration_service.create_project(db, user, cid, data.title, data.description)
    return ProjectOut(id=p.id, title=p.title, status=p.status)


@router.get("/projects/{pid}", response_model=dict)
def get_project(
    pid: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return collaboration_service.project_detail(db, user, pid)


@router.patch("/projects/{pid}/status", response_model=ProjectOut)
def change_project_status(
    pid: str,
    data: ProjectStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    p = collaboration_service.transition_project(db, user, pid, data.status)
    return ProjectOut(id=p.id, title=p.title, status=p.status)


@router.post("/projects/{pid}/milestones", response_model=dict, status_code=201)
def add_milestone(
    pid: str,
    data: MilestoneCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    m = collaboration_service.add_milestone(
        db, user, pid, data.title, data.description, data.due_date, data.owner_id
    )
    return {"id": str(m.id), "title": m.title, "status": m.status}


@router.patch("/projects/{pid}/milestones/{mid}", response_model=dict)
def edit_milestone(
    pid: str,
    mid: str,
    data: MilestoneUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    m = collaboration_service.update_milestone(
        db, user, pid, mid, data.model_dump(exclude_unset=True)
    )
    return {"id": str(m.id), "title": m.title, "status": m.status}


@router.delete("/projects/{pid}/milestones/{mid}", status_code=204)
def remove_milestone(
    pid: str,
    mid: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    collaboration_service.delete_milestone(db, user, pid, mid)
    return None


@router.post("/projects/{pid}/updates", response_model=dict, status_code=201)
def post_update(
    pid: str,
    data: UpdateCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    u = collaboration_service.add_update(db, user, pid, data.text)
    return {"id": str(u.id)}


@router.put("/projects/{pid}/impact", response_model=dict)
def save_impact(
    pid: str,
    data: ImpactUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    collaboration_service.upsert_impact(db, user, pid, data.model_dump(exclude_unset=True))
    return {"message": "Impact information saved."}


@users_router.get("/me/collaborations")
def my_collaborations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = collaboration_service.my_collaborations(db, user)
    return {"total": len(items), "items": items}
