"""Campaign prospect model. Individual contacts within a Smartlead campaign."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class CampaignProspect(Base):
    __tablename__ = "campaign_prospects"
    __table_args__ = (
        # Prevent adding the same email to the same campaign twice
        Index("ix_campaign_prospect_email", "campaign_id", "email", unique=True),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    campaign_id = Column(
        String(36), ForeignKey("marketing_campaigns.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    launch_id = Column(String(36), ForeignKey("launch_instances.id"), nullable=True, index=True)
    email = Column(String(320), nullable=False)  # normalized lowercase
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    company = Column(String(255), nullable=True)
    country = Column(String(2), nullable=True)  # ISO 3166-1 alpha-2
    personalization_context = Column(String(2000), nullable=True)  # freeform context for Claude
    source = Column(String(30), nullable=True)  # apollo, manual, csv_import
    provider_lead_id = Column(String(100), nullable=True)  # Smartlead lead ID

    status = Column(String(20), nullable=False, default="pending")
    # pending, suppressed, sent, delivered, bounced, replied, unsubscribed

    sequence_step = Column(Integer, nullable=False, default=1)  # current step in email sequence
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    bounced_at = Column(DateTime, nullable=True)
    reply_promoted_to_evidence = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    campaign = relationship("MarketingCampaign", back_populates="prospects")
