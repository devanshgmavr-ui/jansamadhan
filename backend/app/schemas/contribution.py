import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ContributionCreate(BaseModel):
    problem_ticket: str | None = Field(default=None, max_length=20)
    solution_ticket: str | None = Field(default=None, max_length=20)
    type: str = Field(pattern="^(SOLUTION_PROPOSAL|RESEARCH|TECHNICAL|PROTOTYPE_TESTING|DEVELOPMENT|COLLABORATION|OTHER)$")
    description: str = Field(min_length=10, max_length=3000)


class ContributionUpdate(BaseModel):
    type: str | None = Field(default=None, pattern="^(SOLUTION_PROPOSAL|RESEARCH|TECHNICAL|PROTOTYPE_TESTING|DEVELOPMENT|COLLABORATION|OTHER)$")
    description: str | None = Field(default=None, min_length=10, max_length=3000)


class ContributionStatusUpdate(BaseModel):
    status: str = Field(pattern="^(ACCEPTED|DECLINED)$")


class ContributionOut(BaseModel):
    id: uuid.UUID
    type: str
    description: str
    status: str
    problem_ticket: str | None
    solution_ticket: str | None
    created_at: datetime
    updated_at: datetime


class DashboardOut(BaseModel):
    user: dict
    profile: dict | None
    counts: dict
    recent_problems: list[dict]
    recent_solutions: list[dict]
    recent_contributions: list[dict]
    collaborations: list[dict] = []
