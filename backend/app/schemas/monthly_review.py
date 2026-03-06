from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

ReviewDecisionType = Literal["continue", "pivot", "kill", "park"]


class MonthlyReviewCreate(BaseModel):
    review_date: date
    metrics_snapshot: Optional[dict] = None
    decision: ReviewDecisionType
    reasoning: Optional[str] = None
    next_hypothesis: Optional[str] = None


class MonthlyReviewResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    idea_id: str
    user_id: str
    review_date: date
    metrics_snapshot: Optional[dict]
    gate_1_status_at_review: Optional[str]
    gate_2_status_at_review: Optional[str]
    gate_3_status_at_review: Optional[str]
    kill_triggers_fired: Optional[list]
    decision: str
    reasoning: Optional[str]
    next_hypothesis: Optional[str]
    created_at: datetime


class MonthlyReviewListResponse(BaseModel):
    items: list[MonthlyReviewResponse]
    total: int


class ReviewSummaryResponse(BaseModel):
    summary: str
    metrics_assessment: str
    trigger_status: str
    key_developments: list[str]
    open_questions: list[str]
    model_version: str
