import uuid
from datetime import date

from pydantic import BaseModel, Field


class CollabCreate(BaseModel):
    problem_ticket: str = Field(max_length=20)
    solution_ticket: str | None = Field(default=None, max_length=20)
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20, max_length=5000)


class JoinRequest(BaseModel):
    role: str = Field(max_length=40)


class MemberPatch(BaseModel):
    status: str = Field(pattern="^(ACTIVE|REMOVED)$")


class CollabStatusUpdate(BaseModel):
    status: str = Field(max_length=30)


class CollabOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str


class MemberOut(BaseModel):
    id: uuid.UUID
    role: str
    status: str


class ProjectCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20, max_length=5000)


class ProjectStatusUpdate(BaseModel):
    status: str = Field(max_length=30)


class ProjectOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    owner_id: uuid.UUID


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    status: str | None = Field(default=None, max_length=20)


class UpdateCreate(BaseModel):
    text: str = Field(min_length=5, max_length=3000)


class ImpactUpsert(BaseModel):
    implementation_date: date | None = None
    affected_population: str | None = Field(default=None, max_length=200)
    outcomes: str | None = Field(default=None, max_length=3000)
    evidence: str | None = Field(default=None, max_length=3000)
    notes: str | None = Field(default=None, max_length=3000)
