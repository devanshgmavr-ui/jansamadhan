"""Collaboration, project lifecycle, milestones, updates and impact.

Permissions are enforced here against the authenticated user. No caller can
act for another user, change roles arbitrarily, or skip lifecycle states."""

from datetime import date as date_type
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.collaboration import (
    PROJECT_TRANSITIONS,
    Collaboration,
    CollaborationMember,
    CollaborationStatus,
    ImpactRecord,
    MemberRole,
    MemberStatus,
    Milestone,
    MilestoneStatus,
    Project,
    ProjectStatus,
    ProjectUpdate,
)
from app.models.problem import Problem, ProblemStatus
from app.models.solution import SOLUTION_TRANSITIONS, Solution, SolutionStatus
from app.models.user import User

VALID_ROLES = {r.value for r in MemberRole}
REQUESTABLE_ROLES = VALID_ROLES - {MemberRole.PROBLEM_OWNER.value}


def _utcnow():
    return datetime.now(timezone.utc)


def _problem_by_ticket(db: Session, ticket: str) -> Problem:
    problem = db.execute(select(Problem).where(Problem.ticket == ticket)).scalars().first()
    if problem is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found.")
    return problem


def _solution_by_ticket(db: Session, ticket: str):
    solution = db.execute(select(Solution).where(Solution.ticket == ticket)).scalars().first()
    if solution is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solution not found.")
    return solution


def _get_collab(db: Session, cid) -> Collaboration:
    from uuid import UUID

    try:
        uid = cid if isinstance(cid, UUID) else UUID(str(cid))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collaboration not found.")
    collab = db.get(Collaboration, uid)
    if collab is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collaboration not found.")
    return collab


def _membership(db: Session, collab_id, user_id) -> CollaborationMember | None:
    return (
        db.execute(
            select(CollaborationMember).where(
                CollaborationMember.collaboration_id == collab_id,
                CollaborationMember.user_id == user_id,
            )
        )
        .scalars()
        .first()
    )


def _is_manager(db: Session, collab: Collaboration, user: User) -> bool:
    if collab.created_by == user.id:
        return True
    problem = db.get(Problem, collab.problem_id)
    return problem is not None and problem.owner_id == user.id


def _require_visible(db: Session, collab: Collaboration, viewer: User) -> None:
    if _is_manager(db, collab, viewer):
        return
    m = _membership(db, collab.id, viewer.id)
    if m is None or m.status not in (MemberStatus.ACTIVE.value, MemberStatus.PENDING.value):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collaboration not found.")


def _require_active_member(db: Session, collab: Collaboration, user: User) -> CollaborationMember:
    if _is_manager(db, collab, user):
        m = _membership(db, collab.id, user.id)
        if m is not None and m.status == MemberStatus.ACTIVE.value:
            return m
        # Managers act by virtue of ownership even without a member row.
        return m  # may be None; callers treat manager status separately
    m = _membership(db, collab.id, user.id)
    if m is None or m.status != MemberStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only active members can perform this action.")
    return m


def create_collaboration(
    db: Session, creator: User, problem_ticket: str, solution_ticket: str | None,
    title: str, description: str,
) -> Collaboration:
    problem = _problem_by_ticket(db, problem_ticket)
    solution = None
    if solution_ticket:
        solution = _solution_by_ticket(db, solution_ticket)
        if solution.problem_id != problem.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Solution does not belong to the given problem.")
    is_owner = problem.owner_id == creator.id
    is_solver = solution is not None and solution.submitter_id == creator.id
    if solution is None:
        soi = db.execute(select(Solution.id).where(
            Solution.problem_id == problem.id, Solution.submitter_id == creator.id)).first()
        is_solver = is_solver or soi is not None
    if not (is_owner or is_solver):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the problem owner or a solution contributor can start a collaboration.")
    collab = Collaboration(
        problem_id=problem.id, solution_id=solution.id if solution else None,
        title=title.strip(), description=description.strip(),
        status=CollaborationStatus.FORMING.value, created_by=creator.id,
    )
    db.add(collab)
    db.flush()
    role = MemberRole.PROBLEM_OWNER.value if is_owner else MemberRole.SOLUTION_CONTRIBUTOR.value
    db.add(CollaborationMember(collaboration_id=collab.id, user_id=creator.id,
                               role=role, status=MemberStatus.ACTIVE.value))
    if problem.status == ProblemStatus.OPEN.value:
        problem.status = ProblemStatus.COLLABORATION.value
        db.add(problem)
    if collab.status == CollaborationStatus.FORMING.value:
        collab.status = CollaborationStatus.ACTIVE.value
        db.add(collab)
    db.commit()
    db.refresh(collab)
    return collab


