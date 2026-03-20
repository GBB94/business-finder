from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class DailyLog(Base):
    __tablename__ = "daily_logs"
    __table_args__ = (
        UniqueConstraint("launch_id", "date", name="uq_daily_log_launch_date"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    launch_id = Column(String(36), ForeignKey("launch_instances.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    tasks_executed = Column(JSON, nullable=True)
    metrics_snapshot = Column(JSON, nullable=True)
    ceo_reasoning = Column(Text, nullable=True)
    anomalies_flagged = Column(Text, nullable=True)
    pending_approvals = Column(JSON, nullable=True)
    next_day_plan = Column(Text, nullable=True)
    ai_cost_today = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    launch_instance = relationship("LaunchInstance", back_populates="daily_logs")
