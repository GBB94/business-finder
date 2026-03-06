from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Index
from sqlalchemy.orm import relationship

from app.database import Base


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id = Column(String(36), ForeignKey("ideas.id"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    task_type = Column(String(50), nullable=False)  # community_scan, evidence_synthesis, consistency_check, review_summary
    status = Column(String(20), nullable=False, default="queued")  # queued, claimed, running, completed, failed, dead_letter, cancelled
    priority = Column(Integer, nullable=False, default=0)
    idempotency_key = Column(String(255), unique=True, nullable=True)
    input_params = Column(JSON, nullable=True)
    output = Column(JSON, nullable=True)
    error_message = Column(String(2000), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    claimed_by = Column(String(255), nullable=True)
    claimed_at = Column(DateTime, nullable=True)

    steps = relationship("AgentTaskStep", back_populates="task", cascade="all, delete-orphan", order_by="AgentTaskStep.step_order")


class AgentTaskStep(Base):
    __tablename__ = "agent_task_steps"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    step_name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending, running, completed, failed, skipped
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error_message = Column(String(2000), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    task = relationship("AgentTask", back_populates="steps")
