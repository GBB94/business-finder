from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import relationship

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    launch_id = Column(String(36), ForeignKey("launch_instances.id"), nullable=True, index=True)  # null for system-level
    actor = Column(String(50), nullable=False)  # system, ceo_agent, engineering_agent, marketing_agent, support_agent, founder
    action = Column(String(50), nullable=False)  # approval_granted, approval_rejected, secret_accessed, deploy_promoted, project_paused, project_resumed, project_killed, budget_changed, manual_override, provider_mutation, task_created, task_failed
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(255), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    launch_instance = relationship("LaunchInstance", back_populates="audit_logs")
