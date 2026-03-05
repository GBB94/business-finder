from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Date, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import default_user_id
from app.database import Base


class ReviewDecision(str, enum.Enum):
    continue_ = "continue"
    pivot = "pivot"
    kill = "kill"
    park = "park"


def _utcnow():
    return datetime.now(timezone.utc)


class MonthlyReview(Base):
    __tablename__ = "monthly_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id: Mapped[str] = mapped_column(String(36), ForeignKey("ideas.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, default=default_user_id)

    review_date: Mapped[date] = mapped_column(Date, nullable=False)
    metrics_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    gate_1_status_at_review: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    gate_2_status_at_review: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    gate_3_status_at_review: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    kill_triggers_fired: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    decision: Mapped[str] = mapped_column(Enum(ReviewDecision), nullable=False)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_hypothesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    idea = relationship("Idea", back_populates="monthly_reviews")
