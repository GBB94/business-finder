from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


SCORING_DIMENSIONS = [
    "problem_severity",
    "market_evidence",
    "revenue_model",
    "distribution_feasibility",
    "purchaser_quality",
    "build_complexity",
    "founder_market_fit",
    "time_to_revenue",
    "founder_constraints",
    "competition_level",
    "defensibility_potential",
]

DEFAULT_WEIGHTS = {
    "problem_severity": 15.0,
    "market_evidence": 12.0,
    "revenue_model": 10.0,
    "distribution_feasibility": 10.0,
    "purchaser_quality": 8.0,
    "build_complexity": 8.0,
    "founder_market_fit": 10.0,
    "time_to_revenue": 8.0,
    "founder_constraints": 7.0,
    "competition_level": 6.0,
    "defensibility_potential": 6.0,
}


def _utcnow():
    return datetime.now(timezone.utc)


class ScoringWeight(Base):
    __tablename__ = "scoring_weights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
