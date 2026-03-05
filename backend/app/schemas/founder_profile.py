from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FounderProfileUpsert(BaseModel):
    monthly_burn_rate: Optional[float] = None
    current_savings: Optional[float] = None
    runway_floor_months: Optional[int] = None
    available_hours_per_week_building: Optional[int] = None
    available_hours_per_week_selling: Optional[int] = None
    marketing_budget_monthly: Optional[float] = None
    stop_spend_trigger: Optional[str] = None
    skills: Optional[list[str]] = None
    audiences_familiar_with: Optional[list[str]] = None


class FounderProfileResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    user_id: str
    monthly_burn_rate: float
    current_savings: float
    runway_floor_months: int
    available_hours_per_week_building: int
    available_hours_per_week_selling: int
    marketing_budget_monthly: float
    stop_spend_trigger: Optional[str]
    skills: Optional[list]
    audiences_familiar_with: Optional[list]
    updated_at: datetime
    runway_months_remaining: Optional[float] = None
