from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

WatchlistSourceType = Literal["subreddit", "hn_ask", "hn_show", "hn_tag"]


class WatchlistEntryCreate(BaseModel):
    source_type: WatchlistSourceType
    source_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    scan_frequency_days: int = Field(7, ge=1, le=30)


class WatchlistEntryUpdate(BaseModel):
    active: Optional[bool] = None
    scan_frequency_days: Optional[int] = Field(None, ge=1, le=30)
    description: Optional[str] = None


class WatchlistEntryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    user_id: str
    source_type: str
    source_name: str
    description: Optional[str]
    active: bool
    scan_frequency_days: int
    last_scanned_at: Optional[datetime]
    created_at: datetime


class WatchlistEntryListResponse(BaseModel):
    items: list[WatchlistEntryResponse]
    total: int
