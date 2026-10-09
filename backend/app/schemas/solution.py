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
    implementation_plan: str | None = Field(default=None, max_length=5000)
    estimated_cost: str | None = Field(default=None, max_length=120)
    estimated_timeline: str | None = Field(default=None, max_length=120)


class SolutionStatusUpdate(BaseModel):
    status: str = Field(min_length=3, max_length=30)


class SolutionAttachmentOut(BaseModel):
    id: uuid.UUID
    original_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class SolutionReviewRequest(BaseModel):
    decision: str = Field(min_length=3, max_length=30)
    reason: str | None = Field(default=None, max_length=2000)


class SolutionOut(BaseModel):
    ticket: str
    problem_ticket: str
    title: str
    short_description: str
    skills: str | None
    expected_impact: str
    contributors: str | None
    estimated_resources: str | None
    implementation_plan: str | None = None
    estimated_cost: str | None = None
    estimated_timeline: str | None = None
    pdf_name: str
    pdf_size_bytes: int
    status: str
    review_status: str = "SUBMITTED"
    review_reason: str | None = None
    reviewed_at: datetime | None = None
    is_selected: bool = False
    attachments: list[SolutionAttachmentOut] = []
    submitter_account_type: str
    mine: bool = False
    created_at: datetime
    updated_at: datetime


class SolutionListOut(BaseModel):
    ticket: str
    problem_ticket: str
    title: str
    status: str
    review_status: str = "SUBMITTED"
    is_selected: bool = False
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


class ImplementationAttachmentOut(BaseModel):
    id: uuid.UUID
    original_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class ImplementationUpdateOut(BaseModel):
    id: uuid.UUID
    problem_ticket: str
    stage: str
    title: str
    description: str | None = None
    attachments: list[ImplementationAttachmentOut] = []
    created_at: datetime


class ImplementationUpdateCreate(BaseModel):
    stage: str = Field(min_length=3, max_length=40)
    title: str = Field(min_length=5, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class TimelineEvent(BaseModel):
    kind: str
    label: str
    detail: str | None = None
    created_at: datetime


class TransparencySolutionOut(BaseModel):
    ticket: str
    title: str
    status: str
    review_status: str = "SUBMITTED"
    is_selected: bool = False
    created_at: datetime


class TransparencyDetailOut(BaseModel):
    """Public detail for an approved complaint (Phase 3). Challenge pages
    carry solutions + winning solution; issue pages carry the
    implementation timeline. Public-safe fields only."""

    ticket: str
    title: str
    category: str
    location: str
    severity: str
    status: str
    decided_at: datetime | None = None
    resolution_type: str | None = None
    decision_reason: str | None = None
    created_at: datetime
    solutions: list[TransparencySolutionOut] = []
    selected_solution: TransparencySolutionOut | None = None
    solution_count: int = 0
    implementation_updates: list[ImplementationUpdateOut] = []
    timeline: list[TimelineEvent] = []
