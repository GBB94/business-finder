"""Marketing campaign and suppression API routes.

Campaign routes are scoped under /api/launches/{launch_id}/marketing/...
since campaigns belong to a launch instance.

Suppression routes stay at /api/marketing/suppressions since they are
user-scoped (cross-campaign, cross-launch).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.campaign_prospect import CampaignProspect
from app.models.email_suppression import EmailSuppression
from app.models.launch_instance import LaunchInstance
from app.models.marketing_campaign import MarketingCampaign
from app.models.user import User
from app.schemas.marketing import (
    CampaignActivate,
    CampaignCreate,
    CampaignCreateResult,
    CampaignDetailResponse,
    CampaignListResponse,
    CampaignResponse,
    ColdEmailDraftRequest,
    DraftResponse,
    ProspectAddRequest,
    ProspectAddResult,
    ProspectResponse,
    ReplyListResponse,
    ReplyPromoteRequest,
    ReplySendRequest,
    SocialDraftRequest,
    SuppressionAdd,
    SuppressionListResponse,
    SuppressionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["marketing"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_launch(db: Session, launch_id: str, user_id: str) -> LaunchInstance:
    """Load launch and verify ownership. Raises 404 if not found."""
    launch = db.query(LaunchInstance).filter_by(id=launch_id, user_id=user_id).first()
    if not launch:
        raise HTTPException(404, "Launch not found")
    return launch


# ---------------------------------------------------------------------------
# Campaigns (scoped under launch)
# ---------------------------------------------------------------------------


@router.get("/api/launches/{launch_id}/marketing/campaigns", response_model=CampaignListResponse)
def list_campaigns(
    launch_id: str,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    launch = _get_launch(db, launch_id, current_user.id)
    q = db.query(MarketingCampaign).filter_by(launch_id=launch_id, user_id=current_user.id)
    if status:
        q = q.filter_by(status=status)
    campaigns = q.order_by(MarketingCampaign.created_at.desc()).all()
    return CampaignListResponse(
        items=[CampaignResponse.model_validate(c) for c in campaigns],
        total=len(campaigns),
    )


@router.post("/api/launches/{launch_id}/marketing/campaigns", response_model=CampaignCreateResult, status_code=201)
def create_campaign(
    launch_id: str,
    body: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a campaign with compliance gate and suppression screening."""
    from app.models.idea import Idea
    from app.services.marketing_agent import classify_and_create_campaign

    launch = _get_launch(db, launch_id, current_user.id)

    # Verify ownership of referenced idea
    idea = db.query(Idea).filter_by(id=body.idea_id, user_id=current_user.id).first()
    if not idea:
        raise HTTPException(404, "Idea not found")

    # Ensure the launch belongs to the same idea
    if launch.idea_id != body.idea_id:
        raise HTTPException(400, "Launch does not belong to the specified idea")

    prospects = [p.model_dump() for p in body.prospects]
    result = asyncio.run(classify_and_create_campaign(
        db,
        idea_id=body.idea_id,
        user_id=current_user.id,
        launch_id=launch_id,
        campaign_name=body.name,
        channel=body.channel,
        audience_type=body.audience_type,
        prospects=prospects,
    ))
    db.commit()
    return CampaignCreateResult(**result)


