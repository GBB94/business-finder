"""Marketing campaign model. Tracks Smartlead cold outbound campaigns per idea."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.database import Base


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id = Column(String(36), ForeignKey("ideas.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    launch_id = Column(String(36), ForeignKey("launch_instances.id"), nullable=True, index=True)

    name = Column(String(255), nullable=False)
    channel = Column(String(30), nullable=False, default="cold_email")  # cold_email, social
    status = Column(String(20), nullable=False, default="draft")
    # draft, pending_approval, approved, active, paused, completed, blocked

    # Audience & compliance classification
    audience_type = Column(String(30), nullable=True)  # b2b, consumer, consumer_international
    target_countries = Column(JSON, nullable=True)  # ["US", "GB", ...]
    cold_email_allowed = Column(Boolean, nullable=False, default=True)
    compliance_blocks = Column(JSON, nullable=True)  # [{country, reason}, ...]

    # Smartlead integration
    provider = Column(String(30), nullable=False, default="smartlead")
    provider_campaign_id = Column(String(100), nullable=True)  # Smartlead campaign ID
    smartlead_email_account_id = Column(String(100), nullable=True)  # bound mailbox
    daily_limit = Column(Integer, nullable=False, default=20)
    sequence_steps = Column(Integer, nullable=False, default=3)

    # Campaign stats
    total_prospects = Column(Integer, nullable=False, default=0)
    total_sent = Column(Integer, nullable=False, default=0)
    total_delivered = Column(Integer, nullable=False, default=0)
    total_bounced = Column(Integer, nullable=False, default=0)
    total_replied = Column(Integer, nullable=False, default=0)
    total_unsubscribed = Column(Integer, nullable=False, default=0)

    # Compliance / deliverability checklist
    dns_authenticated = Column(Boolean, nullable=False, default=False)
    dmarc_policy = Column(Boolean, nullable=False, default=False)
    domain_warmup_complete = Column(Boolean, nullable=False, default=False)
    list_unsubscribe_header_active = Column(Boolean, nullable=False, default=False)
    commercial_ad_disclosure_present = Column(Boolean, nullable=False, default=False)
    physical_address_included = Column(Boolean, nullable=False, default=False)
    unsubscribe_link_verified = Column(Boolean, nullable=False, default=False)
    audience_type_confirmed = Column(Boolean, nullable=False, default=False)
    suppression_list_screened = Column(Boolean, nullable=False, default=False)

    # Approval (mirrors AgentTask approval pattern)
    approval_token_hash = Column(String(64), nullable=True)
    approval_artifact_id = Column(String(255), nullable=True)
    approval_expires_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String(500), nullable=True)
    grant_id = Column(String(36), nullable=True)

    # Social (for channel="social" campaigns)
    platforms = Column(JSON, nullable=True)  # ["twitter", "linkedin"]
    post_content = Column(String(5000), nullable=True)
    scheduled_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))

    prospects = relationship("CampaignProspect", back_populates="campaign", cascade="all, delete-orphan")
