from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

MetricCategoryType = Literal["retention", "economics"]


class MetricEntryCreate(BaseModel):
    category: MetricCategoryType
    metric_key: str = Field(..., min_length=1, max_length=50)
    value: float
    sample_size: Optional[int] = None
    period_start: date
    period_end: date
    note: Optional[str] = None


class MetricEntryResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    idea_id: str
    user_id: str
    category: str
    metric_key: str
    value: float
    sample_size: Optional[int]
    period_start: date
    period_end: date
    note: Optional[str]
    created_at: datetime
    updated_at: datetime


class MetricEntryListResponse(BaseModel):
    items: list[MetricEntryResponse]
    total: int


class MetricWithBenchmark(BaseModel):
    metric_key: str
    label: str
    unit: str
    category: str
    latest_value: Optional[float] = None
    sample_size: Optional[int] = None
    benchmark_value: Optional[float] = None
    benchmark_direction: Optional[str] = None  # "floor" or "ceiling"
    passes_benchmark: Optional[bool] = None
    history: list[MetricEntryResponse] = []


class ComputedMetric(BaseModel):
    metric_key: str
    label: str
    unit: str
    value: Optional[float] = None
    note: Optional[str] = None


class TriggerState(BaseModel):
    key: str
    label: str
    category: str  # "hard" or "soft"
    state: str  # "grey", "yellow", "red"
    fired: bool
    metric_key: Optional[str] = None


class MetricsDashboardResponse(BaseModel):
    retention_metrics: list[MetricWithBenchmark]
    economics_metrics: list[MetricWithBenchmark]
    computed_metrics: list[ComputedMetric]
    trigger_states: list[TriggerState]