def request_join(db: Session, user: User, cid, role: str) -> CollaborationMember:
    collab = _get_collab(db, cid)
    if role not in REQUESTABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Invalid or reserved role.")
    if collab.status in (CollaborationStatus.CLOSED.value, CollaborationStatus.COMPLETED.value):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="This collaboration is closed to new members.")
    existing = _membership(db, collab.id, user.id)
    if existing is not None:
        if existing.status == MemberStatus.ACTIVE.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a member.")
        if existing.status == MemberStatus.PENDING.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Request already pending.")
        existing.status = MemberStatus.PENDING.value
        existing.role = role
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    row = CollaborationMember(collaboration_id=collab.id, user_id=user.id,
                              role=role, status=MemberStatus.PENDING.value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def moderate_member(db: Session, actor: User, cid, mid, new_status: str) -> CollaborationMember:
    collab = _get_collab(db, cid)
    if not _is_manager(db, collab, actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the collaboration creator or problem owner can moderate members.")
    from uuid import UUID

    try:
        target = db.get(CollaborationMember, mid if isinstance(mid, UUID) else UUID(str(mid)))
    except ValueError:
        target = None
    if target is None or target.collaboration_id != collab.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
    if target.user_id == collab.created_by and new_status != MemberStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="The collaboration creator cannot be removed.")
    if new_status == MemberStatus.ACTIVE.value:
        if target.status != MemberStatus.PENDING.value:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Only pending requests can be accepted.")
    elif new_status == MemberStatus.REMOVED.value:
        if target.status not in (MemberStatus.PENDING.value, MemberStatus.ACTIVE.value):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Member cannot be removed from this state.")
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid member status.")
    target.status = new_status
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def leave(db: Session, user: User, cid) -> None:
    collab = _get_collab(db, cid)
    m = _membership(db, collab.id, user.id)
    if m is None or m.status != MemberStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active membership not found.")
    if m.user_id == collab.created_by:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="The creator cannot leave; close the collaboration instead.")
    m.status = MemberStatus.LEFT.value
    db.add(m)
    db.commit()


def set_collab_status(db: Session, actor: User, cid, new_status: str) -> Collaboration:
    collab = _get_collab(db, cid)
    if not _is_manager(db, collab, actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the collaboration creator or problem owner can change its status.")
    allowed = {
        CollaborationStatus.FORMING.value: [CollaborationStatus.ACTIVE.value, CollaborationStatus.CLOSED.value],
        CollaborationStatus.ACTIVE.value: [CollaborationStatus.PAUSED.value, CollaborationStatus.COMPLETED.value, CollaborationStatus.CLOSED.value],
        CollaborationStatus.PAUSED.value: [CollaborationStatus.ACTIVE.value, CollaborationStatus.CLOSED.value],
        CollaborationStatus.COMPLETED.value: [CollaborationStatus.CLOSED.value],
        CollaborationStatus.CLOSED.value: [],
    }
    if new_status not in allowed.get(collab.status, []):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Invalid transition from {collab.status}.")
    collab.status = new_status
    db.add(collab)
    db.commit()
    db.refresh(collab)
    return collab


def _advance_solution(db: Session, solution: Solution, target: str) -> None:
    guard = 0
    while solution.status != target and guard < 12:
        nxt = SOLUTION_TRANSITIONS.get(solution.status, [])
        if not nxt:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"Solution cannot advance from {solution.status}.")
        solution.status = nxt[0]
        guard += 1
    if solution.status != target:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Solution lifecycle cannot reach the required state.")
    db.add(solution)


