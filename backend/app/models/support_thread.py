"""Support thread model for per-customer conversation tracking.

Each thread groups messages from a single customer email address for a
given launch. The support agent uses thread history to draft contextual
responses and detect escalation conditions.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Boolean
from sqlalchemy.orm import relationship

from app.database import Base


class SupportThread(Base):
    __tablename__ = "support_threads"
    __table_args__ = (
        Index("ix_support_threads_launch_email", "launch_id", "customer_email"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    launch_id = Column(String(36), ForeignKey("launch_instances.id"), nullable=False, index=True)
    customer_email = Column(String(320), nullable=False)
    subject = Column(String(500), nullable=True)

    # Thread status: open, waiting_on_customer, escalated, resolved
    status = Column(String(30), nullable=False, default="open")

    # Messages stored as JSON array: [{direction, body, timestamp, message_id}]
    # direction: "inbound" (customer) or "outbound" (drafted/sent)
    messages = Column(JSON, nullable=False, default=list)

    # AI confidence score for last drafted response (0.0-1.0)
    confidence_score = Column(Float, nullable=True)

    # Escalation tracking
    escalated_at = Column(DateTime, nullable=True)
    escalation_reason = Column(String(500), nullable=True)

    # Feature request extraction
    feature_request_extracted = Column(Boolean, default=False)
    evidence_id = Column(String(36), ForeignKey("evidence.id"), nullable=True)

    # Counts for quick queries
    message_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))

    launch_instance = relationship("LaunchInstance", back_populates="support_threads")
