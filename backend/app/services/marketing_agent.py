"""Marketing agent for LaunchPad: cold email, social, and content generation.

All marketing tasks are manual-trigger only in Phase 2. The agent generates
drafts and plans; sending/publishing requires approval gates.

Smartlead handles cold outbound (mailbox-centric). ShellMail handles product
support inbound. Resend handles transactional email.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_task import AgentTask
from app.models.marketing_campaign import MarketingCampaign
from app.models.campaign_prospect import CampaignProspect

logger = logging.getLogger(__name__)

# Bump this when the cold-email prompt changes so we can trace which version
# generated a given sequence. Stored on the campaign's OperationalEvent.
EMAIL_SEQUENCE_PROMPT_VERSION = "v1"

# ---------------------------------------------------------------------------
# Audience-aware compliance classification
# ---------------------------------------------------------------------------

# Hard-block countries where cold outbound is illegal without explicit consent
_HARD_BLOCK_COUNTRIES: set[str] = {"DE", "AT", "CA"}


def classify_campaign(
    audience_type: str | None,
    countries: list[str | None],
) -> dict:
    """Audience-type-aware classification.

    Returns {"allowed": bool, "classification": str, "requirements": [...],
             "warnings": [...], "compliance_blocks": [...]}

    Hard blocks:
      - consumer_international: always blocked (no cold outbound to consumers outside US)
      - b2b + DE/AT/CA: blocked for those prospects (UWG/CASL)
    """
    from app.services.compliance_gate import classify_campaign_prospects, classify_country

    # Consumer international is always blocked
    if audience_type == "consumer_international":
        return {
            "allowed": False,
            "classification": "consumer_international_block",
            "requirements": [],
            "warnings": ["Cold outbound to international consumers is not allowed."],
            "compliance_blocks": [{"country": "ALL", "reason": "consumer_international"}],
        }

    compliance = classify_campaign_prospects(countries)
    blocks = []

    for cc in countries:
        if cc:
            result = classify_country(cc)
            if not result.allowed:
                blocks.append({"country": cc, "reason": result.warnings[0] if result.warnings else "hard_block"})

    return {
        "allowed": compliance.allowed or len(blocks) < len(countries),  # allowed if any prospects pass
        "classification": compliance.classification,
        "requirements": compliance.requirements,
        "warnings": compliance.warnings,
        "compliance_blocks": blocks,
    }


# ---------------------------------------------------------------------------
# Cold email drafting
# ---------------------------------------------------------------------------


async def draft_cold_emails(
    idea_name: str,
    idea_audience: str,
    idea_problem: str,
    idea_solution: str,
    prospect_count: int = 5,
    model: str | None = None,
) -> dict:
    """Generate personalized cold email drafts for an idea.

    Returns a dict with drafts, subject lines, and token usage.
    """
    model = model or settings.CLAUDE_MODEL_HAIKU

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": (
                    f"You are a cold email specialist. Generate {prospect_count} cold email drafts "
                    f"for the following product:\n\n"
                    f"Product: {idea_name}\n"
                    f"Target Audience: {idea_audience}\n"
                    f"Problem it solves: {idea_problem}\n"
                    f"Solution: {idea_solution}\n\n"
                    f"For each email, provide:\n"
                    f"1. A compelling subject line (under 50 chars)\n"
                    f"2. The email body (3-5 sentences, personalization placeholders like {{first_name}}, {{company}})\n"
                    f"3. A clear CTA\n\n"
                    f"Return as a JSON object with a 'drafts' array, each item having "
                    f"'subject', 'body', and 'cta' fields. Keep the tone professional but conversational. "
                    f"No hype words. Focus on the problem, not the product."
                ),
            }
        ],
    )

    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return {
        "raw_response": response.content[0].text,
        "tokens_used": tokens_used,
        "model_version": model,
        "prompt_version": EMAIL_SEQUENCE_PROMPT_VERSION,
        "draft_count": prospect_count,
    }


async def draft_cold_email_campaign(
    idea_name: str,
    idea_audience: str,
    idea_problem: str,
    idea_solution: str,
    prospects: list[dict],
    model: str | None = None,
) -> dict:
    """Generate a 3-step email sequence for a cold outbound campaign.

    The sequence follows the spec rules:
      - Step 1 (day 0): Problem-focused intro, no product pitch
      - Step 2 (day 3): Value-add follow-up with a relevant insight
      - Step 3 (day 7): Soft close with a specific ask (15-min call, free trial, etc.)

    All steps include {{first_name}} and {{company}} placeholders for Smartlead merge.
    """
    model = model or settings.CLAUDE_MODEL_HAIKU

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=model,
        max_tokens=3072,
        messages=[
            {
                "role": "user",
                "content": (
                    "You are a B2B cold email specialist. Write a 3-email sequence.\n\n"
                    f"Product: {idea_name}\n"
                    f"Audience: {idea_audience}\n"
                    f"Problem: {idea_problem}\n"
                    f"Solution: {idea_solution}\n\n"
                    "Rules:\n"
                    "- Email 1 (Day 0): Focus on the prospect's problem. No product pitch. "
                    "Ask if they experience this pain point. Use {{first_name}} and {{company}} placeholders.\n"
                    "- Email 2 (Day 3): Share a relevant insight or data point that relates to the problem. "
                    "Briefly mention your solution as one option.\n"
                    "- Email 3 (Day 7): Soft close. Suggest a specific, low-friction next step "
                    "(15-min call, free trial link, short demo video).\n\n"
                    "Each email: subject line under 50 chars, body 3-5 sentences, professional but conversational tone.\n"
                    "No hype words, no emoji, no 'just following up'.\n\n"
                    "Return as JSON:\n"
                    '{"sequences": [\n'
                    '  {"seq_number": 1, "seq_delay_days": 0, "subject": "...", "email_body": "..."},\n'
                    '  {"seq_number": 2, "seq_delay_days": 3, "subject": "...", "email_body": "..."},\n'
                    '  {"seq_number": 3, "seq_delay_days": 7, "subject": "...", "email_body": "..."}\n'
                    "]}"
                ),
            }
        ],
    )

    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return {
        "raw_response": response.content[0].text,
        "tokens_used": tokens_used,
        "model_version": model,
        "prompt_version": EMAIL_SEQUENCE_PROMPT_VERSION,
        "sequence_steps": 3,
    }


async def draft_social_post(
    idea_name: str,
    idea_audience: str,
    idea_problem: str,
    idea_solution: str,
    platform: str = "twitter",
    milestone: str | None = None,
    model: str | None = None,
) -> dict:
    """Generate a social media post draft.

    Returns a dict with the draft post and token usage.
    """
    model = model or settings.CLAUDE_MODEL_HAIKU

    platform_rules = {
        "twitter": "Max 280 characters. No hashtag spam (1-2 max). Thread format OK.",
        "linkedin": "Professional tone. 1-3 paragraphs. Can be longer.",
    }

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Write a {platform} post for:\n\n"
                    f"Product: {idea_name}\n"
                    f"Audience: {idea_audience}\n"
                    f"Problem: {idea_problem}\n"
                    f"Solution: {idea_solution}\n"
                    f"{f'Milestone/context: {milestone}' if milestone else ''}\n\n"
                    f"Platform rules: {platform_rules.get(platform, 'Keep it concise.')}\n\n"
                    f"Return as JSON with 'post' (the text) and 'notes' (any suggestions). "
                    f"Tone: authentic, not corporate. No emoji overload."
                ),
            }
        ],
    )

    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return {
        "raw_response": response.content[0].text,
        "tokens_used": tokens_used,
        "model_version": model,
        "platform": platform,
    }


async def write_content(
    idea_name: str,
    idea_audience: str,
    idea_problem: str,
    idea_solution: str,
    content_type: str = "blog_post",
    topic: str | None = None,
    model: str | None = None,
) -> dict:
    """Generate marketing content (blog post, landing page copy, etc.).

    Returns a dict with the content and token usage.
    """
    model = model or settings.CLAUDE_MODEL

    content_prompts = {
        "blog_post": "Write a blog post (800-1200 words) that addresses a pain point the target audience has.",
        "landing_page": "Write landing page copy: hero headline, subheadline, 3 benefit sections, CTA.",
        "faq": "Write 8-10 FAQ entries covering common questions about this product.",
        "email_sequence": "Write a 3-email welcome sequence for new signups.",
    }

    prompt = content_prompts.get(content_type, f"Write {content_type} content.")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Product: {idea_name}\n"
                    f"Audience: {idea_audience}\n"
                    f"Problem: {idea_problem}\n"
                    f"Solution: {idea_solution}\n"
                    f"{f'Topic: {topic}' if topic else ''}\n\n"
                    f"{prompt}\n\n"
                    f"Return as JSON with 'title', 'content', and 'meta_description' fields."
                ),
            }
        ],
    )

    tokens_used = response.usage.input_tokens + response.usage.output_tokens

    return {
        "raw_response": response.content[0].text,
        "tokens_used": tokens_used,
        "model_version": model,
        "content_type": content_type,
    }


# ---------------------------------------------------------------------------
# Campaign lifecycle (Smartlead-backed)
# ---------------------------------------------------------------------------


async def classify_and_create_campaign(
    db: Session,
    *,
    idea_id: str,
    user_id: str,
    launch_id: str | None,
    campaign_name: str,
    channel: str = "cold_email",
    audience_type: str | None = None,
    prospects: list[dict],
) -> dict:
    """Create a campaign after running compliance gate and suppression screening.

    Each prospect dict: {"email", "first_name", "last_name", "company", "country",
                         "personalization_context", "source"}

    Steps:
      1. Audience-aware compliance classification
      2. Per-prospect country blocking (UWG/CASL hard blocks)
      3. Suppression screening (per-tenant)
      4. Create MarketingCampaign + CampaignProspect rows
      5. Return summary (not yet sent to Smartlead, needs approval)
    """
    from app.services.compliance_gate import classify_country
    from app.services.suppression_service import bulk_screen, normalize_email

    # Step 1: Audience-aware classification
    countries = [p.get("country") for p in prospects]
    classification = classify_campaign(audience_type, countries)

    # If entire audience type is blocked, create a blocked campaign
    if not classification["allowed"] and classification.get("classification") == "consumer_international_block":
        campaign = MarketingCampaign(
            idea_id=idea_id,
            user_id=user_id,
            launch_id=launch_id,
            name=campaign_name,
            channel=channel,
            audience_type=audience_type,
            status="blocked",
            cold_email_allowed=False,
            compliance_blocks=classification["compliance_blocks"],
            target_countries=list(set(c for c in countries if c)),
            total_prospects=0,
        )
        db.add(campaign)
        db.flush()
        return {
            "campaign_id": campaign.id,
            "status": "blocked",
            "classification": classification["classification"],
            "requirements": classification["requirements"],
            "warnings": classification["warnings"],
            "total_eligible": 0,
            "blocked_uwg": len(prospects),
            "suppressed": 0,
        }

    # Step 2: Screen individual prospects by country
    blocked_prospects: list[dict] = []
    eligible_prospects: list[dict] = []

    for p in prospects:
        country_result = classify_country(p.get("country"))
        if not country_result.allowed:
            blocked_prospects.append({**p, "block_reason": "uwg_hard_block"})
        else:
            eligible_prospects.append(p)

    # Step 3: Suppression screening (scoped to this user)
    emails_to_check = [p["email"] for p in eligible_prospects if p.get("email")]
    suppressed_emails = bulk_screen(db, user_id, emails_to_check)

    final_prospects: list[dict] = []
    suppressed_prospects: list[dict] = []

    for p in eligible_prospects:
        if normalize_email(p.get("email", "")) in suppressed_emails:
            suppressed_prospects.append({**p, "block_reason": "suppressed"})
        else:
            final_prospects.append(p)

    # Step 4: Create campaign
    unique_countries = list(set(c for c in countries if c))
    campaign = MarketingCampaign(
        idea_id=idea_id,
        user_id=user_id,
        launch_id=launch_id,
        name=campaign_name,
        channel=channel,
        audience_type=audience_type,
        status="draft",
        cold_email_allowed=True,
        target_countries=unique_countries,
        compliance_blocks=classification["compliance_blocks"] if classification["compliance_blocks"] else None,
        suppression_list_screened=True,
        audience_type_confirmed=bool(audience_type),
        total_prospects=len(final_prospects),
    )
    db.add(campaign)
    db.flush()

    # Step 5: Create prospect rows
    for p in final_prospects:
        prospect = CampaignProspect(
            campaign_id=campaign.id,
            launch_id=launch_id,
            email=normalize_email(p.get("email", "")),
            first_name=p.get("first_name"),
            last_name=p.get("last_name"),
            company=p.get("company"),
            country=p.get("country"),
            personalization_context=p.get("personalization_context"),
            source=p.get("source", "manual"),
            status="pending",
        )
        db.add(prospect)

    db.flush()

    return {
        "campaign_id": campaign.id,
        "status": "draft",
        "classification": classification["classification"],
        "requirements": classification["requirements"],
        "warnings": classification["warnings"],
        "total_eligible": len(final_prospects),
        "blocked_uwg": len(blocked_prospects),
        "suppressed": len(suppressed_prospects),
    }


# ---------------------------------------------------------------------------
# Compliance checklist flags
# ---------------------------------------------------------------------------

_REQUIRED_CHECKLIST_FLAGS = [
    "dns_authenticated",
    "dmarc_policy",
    "domain_warmup_complete",
    "list_unsubscribe_header_active",
    "physical_address_included",
    "unsubscribe_link_verified",
    "audience_type_confirmed",
    "suppression_list_screened",
]


def verify_compliance_checklist(campaign: MarketingCampaign) -> list[str]:
    """Return list of failing checklist flags. Empty means all pass."""
    failures = []
    for flag in _REQUIRED_CHECKLIST_FLAGS:
        if not getattr(campaign, flag, False):
            failures.append(flag)
    return failures


async def run_cold_email_campaign(
    db: Session,
    campaign_id: str,
) -> dict:
    """Pre-activation verification for a cold email campaign.

    Checks:
      1. All 8 compliance checklist flags are True
      2. smartlead_email_account_id is set (mailbox bound)
      3. Campaign is in draft status
      4. cold_email_allowed is True

    Returns a dict with pass/fail status and any missing flags.
    This is called by the step handler before pushing to Smartlead.
    """
    campaign = db.query(MarketingCampaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    errors: list[str] = []

    if campaign.status != "draft":
        errors.append(f"Campaign must be in draft status, got '{campaign.status}'")

    if not campaign.cold_email_allowed:
        errors.append("Cold email is not allowed for this campaign (compliance block)")

    if not campaign.smartlead_email_account_id:
        errors.append("No sending mailbox bound (smartlead_email_account_id is empty)")

    checklist_failures = verify_compliance_checklist(campaign)
    if checklist_failures:
        errors.append(f"Compliance checklist failures: {', '.join(checklist_failures)}")

    return {
        "campaign_id": campaign_id,
        "ready": len(errors) == 0,
        "errors": errors,
        "checklist_failures": checklist_failures if checklist_failures else [],
    }


async def activate_campaign_on_smartlead(
    db: Session,
    campaign_id: str,
    sequences: list[dict],
    *,
    skip_start: bool = False,
) -> dict:
    """Push a draft campaign to Smartlead.

    When called from the step handler, ``skip_start=True`` so the handler
    can bind the mailbox between campaign creation and campaign start.

    Sequences: [{"seq_number": 1, "subject": "...", "email_body": "...", "seq_delay_days": 0}, ...]

    Steps:
      1. Create Smartlead campaign
      2. Save sequences
      3. Add leads
      4. (optionally) Start campaign
      5. Update local campaign status
    """
    from app.services import smartlead_service as sl

    campaign = db.query(MarketingCampaign).filter_by(id=campaign_id).first()
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")
    if campaign.status != "draft":
        raise ValueError(f"Campaign must be in draft status, got {campaign.status}")

    # 1. Create on Smartlead
    sl_campaign = await sl.create_campaign(campaign.name)
    sl_campaign_id = sl_campaign.get("id")
    if not sl_campaign_id:
        raise RuntimeError("Smartlead did not return a campaign ID")

    campaign.provider_campaign_id = str(sl_campaign_id)

    # 2. Save sequences
    await sl.save_campaign_sequence(sl_campaign_id, sequences)

    # 3. Add leads
    prospects = (
        db.query(CampaignProspect)
        .filter_by(campaign_id=campaign_id, status="pending")
        .all()
    )
    if prospects:
        lead_list = []
        for p in prospects:
            lead = {"email": p.email}
            if p.first_name:
                lead["first_name"] = p.first_name
            if p.last_name:
                lead["last_name"] = p.last_name
            if p.company:
                lead["company_name"] = p.company
            lead_list.append(lead)

        result = await sl.add_leads_to_campaign(sl_campaign_id, lead_list)
        # Update provider IDs if returned
        uploaded = result.get("uploaded_leads") or result.get("data") or []
        email_to_id = {
            l.get("email", "").lower(): str(l.get("id", ""))
            for l in uploaded if l.get("id")
        }
        for p in prospects:
            pid = email_to_id.get(p.email)
            if pid:
                p.provider_lead_id = pid

    # 4. Start campaign (unless caller will handle start after binding mailbox)
    if not skip_start:
        await sl.update_campaign_status(sl_campaign_id, "START")
        campaign.status = "active"

    db.flush()

    return {
        "campaign_id": campaign.id,
        "provider_campaign_id": str(sl_campaign_id),
        "status": campaign.status,
        "prospects_uploaded": len(prospects),
    }