def create_project(db: Session, actor: User, cid, title: str, description: str) -> Project:
    collab = _get_collab(db, cid)
    _require_active_member(db, collab, actor)
    if not _is_manager(db, collab, actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the collaboration creator or problem owner can create the project.")
    if collab.status != CollaborationStatus.ACTIVE.value:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Projects can only start from an active collaboration.")
    existing = db.execute(select(Project).where(Project.collaboration_id == collab.id)).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project already exists.")
    project = Project(collaboration_id=collab.id, title=title.strip(),
                      description=description.strip(), status=ProjectStatus.DEVELOPMENT.value)
    db.add(project)
    problem = db.get(Problem, collab.problem_id)
    if problem is not None and problem.status in (ProblemStatus.OPEN.value, ProblemStatus.COLLABORATION.value):
        problem.status = ProblemStatus.IN_DEVELOPMENT.value
        db.add(problem)
    if collab.solution_id is not None:
        solution = db.get(Solution, collab.solution_id)
        if solution is not None:
            _advance_solution(db, solution, SolutionStatus.DEVELOPMENT.value)
    db.commit()
    db.refresh(project)
    return project


def _get_project(db: Session, pid) -> Project:
    from uuid import UUID

    try:
        uid = pid if isinstance(pid, UUID) else UUID(str(pid))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    project = db.get(Project, uid)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def _project_collab(db: Session, project: Project) -> Collaboration:
    return db.get(Collaboration, project.collaboration_id)


def require_project_visible(db: Session, project: Project, viewer: User) -> Collaboration:
    collab = _project_collab(db, project)
    _require_visible(db, collab, viewer)
    return collab


def transition_project(db: Session, actor: User, pid, new_status: str) -> Project:
    project = _get_project(db, pid)
    collab = _project_collab(db, project)
    _require_active_member(db, collab, actor)
    allowed = PROJECT_TRANSITIONS.get(project.status, [])
    if new_status not in allowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"Invalid transition from {project.status}. Allowed: {allowed or 'none'}.")
    project.status = new_status
    db.add(project)
    problem = db.get(Problem, collab.problem_id)
    solution = db.get(Solution, collab.solution_id) if collab.solution_id else None
    mapping = {
        # PROTOTYPE is handled above (solution only); the problem stays
        # IN_DEVELOPMENT until the PILOT stage begins.
        ProjectStatus.PILOT.value: (ProblemStatus.PILOT.value, SolutionStatus.PILOT.value),
        ProjectStatus.IMPLEMENTATION.value: (ProblemStatus.IMPLEMENTED.value, SolutionStatus.IMPLEMENTED.value),
        ProjectStatus.IMPACT_RECORDED.value: (None, SolutionStatus.IMPACT_RECORDED.value),
        ProjectStatus.CLOSED.value: (ProblemStatus.CLOSED.value, None),
    }
    if project.status == ProjectStatus.PROTOTYPE.value and solution is not None:
        _advance_solution(db, solution, SolutionStatus.PROTOTYPE.value)
    else:
        targets = mapping.get(project.status, (None, None))
        if problem is not None and targets[0] and problem.status != targets[0]:
            problem.status = targets[0]
            db.add(problem)
        if solution is not None and targets[1]:
            _advance_solution(db, solution, targets[1])
    db.commit()
    db.refresh(project)
    return project


