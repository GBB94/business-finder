from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Float, Integer, Date, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import default_user_id
from app.database import Base


class MetricCategory(str, enum.Enum):
    retention = "retention"
    economics = "economics"


def _utcnow():
    return datetime.now(timezone.utc)


class MetricEntry(Base):
    __tablename__ = "metric_entries"
    __table_args__ = (
        UniqueConstraint("idea_id", "metric_key", "period_start", name="uq_idea_metric_period"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id: Mapped[str] = mapped_column(String(36), ForeignKey("ideas.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True, default=default_user_id)

    category: Mapped[str] = mapped_column(Enum(MetricCategory), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    sample_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    idea = relationship("Idea", back_populates="metric_entries")
