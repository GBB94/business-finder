from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from app.database import Base


class ApprovalGrant(Base):
    __tablename__ = "approval_grants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    launch_id = Column(String(36), ForeignKey("launch_instances.id"), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)
    channel_or_provider = Column(String(100), nullable=True)
    granted_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    granted_by = Column(String(36), nullable=False)  # always founder user_id
    original_task_id = Column(String(36), ForeignKey("agent_tasks.id"), nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoke_reason = Column(String(500), nullable=True)

    launch_instance = relationship("LaunchInstance", back_populates="approval_grants")
