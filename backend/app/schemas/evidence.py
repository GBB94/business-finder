from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

GateLabelType = Literal["1", "2", "3", "discovery", "scoring"]
EvidenceTypeType = Literal[
    "community_signal", "customer_conversation", "landing_page_metric",
    "pre_sale", "competitor_datapoint", "keyword_data",
    "retention_metric", "financial_metric", "outreach_metric", "note",
]
SourceTypeType = Literal[
    "reddit", "hn", "github", "g2_manual", "capterra_manual",
    "kw_manual", "stripe", "conversation", "note", "other",
]
SentimentType = Literal["positive", "negative", "neutral", "mixed"]


class EvidenceCreate(BaseModel):
    gate: GateLabelType
    evidence_type: EvidenceTypeType
    title: str = Field(..., min_length=1, max_length=500)
    content: Optional[dict] = None
    source_url: Optional[str] = None
    source_type: SourceTypeType = "other"
    sentiment: SentimentType = "neutral"
    tags: Optional[list[str]] = None


class EvidenceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    idea_id: str
    user_id: str
    gate: str
    evidence_type: str
    title: str
    content: Optional[dict]
    content_purged: bool
    source_url: Optional[str]
    source_type: str
    sentiment: str
    created_at: datetime
    tags: Optional[list]


class EvidenceListResponse(BaseModel):
    items: list[EvidenceResponse]
    total: int
