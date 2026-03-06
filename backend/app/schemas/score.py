from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


from typing import Literal

ScoringDimensionType = Literal[
    "problem_severity", "market_evidence", "revenue_model",
    "distribution_feasibility", "purchaser_quality", "build_complexity",
    "founder_market_fit", "time_to_revenue", "founder_constraints",
    "competition_level", "defensibility_potential",
]


class DimensionScoreInput(BaseModel):
    dimension: ScoringDimensionType
    score: int = Field(..., ge=1, le=5)
    note: Optional[str] = None


class ScoreCreate(BaseModel):
    dimensions: list[DimensionScoreInput]


class ScoreUpdate(BaseModel):
    dimensions: list[DimensionScoreInput]


class DimensionScoreResponse(BaseModel):
    dimension: str
    score: Optional[int]
    note: Optional[str]
    weight: float
    weighted_contribution: Optional[float]
    auto_computed: bool = False


class ScoreResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    idea_id: str
    user_id: str
    weighted_total: Optional[float]
    disqualifiers_checked: Optional[list]
    scored_at: datetime
    updated_at: datetime
    dimensions: list[DimensionScoreResponse] = []


class SynthesizeRequest(BaseModel):
    dimension: str


class SynthesisResponse(BaseModel):
    dimension: str
    summary: str
    key_findings: list[str]
    evidence_cited: list[str]
    gaps: str
    model_version: str


class InconsistencyItem(BaseModel):
    dimension: str
    severity: str
    message: str
    evidence_ids: list[str] = []


class ConsistencyResponse(BaseModel):
    inconsistencies: list[InconsistencyItem]
    overall_assessment: str
    model_version: str
