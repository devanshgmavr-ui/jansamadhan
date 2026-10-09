import uuid
from datetime import datetime

from pydantic import BaseModel, Field

SEVERITIES = ("Low", "Moderate", "High", "Critical")


class ProblemCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    category: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20, max_length=10000)
    affected_group: str = Field(min_length=2, max_length=500)
    severity: str = Field(pattern="^(Low|Moderate|High|Critical)$")
    desired_solution_type: str = Field(min_length=2, max_length=1000)
    skills: str | None = Field(default=None, max_length=500)
    supporting_info: str | None = Field(default=None, max_length=5000)


class ProblemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    category: str | None = Field(default=None, min_length=2, max_length=100)
    location: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, min_length=20, max_length=10000)
    affected_group: str | None = Field(default=None, min_length=2, max_length=500)
    severity: str | None = Field(default=None, pattern="^(Low|Moderate|High|Critical)$")
    desired_solution_type: str | None = Field(default=None, min_length=2, max_length=1000)
    skills: str | None = Field(default=None, max_length=500)
    supporting_info: str | None = Field(default=None, max_length=5000)
    revision_note: str | None = Field(default=None, max_length=500)


class AttachmentOut(BaseModel):
    id: uuid.UUID
    original_name: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class GovernmentReviewInfo(BaseModel):
    """Owner-only government-routing snapshot (G4). Attached to owner-scoped
    problem responses so the dashboard can show the routing state, the
    information request, and the review window. Never added to public
    discovery/detail schemas: strangers must not learn any of this."""

    review_status: str
    info_request: str | None = None
    pending_since: datetime | None = None
    sla_due_at: datetime | None = None
    expired: bool = False
    escalation_flag: bool = False
    # Phase 1 decision classification, derived from the persisted review
    # state (ASSIGNED_TO_PUBLIC -> PUBLIC, GOVERNMENT_ISSUE -> GOVERNMENT).
    # Stored implicitly by the decision, never a separate column.
    resolution_type: str | None = None
    # Public-facing remark recorded with the terminal decision, if any.
    decision_reason: str | None = None
    # Approval timestamp (GovernmentReview.decided_at), reused — no duplicate.
    decided_at: datetime | None = None


class ProblemOut(BaseModel):
    ticket: str
    title: str
    category: str
    location: str
    description: str
    affected_group: str
    severity: str
    desired_solution_type: str
    skills: str | None
    supporting_info: str | None
    status: str
    current_version: int
    created_at: datetime
    updated_at: datetime
    attachments: list[AttachmentOut] = []
    government_review: GovernmentReviewInfo | None = None


class ProblemListOut(BaseModel):
    ticket: str
    title: str
    category: str
    status: str
    current_version: int
    created_at: datetime
    updated_at: datetime


class VersionOut(BaseModel):
    version_number: int
    title: str
    category: str
    location: str
    description: str
    affected_group: str
    severity: str
    desired_solution_type: str
    skills: str | None
    supporting_info: str | None
    revision_note: str | None
    created_at: datetime


class HistoryOut(BaseModel):
    ticket: str
    current_version: int
    versions: list[VersionOut]


class TrackStage(BaseModel):
    key: str
    label: str
    state: str  # done | current | pending


class TrackOut(BaseModel):
    ticket: str
    title: str
    status: str
    current_version: int
    submitted_at: datetime
    updated_at: datetime
    stages: list[TrackStage]
    # Owner-only routing snapshot (same shape as ProblemOut.government_review,
    # same privacy rule: track is owner-scoped, never public). Lets the Track
    # page show the official's information request and review state.
    government_review: GovernmentReviewInfo | None = None


class DiscoveryItem(BaseModel):
    ticket: str
    title: str
    category: str
    location: str
    affected_group: str
    status: str
    area: str | None = None
    scope: str | None = None
    problem_type: str | None = None
    tags: list[str] = []
    created_at: datetime


class DiscoveryOut(BaseModel):
    total: int
    page: int
    limit: int
    pages: int
    items: list[DiscoveryItem]


class TransparencyItem(BaseModel):
    """One card on the public transparency dashboard. Only decided,
    public-safe fields: ticket, classification, approval date, resolution
    and the public remark. Never owner identity, info requests, or notes."""

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


class TransparencyOut(BaseModel):
    total: int
    page: int
    limit: int
    pages: int
    items: list[TransparencyItem]


class TransparencyStats(BaseModel):
    total_approved: int
    challenges: int
    issues: int
    open_challenges: int
    resolved: int


class PublicProblemOut(BaseModel):
    ticket: str
    title: str
    description: str
    category: str
    location: str
    affected_group: str
    severity: str
    desired_solution_type: str
    skills: str | None
    status: str
    area: str | None = None
    scope: str | None = None
    problem_type: str | None = None
    tech_areas: list[str] = []
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime


class SimilarOut(BaseModel):
    ticket: str
    relation: str


class ReviewOut(BaseModel):
    review_number: int
    version_number: int
    provider: str
    model: str
    status: str
    decision: str | None
    reason: str | None
    missing_info: list[str] = []
    understandable: bool | None = None
    sufficient_info: bool | None = None
    solvable: bool | None = None
    duplicate_status: str | None = None
    problem_type: str | None = None
    affected_group: str | None = None
    geo_context: str | None = None
    category: str | None = None
    scope: str | None = None
    tech_areas: list[str] = []
    tags: list[str] = []
    similar: list[SimilarOut] = []
    error_detail: str | None = None
    created_at: datetime