def add_milestone(db: Session, actor: User, pid, title: str, description: str | None,
                  due_date: date_type | None, owner_ticket_user_id) -> Milestone:
    from uuid import UUID

    project = _get_project(db, pid)
    collab = _project_collab(db, project)
    _require_active_member(db, collab, actor)
    try:
        owner_id = owner_ticket_user_id if isinstance(owner_ticket_user_id, UUID) else UUID(str(owner_ticket_user_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid milestone owner.")
    owner_m = _membership(db, collab.id, owner_id)
    if owner_m is None or owner_m.status != MemberStatus.ACTIVE.value:
        if not (collab.created_by == owner_id):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="Milestone owner must be an active member.")
    ms = Milestone(project_id=project.id, title=title.strip(),
                   description=(description.strip() if description else None),
                   due_date=due_date, status=MilestoneStatus.PENDING.value, owner_id=owner_id)
    db.add(ms)
    db.commit()
    db.refresh(ms)
    return ms


def update_milestone(db: Session, actor: User, pid, mid, fields: dict) -> Milestone:
    from uuid import UUID

    project = _get_project(db, pid)
    collab = _project_collab(db, project)
    try:
        m = db.get(Milestone, mid if isinstance(mid, UUID) else UUID(str(mid)))
    except ValueError:
        m = None
    if m is None or m.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found.")
    if not (m.owner_id == actor.id or _is_manager(db, collab, actor)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the milestone owner or managers can update it.")
    if "title" in fields and fields["title"] is not None:
        m.title = fields["title"].strip()
    if "description" in fields:
        m.description = fields["description"].strip() if fields["description"] else None
    if "due_date" in fields:
        m.due_date = fields["due_date"]
    if "status" in fields and fields["status"] is not None:
        if fields["status"] not in (MilestoneStatus.PENDING.value, MilestoneStatus.IN_PROGRESS.value, MilestoneStatus.DONE.value):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid milestone status.")
        m.status = fields["status"]
        m.completed_at = _utcnow() if m.status == MilestoneStatus.DONE.value else None
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def delete_milestone(db: Session, actor: User, pid, mid) -> None:
    from uuid import UUID

    project = _get_project(db, pid)
    collab = _project_collab(db, project)
    try:
        m = db.get(Milestone, mid if isinstance(mid, UUID) else UUID(str(mid)))
    except ValueError:
        m = None
    if m is None or m.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Milestone not found.")
    if not (m.owner_id == actor.id or _is_manager(db, collab, actor)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the milestone owner or managers can delete it.")
    db.delete(m)
    db.commit()


def add_update(db: Session, actor: User, pid, text: str) -> ProjectUpdate:
    project = _get_project(db, pid)
    collab = _project_collab(db, project)
    _require_active_member(db, collab, actor)
    row = ProjectUpdate(project_id=project.id, author_id=actor.id, text=text.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def upsert_impact(db: Session, actor: User, pid, fields: dict) -> ImpactRecord:
    project = _get_project(db, pid)
    collab = _project_collab(db, project)
    _require_active_member(db, collab, actor)
    record = db.execute(select(ImpactRecord).where(ImpactRecord.project_id == project.id)).scalars().first()
    if record is None:
        record = ImpactRecord(project_id=project.id)
    for key in ("implementation_date", "affected_population", "outcomes", "evidence", "notes"):
        if key in fields:
            setattr(record, key, fields[key])
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def my_collaborations(db: Session, user: User):
    rows = (
        db.execute(
            select(Collaboration, CollaborationMember)
            .join(CollaborationMember, CollaborationMember.collaboration_id == Collaboration.id)
            .where(CollaborationMember.user_id == user.id)
            .order_by(Collaboration.created_at.desc())
        )
        .all()
    )
    out = []
    for collab, member in rows:
        problem = db.get(Problem, collab.problem_id)
        out.append({
            "id": str(collab.id),
            "title": collab.title,
            "status": collab.status,
            "role": member.role,
            "membership": member.status,
            "problem_ticket": problem.ticket if problem else None,
        })
    return out


def detail(db: Session, viewer: User, cid) -> dict:
    collab = _get_collab(db, cid)
    _require_visible(db, collab, viewer)
    problem = db.get(Problem, collab.problem_id)
    solution = db.get(Solution, collab.solution_id) if collab.solution_id else None
    members = (
        db.execute(
            select(CollaborationMember).where(CollaborationMember.collaboration_id == collab.id)
            .order_by(CollaborationMember.created_at.asc())
        )
        .scalars()
        .all()
    )
    member_users = {}
    if members:
        for u in db.execute(select(User).where(User.id.in_([m.user_id for m in members]))).scalars().all():
            member_users[u.id] = u
    project = db.execute(select(Project).where(Project.collaboration_id == collab.id)).scalars().first()
    return {
        "id": str(collab.id),
        "title": collab.title,
        "description": collab.description,
        "status": collab.status,
        "problem_ticket": problem.ticket if problem else None,
        "solution_ticket": solution.ticket if solution else None,
        "is_manager": _is_manager(db, collab, viewer),
        "members": [
            {"id": str(m.id), "role": m.role, "status": m.status,
             "account_type": member_users[m.user_id].account_type.value if m.user_id in member_users else "?",
             "is_self": m.user_id == viewer.id}
            for m in members
        ],
        "project_id": str(project.id) if project else None,
        "project_status": project.status if project else None,
        "created_at": collab.created_at.isoformat(),
    }


def project_detail(db: Session, viewer: User, pid) -> dict:
    project = _get_project(db, pid)
    collab = require_project_visible(db, project, viewer)
    problem = db.get(Problem, collab.problem_id)
    solution = db.get(Solution, collab.solution_id) if collab.solution_id else None
    milestones = (
        db.execute(select(Milestone).where(Milestone.project_id == project.id)
                   .order_by(Milestone.created_at.asc())).scalars().all()
    )
    updates = (
        db.execute(select(ProjectUpdate).where(ProjectUpdate.project_id == project.id)
                   .order_by(ProjectUpdate.created_at.desc()).limit(50)).scalars().all()
    )
    impact = db.execute(select(ImpactRecord).where(ImpactRecord.project_id == project.id)).scalars().first()
    return {
        "id": str(project.id),
        "title": project.title,
        "description": project.description,
        "status": project.status,
        "collaboration_id": str(collab.id),
        "problem_ticket": problem.ticket if problem else None,
        "solution_ticket": solution.ticket if solution else None,
        "milestones": [
            {"id": str(m.id), "title": m.title, "description": m.description,
             "due_date": m.due_date.isoformat() if m.due_date else None,
             "status": m.status,
             "completed_at": m.completed_at.isoformat() if m.completed_at else None,
             "owner_id": str(m.owner_id)}
            for m in milestones
        ],
        "updates": [
            {"id": str(u.id), "text": u.text, "author_id": str(u.author_id),
             "created_at": u.created_at.isoformat()}
            for u in updates
        ],
        "impact": None if impact is None else {
            "implementation_date": impact.implementation_date.isoformat() if impact.implementation_date else None,
            "affected_population": impact.affected_population,
            "outcomes": impact.outcomes,
            "evidence": impact.evidence,
            "notes": impact.notes,
        },
    }
