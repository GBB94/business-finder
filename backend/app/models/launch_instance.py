from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import relationship

from app.database import Base


class LaunchInstance(Base):
    __tablename__ = "launch_instances"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id = Column(String(36), ForeignKey("ideas.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="provisioning")  # provisioning, preview, active, paused, killed
    github_repo_url = Column(String(500), nullable=True)
    preview_url = Column(String(500), nullable=True)
    production_url = Column(String(500), nullable=True)
    secret_ref = Column(String(255), nullable=True)  # vault key prefix e.g. "project-{id}"
    daily_budget_cap = Column(Float, nullable=True)
    total_spend_to_date = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))

    operational_events = relationship("OperationalEvent", back_populates="launch_instance", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="launch_instance", cascade="all, delete-orphan")
    daily_logs = relationship("DailyLog", back_populates="launch_instance", cascade="all, delete-orphan")
    approval_grants = relationship("ApprovalGrant", back_populates="launch_instance", cascade="all, delete-orphan")
    project_metrics_daily = relationship("ProjectMetricsDaily", back_populates="launch_instance", cascade="all, delete-orphan")
