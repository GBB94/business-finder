from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


LaunchStatusType = Literal["provisioning", "preview", "active", "paused", "killed"]


class LaunchCreate(BaseModel):
    idea_id: str
    daily_budget_cap: Optional[float] = None


class LaunchUpdate(BaseModel):
    status: Optional[LaunchStatusType] = None
    daily_budget_cap: Optional[float] = None


class LaunchResponse(BaseModel):
    id: str
    idea_id: str
    user_id: str
    status: str
    github_repo_url: Optional[str] = None
    preview_url: Optional[str] = None
    production_url: Optional[str] = None
    secret_ref: Optional[str] = None
    daily_budget_cap: Optional[float] = None
    total_spend_to_date: float
    created_at: datetime
    updated_at: Optional[datetime] = None
    idea_name: Optional[str] = None

    model_config = {"from_attributes": True}


class LaunchListResponse(BaseModel):
    items: list[LaunchResponse]
    total: int


# --- Operational Events ---

class OperationalEventResponse(BaseModel):
    id: str
    launch_id: str
    event_type: str
    payload: Optional[dict] = None
    promoted_to_evidence: bool
    evidence_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OperationalEventListResponse(BaseModel):
    items: list[OperationalEventResponse]
    total: int


# --- Project Metrics Daily ---

class ProjectMetricsDailyResponse(BaseModel):
    id: str
    launch_id: str
    date: date
    signups: int
    active_users: int
    activation_count: int
    activation_rate: Optional[float] = None
    revenue_cents: int
    ad_spend_cents: int
    ai_cost_cents: int
    total_spend_cents: int
    error_count: int
    support_tickets_received: int
    uptime_pct: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectMetricsDailyListResponse(BaseModel):
    items: list[ProjectMetricsDailyResponse]
    total: int


# --- Daily Logs ---

class DailyLogResponse(BaseModel):
    id: str
    launch_id: str
    date: date
    tasks_executed: Optional[list] = None
    metrics_snapshot: Optional[dict] = None
    ceo_reasoning: Optional[str] = None
    anomalies_flagged: Optional[str] = None
    pending_approvals: Optional[list] = None
    next_day_plan: Optional[str] = None
    ai_cost_today: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DailyLogListResponse(BaseModel):
    items: list[DailyLogResponse]
    total: int


# --- Audit Log ---

class AuditLogResponse(BaseModel):
    id: str
    launch_id: Optional[str] = None
    actor: str
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
