"""Pydantic schemas for marketing campaigns and prospects."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Campaign schemas
# ---------------------------------------------------------------------------


class ProspectInput(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    country: Optional[str] = None  # ISO 3166-1 alpha-2
    personalization_context: Optional[str] = None
    source: Optional[str] = None  # apollo, manual, csv_import


class CampaignCreate(BaseModel):
    idea_id: str
    name: str = Field(..., max_length=255)
    channel: str = "cold_email"  # cold_email, social
    audience_type: Optional[str] = None  # b2b, consumer, consumer_international
    prospects: list[ProspectInput] = Field(..., min_length=1)


class SequenceStep(BaseModel):
    seq_number: int = 1
    subject: str
    email_body: str
    seq_delay_days: int = 0


class CampaignActivate(BaseModel):
    sequences: list[SequenceStep] = Field(..., min_length=1)


class ProspectResponse(BaseModel):
    id: str
    campaign_id: str
    launch_id: Optional[str] = None
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    country: Optional[str] = None
    personalization_context: Optional[str] = None
    source: Optional[str] = None
    provider_lead_id: Optional[str] = None
    status: str
    sequence_step: int
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    bounced_at: Optional[datetime] = None
    reply_promoted_to_evidence: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignResponse(BaseModel):
    id: str
    idea_id: str
    user_id: str
    launch_id: Optional[str] = None
    name: str
    channel: str
    status: str
    audience_type: Optional[str] = None
    target_countries: Optional[list[str]] = None
    cold_email_allowed: bool = True
    compliance_blocks: Optional[list[dict]] = None

    # Provider
    provider: str
    provider_campaign_id: Optional[str] = None
    smartlead_email_account_id: Optional[str] = None
    daily_limit: int = 20
    sequence_steps: int = 3

    # Stats
    total_prospects: int
    total_sent: int
    total_delivered: int
    total_bounced: int
    total_replied: int
    total_unsubscribed: int

    # Compliance checklist
    dns_authenticated: bool = False
    dmarc_policy: bool = False
    domain_warmup_complete: bool = False
    list_unsubscribe_header_active: bool = False
    commercial_ad_disclosure_present: bool = False
    physical_address_included: bool = False
    unsubscribe_link_verified: bool = False
    audience_type_confirmed: bool = False
    suppression_list_screened: bool = False

    # Approval
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None

    # Social
    platforms: Optional[list[str]] = None
    post_content: Optional[str] = None
    scheduled_at: Optional[datetime] = None

    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CampaignChecklistUpdate(BaseModel):
    dns_authenticated: Optional[bool] = None
    dmarc_policy: Optional[bool] = None
    domain_warmup_complete: Optional[bool] = None
    list_unsubscribe_header_active: Optional[bool] = None
    commercial_ad_disclosure_present: Optional[bool] = None
    physical_address_included: Optional[bool] = None
    unsubscribe_link_verified: Optional[bool] = None
    audience_type_confirmed: Optional[bool] = None
    suppression_list_screened: Optional[bool] = None


class CampaignDetailResponse(CampaignResponse):
    prospects: list[ProspectResponse] = []


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int


class CampaignCreateResult(BaseModel):
    campaign_id: str
    status: str
    classification: str
    requirements: list[str]
    warnings: list[str]
    total_eligible: int
    blocked_uwg: int
    suppressed: int


# ---------------------------------------------------------------------------
# Suppression schemas
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Draft trigger schemas
# ---------------------------------------------------------------------------


class ColdEmailDraftRequest(BaseModel):
    idea_id: str
    prospects: list[ProspectInput] = Field(default_factory=list)


class SocialDraftRequest(BaseModel):
    idea_id: str
    platform: str = "twitter"  # twitter, linkedin
    milestone: Optional[str] = None


class DraftResponse(BaseModel):
    raw_response: str
    tokens_used: int
    model_version: str
    prompt_version: Optional[str] = None


# ---------------------------------------------------------------------------
# Prospect add schemas
# ---------------------------------------------------------------------------


class ProspectAddRequest(BaseModel):
    prospects: list[ProspectInput] = Field(..., min_length=1)


class ProspectAddResult(BaseModel):
    added: int
    suppressed: int
    duplicates: int


# ---------------------------------------------------------------------------
# Reply schemas
# ---------------------------------------------------------------------------


class ReplyListResponse(BaseModel):
    items: list[dict]
    total: int


class ReplyPromoteRequest(BaseModel):
    evidence_type: str = "campaign_reply"
    notes: Optional[str] = None


class ReplySendRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)


# ---------------------------------------------------------------------------
# Suppression schemas
# ---------------------------------------------------------------------------


class SuppressionAdd(BaseModel):
    email: str
    reason: str = "manual"  # manual, bounce, complaint, unsubscribe


class SuppressionResponse(BaseModel):
    id: str
    email: str
    reason: str
    source_provider: Optional[str] = None
    source_campaign_id: Optional[str] = None
    synced_to_smartlead: bool = False
    suppressed_at: datetime

    model_config = {"from_attributes": True}


class SuppressionListResponse(BaseModel):
    items: list[SuppressionResponse]
    total: int
