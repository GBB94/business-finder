from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

DismissReasonType = Literal[
    "not_my_audience", "too_crowded", "pain_too_weak",
    "already_have_idea", "resurface_later", "other",
]


class CandidateCreate(BaseModel):
    """Founder suggestion for a candidate idea."""
    problem_signal: str = Field(..., min_length=1)
    target_audience: str = Field(..., min_length=1)
    founder_note: Optional[str] = None
    suggested_solution: Optional[str] = None
    auto_scan: bool = False


class CandidateDismiss(BaseModel):
    dismiss_reason: DismissReasonType
    review_note: Optional[str] = None


class CandidateSourcePostResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    source_id: str
    source_type: str
    source_url: str
    subreddit: Optional[str]
    title: str
    relevance_score: Optional[int]
    engagement_score: int
    sentiment: Optional[str]
    content_purged: bool
    ingested_at: datetime


class CandidateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    user_id: str
    source: str
    status: str
    problem_signal: str
    target_audience: str
    pain_intensity_score: Optional[float]
    pain_type: Optional[str]
    evidence_summary: Optional[str]
    source_communities: Optional[list]
    cross_community: bool
    spending_signals: Optional[list]
    competitor_mentions: Optional[list]
    competition_signal: Optional[str]
    raw_themes: Optional[list]
    sample_post_count: int
    prompt_version: Optional[str]
    model_version: Optional[str]
    founder_note: Optional[str]
    suggested_solution: Optional[str]
    scan_job_id: Optional[str]
    promoted_idea_id: Optional[str]
    review_note: Optional[str]
    dismiss_reason: Optional[str]
    derived_content_purged: bool
    reviewed_at: Optional[datetime]
    created_at: datetime


class CandidateDetailResponse(CandidateResponse):
    source_posts: list[CandidateSourcePostResponse] = []


class CandidateListResponse(BaseModel):
    items: list[CandidateResponse]
    total: int
