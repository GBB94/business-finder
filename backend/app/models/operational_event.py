from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, JSON, String, text
from sqlalchemy.orm import relationship

from app.database import Base


class OperationalEvent(Base):
    __tablename__ = "operational_events"
    __table_args__ = (
        # Enforce uniqueness for webhook-delivered events so concurrent retries
        # cannot insert duplicates (provider_event_id is NULL for non-webhook events).
        Index(
            "ix_operational_events_provider_event",
            "launch_id", "provider_event_id",
            unique=True,
            postgresql_where=text("provider_event_id IS NOT NULL"),
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    launch_id = Column(String(36), ForeignKey("launch_instances.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=True)
    provider_event_id = Column(String(255), nullable=True)  # webhook provider's event ID for deduplication
    promoted_to_evidence = Column(Boolean, default=False)
    evidence_id = Column(String(36), ForeignKey("evidence.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    launch_instance = relationship("LaunchInstance", back_populates="operational_events")
