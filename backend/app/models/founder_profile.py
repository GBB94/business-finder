from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Float, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class FounderProfile(Base):
    __tablename__ = "founder_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)

    monthly_burn_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_savings: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    runway_floor_months: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    available_hours_per_week_building: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_hours_per_week_selling: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    marketing_budget_monthly: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stop_spend_trigger: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    skills: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    audiences_familiar_with: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
