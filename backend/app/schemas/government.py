"""Response/request schemas for the government routing portal API (G3).

Government review API: neutral operational wording only. This module never
describes JanSamadhan as an official government website.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GovLoginRequest(BaseModel):
    employee_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class GovTokenResponse(BaseModel):
    # Access-only by design (no government refresh tokens in G3).
    access_token: str
    token_type: str = "bearer"


class GovUserOut(BaseModel):
    id: uuid.UUID
    employee_id: str
    full_name: str | None = None
    designation: str | None = None
    is_active: bool


class GovMessageResponse(BaseModel):
    message: str


class GovDashboardOut(BaseModel):
    pending: int
    attention: int  # AUTO_ESCALATED: needs routing attention
    government_issue: int
    assigned_to_public: int
    more_information_required: int


class GovQueueItem(BaseModel):
    ticket: str
    title: str
    category: str
    location: str
    affected_group: str
    problem_status: str
    review_status: str
    pending_since: datetime
    sla_due_at: datetime
    expired: bool
    escalation_flag: bool
    decided_at: datetime | None = None
    created_at: datetime


class GovQueueOut(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: list[GovQueueItem]


class GovVersionOut(BaseModel):
    version_number: int
    title: str
    category: str
    location: str
    description: str
    affected_group: str
    severity: str
    desired_solution_type: str
    skills: str | None = None
    supporting_info: str | None = None
    revision_note: str | None = None
    created_at: datetime


class GovAIReviewOut(BaseModel):
    review_number: int
    version_number: int
    provider: str
    model: str
    status: str
    decision: str | None = None
    reason: str | None = None
    missing_info: list[str] = []
    category: str | None = None
    affected_group: str | None = None
    geo_context: str | None = None
    problem_type: str | None = None
    scope: str | None = None
    tech_areas: list[str] = []
    tags: list[str] = []
    duplicate_status: str | None = None
    similar: list[dict] = []
    created_at: datetime


class GovActorOut(BaseModel):
    kind: str  # "official" | "system" | "public_user"
    employee_id: str | None = None
    full_name: str | None = None


class GovHistoryItem(BaseModel):
    action: str
    previous_status: str | None = None
    new_status: str
    actor: GovActorOut
    reason: str | None = None
    created_at: datetime


class GovReviewStateOut(BaseModel):
    review_status: str
    pending_since: datetime
    sla_due_at: datetime
    expired: bool
    decided_at: datetime | None = None
    decided_by: GovActorOut | None = None
    escalation_flag: bool
    info_request: str | None = None
    user_response: str | None = None


class GovRequestDetailOut(BaseModel):
    ticket: str
    title: str
    description: str
    category: str
    location: str
    affected_group: str
    severity: str
    desired_solution_type: str
    skills: str | None = None
    supporting_info: str | None = None
    problem_status: str
    current_version: int
    created_at: datetime
    updated_at: datetime
    versions: list[GovVersionOut] = []
    ai_review: GovAIReviewOut | None = None
    government: GovReviewStateOut
    history: list[GovHistoryItem] = []


class GovReasonBody(BaseModel):
    # Required for mark-government-issue and request-information.
    reason: str = Field(min_length=1, max_length=2000)


class GovAssignBody(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class GovActionOut(BaseModel):
    ticket: str
    review_status: str
    problem_status: str
    decided_at: datetime | None = None


class GovSweepOut(BaseModel):
    evaluated: int
    escalated: int
    escalated_tickets: list[str] = []
