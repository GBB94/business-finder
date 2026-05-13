"""Email suppression list. Cross-campaign enforcement: any send must check this table first.

A suppressed email is never contacted again by any campaign for that user
unless manually removed. Sources: bounces, complaints, unsubscribes, manual adds.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String

from app.database import Base


class EmailSuppression(Base):
    __tablename__ = "email_suppressions"
    __table_args__ = (
        # Per-tenant suppression: unique on (user_id, email) so one user's
        # bounce does not suppress the address for other tenants.
        Index("ix_email_suppressions_user_email", "user_id", "email", unique=True),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String(320), nullable=False)  # normalized lowercase
    reason = Column(String(30), nullable=False)  # bounce, complaint, unsubscribe, manual
    source_provider = Column(String(30), nullable=True)  # smartlead, shellmail, resend, manual
    source_campaign_id = Column(String(36), nullable=True)  # FK to marketing_campaigns.id (nullable for manual)
    provider_event_id = Column(String(255), nullable=True)  # original bounce/complaint event ID
    synced_to_smartlead = Column(Boolean, nullable=False, default=False)
    synced_at = Column(DateTime, nullable=True)
    suppressed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
