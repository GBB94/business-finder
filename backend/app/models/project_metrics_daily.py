from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class ProjectMetricsDaily(Base):
    __tablename__ = "project_metrics_daily"
    __table_args__ = (
        UniqueConstraint("launch_id", "date", name="uq_project_metrics_daily_launch_date"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    launch_id = Column(String(36), ForeignKey("launch_instances.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    signups = Column(Integer, default=0)
    active_users = Column(Integer, default=0)
    activation_count = Column(Integer, default=0)
    activation_rate = Column(Float, nullable=True)
    revenue_cents = Column(Integer, default=0)
    ad_spend_cents = Column(Integer, default=0)
    ai_cost_cents = Column(Integer, default=0)
    total_spend_cents = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    support_tickets_received = Column(Integer, default=0)
    uptime_pct = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    launch_instance = relationship("LaunchInstance", back_populates="project_metrics_daily")
