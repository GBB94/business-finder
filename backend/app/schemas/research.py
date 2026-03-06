from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    queries: list[str] = Field(..., min_length=1, max_length=5)
    sources: list[Literal["hn", "reddit"]] = ["hn", "reddit"]


class ResearchJobResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    idea_id: Optional[str]
    job_type: str
    status: str
    retry_count: int
    input_params: Optional[dict]
    results: Optional[dict]
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class ResearchJobListResponse(BaseModel):
    items: list[ResearchJobResponse]
    total: int


class PurgeRequest(BaseModel):
    older_than_days: int = Field(90, ge=0)
