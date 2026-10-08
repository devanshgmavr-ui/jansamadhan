import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SolutionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    short_description: str | None = Field(default=None, min_length=20, max_length=2000)
    skills: str | None = Field(default=None, max_length=500)
    expected_impact: str | None = Field(default=None, min_length=10, max_length=2000)
    contributors: str | None = Field(default=None, max_length=500)
    estimated_resources: str | None = Field(default=None, max_length=500)


class SolutionStatusUpdate(BaseModel):
    status: str = Field(min_length=3, max_length=30)


class SolutionOut(BaseModel):
    ticket: str
    problem_ticket: str
    title: str
    short_description: str
    skills: str | None
    expected_impact: str
    contributors: str | None
    estimated_resources: str | None
    pdf_name: str
    pdf_size_bytes: int
    status: str
    submitter_account_type: str
    mine: bool = False
    created_at: datetime
    updated_at: datetime


class SolutionListOut(BaseModel):
    ticket: str
    problem_ticket: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class SolutionTrackOut(BaseModel):
    ticket: str
    problem_ticket: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    stages: list[dict]
