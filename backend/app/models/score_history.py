from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Float, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class ScoreHistory(Base):
    """Append-only snapshot of scores. One row created each time a score is saved."""
    __tablename__ = "score_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id: Mapped[str] = mapped_column(String(36), ForeignKey("ideas.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Snapshot of all dimension scores at this point in time
    dimensions_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    weighted_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    snapshot_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
