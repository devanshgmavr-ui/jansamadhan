"""AI provider abstraction. All providers return a validated AIReviewOutput."""

import enum
from typing import Protocol

from pydantic import BaseModel, Field


class AIDecision(str, enum.Enum):
    APPROVED = "APPROVED"
    NEEDS_INFORMATION = "NEEDS_INFORMATION"
    NOT_SOCIETAL = "NOT_SOCIETAL"


class AIArea(str, enum.Enum):
    RURAL = "Rural"
    URBAN = "Urban"
    SEMI_URBAN = "Semi-Urban"
    GENERAL = "General"


class AIScope(str, enum.Enum):
    INDIVIDUAL = "Individual"
    FAMILY = "Family"
    COMMUNITY = "Community"
    INSTITUTION = "Institution"
    ORGANIZATION = "Organization"
    REGIONAL = "Regional"
    NATIONAL = "National"


class DupRelation(str, enum.Enum):
    DUPLICATE = "duplicate"
    SIMILAR = "similar"
    DISTINCT = "distinct"


class SimilarRef(BaseModel):
    ticket: str = Field(min_length=1, max_length=20)
    relation: DupRelation


class AIChecks(BaseModel):
    understandable: bool
    sufficient_info: bool
    solvable: bool
    duplicate_status: DupRelation
    problem_type: str = Field(min_length=2, max_length=60)
    affected_group: str = Field(min_length=2, max_length=120)
    geo_context: AIArea
    category: str = Field(min_length=2, max_length=60)
    tags: list[str] = Field(min_length=1, max_length=8)

    @classmethod
    def _clean_str(cls, v: str, limit: int) -> str:
        return v.strip()[:limit]


class AIReviewOutput(BaseModel):
    checks: AIChecks
    decision: AIDecision
    reason: str = Field(min_length=10, max_length=1000)
    missing_info: list[str] = Field(default_factory=list, max_length=10)
    scope: AIScope
    tech_areas: list[str] = Field(default_factory=list, max_length=6)
    similar: list[SimilarRef] = Field(default_factory=list, max_length=5)


class AIReviewInput(BaseModel):
    ticket: str
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
    candidates: list[dict] = Field(default_factory=list)  # {ticket,title,category}


class AIProviderError(Exception):
    pass


class AIProvider(Protocol):
    name: str

    def review(self, data: AIReviewInput) -> AIReviewOutput: ...
