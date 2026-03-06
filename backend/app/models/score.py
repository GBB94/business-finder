from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Float, Integer, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("idea_id", "user_id", name="uq_score_idea_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id: Mapped[str] = mapped_column(String(36), ForeignKey("ideas.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # 11 scoring dimensions: score (1-5) + note
    problem_severity_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    problem_severity_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    market_evidence_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    market_evidence_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    revenue_model_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    revenue_model_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    distribution_feasibility_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    distribution_feasibility_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    purchaser_quality_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    purchaser_quality_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    build_complexity_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    build_complexity_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    founder_market_fit_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    founder_market_fit_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    time_to_revenue_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_to_revenue_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    founder_constraints_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    founder_constraints_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    competition_level_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    competition_level_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    defensibility_potential_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    defensibility_potential_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    weighted_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    disqualifiers_checked: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    scored_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    idea = relationship("Idea", back_populates="scores")