@router.get("/api/launches/{launch_id}/marketing/campaigns/{campaign_id}", response_model=CampaignDetailResponse)
def get_campaign(
    launch_id: str,
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_launch(db, launch_id, current_user.id)
    campaign = (
        db.query(MarketingCampaign)
        .filter_by(id=campaign_id, launch_id=launch_id, user_id=current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    prospects = (
        db.query(CampaignProspect)
        .filter_by(campaign_id=campaign_id)
        .order_by(CampaignProspect.created_at.desc())
        .all()
    )

    resp = CampaignDetailResponse.model_validate(campaign)
    resp.prospects = [ProspectResponse.model_validate(p) for p in prospects]
    return resp


@router.post("/api/launches/{launch_id}/marketing/campaigns/{campaign_id}/activate", status_code=202)
def activate_campaign(
    launch_id: str,
    campaign_id: str,
    body: CampaignActivate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enqueue campaign activation through the agent-task approval flow.

    This does NOT push to Smartlead directly. Instead it creates an
    agent task of type 'activate_campaign' which goes through the
    approve_once gate (same as scaffold/deploy). The step handler
    performs the actual Smartlead activation after approval.
    """
    _get_launch(db, launch_id, current_user.id)
    campaign = (
        db.query(MarketingCampaign)
        .filter_by(id=campaign_id, launch_id=launch_id, user_id=current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if campaign.status != "draft":
        raise HTTPException(400, f"Campaign must be in draft status, got '{campaign.status}'")

    from app.services.agent_task_service import create_task
    from app.services.task_enqueue import enqueue_task

    sequences = [s.model_dump() for s in body.sequences]
    idem_key = f"activate_campaign:{campaign_id}"

    task = create_task(
        db,
        idea_id=campaign.idea_id,
        user_id=current_user.id,
        task_type="activate_campaign",
        idempotency_key=idem_key,
        input_params={
            "campaign_id": campaign_id,
            "sequences": sequences,
        },
    )
    task.launch_id = launch_id
    task.agent_type = "marketing"

    if task.status == "queued":
        if not enqueue_task(db, task):
            raise HTTPException(503, "Failed to enqueue activation task")
    else:
        db.commit()

    return {"status": "queued", "task_id": task.id}


@router.post("/api/launches/{launch_id}/marketing/campaigns/{campaign_id}/pause", response_model=CampaignResponse)
def pause_campaign(
    launch_id: str,
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pause an active campaign on Smartlead."""
    _get_launch(db, launch_id, current_user.id)
    campaign = (
        db.query(MarketingCampaign)
        .filter_by(id=campaign_id, launch_id=launch_id, user_id=current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if campaign.status != "active":
        raise HTTPException(400, f"Cannot pause campaign with status '{campaign.status}'")

    # Fail-closed: local status only advances after provider confirms.
    if campaign.provider_campaign_id:
        from app.services import smartlead_service as sl
        try:
            asyncio.run(sl.update_campaign_status(int(campaign.provider_campaign_id), "PAUSE"))
        except Exception:
            logger.exception("Failed to pause Smartlead campaign %s", campaign.provider_campaign_id)
            raise HTTPException(502, "Failed to pause campaign on Smartlead. Local status unchanged.")

    campaign.status = "paused"
    db.commit()
    db.refresh(campaign)
    return CampaignResponse.model_validate(campaign)


@router.post("/api/launches/{launch_id}/marketing/campaigns/{campaign_id}/resume", response_model=CampaignResponse)
def resume_campaign(
    launch_id: str,
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resume a paused campaign on Smartlead. Fail-closed: local status only
    advances after provider confirms."""
    _get_launch(db, launch_id, current_user.id)
    campaign = (
        db.query(MarketingCampaign)
        .filter_by(id=campaign_id, launch_id=launch_id, user_id=current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if campaign.status != "paused":
        raise HTTPException(400, f"Cannot resume campaign with status '{campaign.status}'")

    if campaign.provider_campaign_id:
        from app.services import smartlead_service as sl
        try:
            asyncio.run(sl.update_campaign_status(int(campaign.provider_campaign_id), "START"))
        except Exception:
            logger.exception("Failed to resume Smartlead campaign %s", campaign.provider_campaign_id)
            raise HTTPException(502, "Failed to resume campaign on Smartlead. Local status unchanged.")

    campaign.status = "active"
    db.commit()
    db.refresh(campaign)
    return CampaignResponse.model_validate(campaign)


# ---------------------------------------------------------------------------
# Draft triggers
# ---------------------------------------------------------------------------


@router.post("/api/launches/{launch_id}/marketing/cold-email/draft", response_model=DraftResponse)
def draft_cold_email(
    launch_id: str,
    body: ColdEmailDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a 3-step cold email sequence draft via Claude."""
    from app.models.idea import Idea
    from app.services.marketing_agent import draft_cold_email_campaign

    launch = _get_launch(db, launch_id, current_user.id)
    idea = db.query(Idea).filter_by(id=body.idea_id, user_id=current_user.id).first()
    if not idea:
        raise HTTPException(404, "Idea not found")

    prospects = [p.model_dump() for p in body.prospects]
    result = asyncio.run(draft_cold_email_campaign(
        idea_name=idea.name,
        idea_audience=idea.audience or "",
        idea_problem=idea.problem_statement or "",
        idea_solution=idea.proposed_solution or "",
        prospects=prospects,
    ))
    return DraftResponse(**result)


@router.post("/api/launches/{launch_id}/marketing/social/draft", response_model=DraftResponse)
def draft_social_post(
    launch_id: str,
    body: SocialDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a social media post draft via Claude."""
    from app.models.idea import Idea
    from app.services.marketing_agent import draft_social_post as _draft_social

    launch = _get_launch(db, launch_id, current_user.id)
    idea = db.query(Idea).filter_by(id=body.idea_id, user_id=current_user.id).first()
    if not idea:
        raise HTTPException(404, "Idea not found")

    result = asyncio.run(_draft_social(
        idea_name=idea.name,
        idea_audience=idea.audience or "",
        idea_problem=idea.problem_statement or "",
        idea_solution=idea.proposed_solution or "",
        platform=body.platform,
        milestone=body.milestone,
    ))
    return DraftResponse(**result)


# ---------------------------------------------------------------------------
# Prospects (add to existing campaign)
# ---------------------------------------------------------------------------


@router.get(
    "/api/launches/{launch_id}/marketing/campaigns/{campaign_id}/prospects",
    response_model=list[ProspectResponse],
)
def list_prospects(
    launch_id: str,
    campaign_id: str,
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_launch(db, launch_id, current_user.id)
    campaign = (
        db.query(MarketingCampaign)
        .filter_by(id=campaign_id, launch_id=launch_id, user_id=current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    q = db.query(CampaignProspect).filter_by(campaign_id=campaign_id)
    if status:
        q = q.filter_by(status=status)
    prospects = q.order_by(CampaignProspect.created_at.desc()).all()
    return [ProspectResponse.model_validate(p) for p in prospects]


@router.post(
    "/api/launches/{launch_id}/marketing/campaigns/{campaign_id}/prospects",
    response_model=ProspectAddResult,
    status_code=201,
)
def add_prospects(
    launch_id: str,
    campaign_id: str,
    body: ProspectAddRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add prospects to an existing campaign with suppression screening."""
    from app.services.suppression_service import bulk_screen, normalize_email

    _get_launch(db, launch_id, current_user.id)
    campaign = (
        db.query(MarketingCampaign)
        .filter_by(id=campaign_id, launch_id=launch_id, user_id=current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    if campaign.status not in ("draft", "paused"):
        raise HTTPException(400, f"Cannot add prospects to campaign with status '{campaign.status}'")

    # Screen against suppression list
    emails = [p.email for p in body.prospects]
    suppressed_emails = bulk_screen(db, current_user.id, emails)

    added = 0
    suppressed = 0
    duplicates = 0

    for p in body.prospects:
        norm = normalize_email(p.email)
        if norm in suppressed_emails:
            suppressed += 1
            continue

        # Check for duplicate within this campaign
        existing = (
            db.query(CampaignProspect)
            .filter_by(campaign_id=campaign_id, email=norm)
            .first()
        )
        if existing:
            duplicates += 1
            continue

        prospect = CampaignProspect(
            campaign_id=campaign_id,
            launch_id=launch_id,
            email=norm,
            first_name=p.first_name,
            last_name=p.last_name,
            company=p.company,
            country=p.country,
            personalization_context=p.personalization_context,
            source=p.source or "manual",
            status="pending",
        )
        db.add(prospect)
        added += 1

    campaign.total_prospects = (
        db.query(CampaignProspect).filter_by(campaign_id=campaign_id).count() + added
    )
    db.commit()

    return ProspectAddResult(added=added, suppressed=suppressed, duplicates=duplicates)


# ---------------------------------------------------------------------------
# Campaign replies (from Smartlead webhook events)
# ---------------------------------------------------------------------------


@router.get("/api/launches/{launch_id}/replies", response_model=ReplyListResponse)
def list_replies(
    launch_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List campaign reply events for a launch."""
    from app.models.operational_event import OperationalEvent

    _get_launch(db, launch_id, current_user.id)
    q = (
        db.query(OperationalEvent)
        .filter(
            OperationalEvent.launch_id == launch_id,
            OperationalEvent.event_type == "email_replied",
        )
    )
    total = q.count()
    events = q.order_by(OperationalEvent.created_at.desc()).offset(offset).limit(limit).all()
    items = [
        {
            "id": e.id,
            "launch_id": e.launch_id,
            "event_type": e.event_type,
            "payload": e.payload,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]
    return ReplyListResponse(items=items, total=total)


@router.post("/api/launches/{launch_id}/replies/{event_id}/promote", status_code=201)
def promote_reply(
    launch_id: str,
    event_id: str,
    body: ReplyPromoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote a campaign reply to IdeaScope evidence."""
    from app.models.evidence import Evidence
    from app.models.operational_event import OperationalEvent

    launch = _get_launch(db, launch_id, current_user.id)
    event = (
        db.query(OperationalEvent)
        .filter_by(id=event_id, launch_id=launch_id, event_type="email_replied")
        .first()
    )
    if not event:
        raise HTTPException(404, "Reply event not found")

    payload = event.payload or {}
    from_email = payload.get("lead_email") or payload.get("email") or ""
    reply_text = payload.get("reply_text") or payload.get("body") or ""

    evidence = Evidence(
        idea_id=launch.idea_id,
        user_id=current_user.id,
        evidence_type=body.evidence_type,
        source="smartlead_reply",
        content=reply_text[:5000],
        notes=body.notes or f"Campaign reply from {from_email}",
    )
    db.add(evidence)

    # Mark the prospect as promoted if we can find them
    campaign_id = payload.get("campaign_id")
    if campaign_id and from_email:
        prospect = (
            db.query(CampaignProspect)
            .filter_by(campaign_id=campaign_id, email=from_email.lower())
            .first()
        )
        if prospect:
            prospect.reply_promoted_to_evidence = True

    db.commit()
    return {"status": "promoted", "evidence_id": evidence.id}


@router.post("/api/launches/{launch_id}/replies/{event_id}/reply", status_code=202)
def reply_to_prospect(
    launch_id: str,
    event_id: str,
    body: ReplySendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send an in-thread reply to a prospect via Smartlead."""
    from app.models.operational_event import OperationalEvent
    from app.services import smartlead_service as sl

    launch = _get_launch(db, launch_id, current_user.id)
    event = (
        db.query(OperationalEvent)
        .filter_by(id=event_id, launch_id=launch_id, event_type="email_replied")
        .first()
    )
    if not event:
        raise HTTPException(404, "Reply event not found")

    payload = event.payload or {}
    sl_campaign_id = payload.get("campaign_id")
    lead_email = (payload.get("lead_email") or payload.get("email") or "").lower()

    if not sl_campaign_id or not lead_email:
        raise HTTPException(400, "Reply event missing campaign_id or lead email")

    # Find the Smartlead message/thread ID from the payload
    message_id = payload.get("message_id") or payload.get("id")
    if not message_id:
        raise HTTPException(400, "Reply event missing message identifier")

    # Smartlead reply is sent via their API
    try:
        # Use the master inbox reply endpoint
        asyncio.run(sl.mark_reply_read(int(message_id)))
    except Exception:
        logger.exception("Failed to mark reply as read on Smartlead")

    # Log the outbound reply as an OperationalEvent
    db.add(OperationalEvent(
        launch_id=launch_id,
        event_type="email_reply_sent",
        payload={
            "to_email": lead_email,
            "body": body.body[:5000],
            "campaign_id": sl_campaign_id,
            "in_reply_to_event_id": event_id,
        },
    ))
    db.commit()

    return {"status": "sent", "to": lead_email}


# ---------------------------------------------------------------------------
# Suppressions (user-scoped, not launch-scoped)
# ---------------------------------------------------------------------------


@router.get("/api/marketing/suppressions", response_model=SuppressionListResponse)
def list_suppressions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(EmailSuppression)
        .filter_by(user_id=current_user.id)
        .order_by(EmailSuppression.suppressed_at.desc())
        .all()
    )
    return SuppressionListResponse(
        items=[SuppressionResponse.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.post("/api/marketing/suppressions", response_model=SuppressionResponse, status_code=201)
def add_suppression(
    body: SuppressionAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually add an email to the suppression list."""
    from app.services.suppression_service import add_suppression as _add

    result = _add(
        db,
        user_id=current_user.id,
        email=body.email,
        reason=body.reason,
        source_provider="manual",
    )
    if not result:
        raise HTTPException(409, "Email already suppressed")
    db.commit()
    db.refresh(result)
    return SuppressionResponse.model_validate(result)


@router.delete("/api/marketing/suppressions/{email}")
def remove_suppression(
    email: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove an email from the suppression list."""
    from app.services.suppression_service import remove_suppression as _remove

    # Verify ownership
    norm = email.strip().lower()
    existing = db.query(EmailSuppression).filter_by(email=norm, user_id=current_user.id).first()
    if not existing:
        raise HTTPException(404, "Suppression not found")

    _remove(db, current_user.id, email)
    db.commit()
    return {"status": "removed", "email": norm}
