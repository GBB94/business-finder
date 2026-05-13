"""Nightly suppression sync job.

Polls Smartlead campaign analytics for new bounces and unsubscribes,
then adds them to the EmailSuppression table. This catches events
that may have been missed by webhooks (network issues, etc.).
"""
from __future__ import annotations

import asyncio
import logging

from app.database import SessionLocal
from app.models.marketing_campaign import MarketingCampaign

logger = logging.getLogger(__name__)


async def _sync_campaign(db, campaign: MarketingCampaign, user_id: str) -> int:
    """Sync bounces and unsubscribes for a single campaign."""
    from app.services import smartlead_service as sl
    from app.services.suppression_service import add_suppression

    if not campaign.provider_campaign_id:
        return 0

    added = 0
    try:
        sl_campaign_id = int(campaign.provider_campaign_id)
        analytics = await sl.get_campaign_analytics(sl_campaign_id)

        # Sync aggregate counts
        campaign.total_sent = analytics.get("sent", campaign.total_sent)
        campaign.total_delivered = analytics.get("delivered", campaign.total_delivered)
        campaign.total_bounced = analytics.get("bounced", campaign.total_bounced)
        campaign.total_replied = analytics.get("replied", campaign.total_replied)
        campaign.total_unsubscribed = analytics.get("unsubscribed", campaign.total_unsubscribed)

        # Fetch leads and check for new bounces/unsubscribes
        offset = 0
        while True:
            leads_result = await sl.get_campaign_leads(sl_campaign_id, offset=offset, limit=100)
            leads = leads_result.get("data") or leads_result.get("leads") or []
            if not leads:
                break

            for lead in leads:
                status = (lead.get("status") or "").lower()
                email = (lead.get("email") or "").lower()
                if not email:
                    continue

                if status in ("bounced", "bounce"):
                    result = add_suppression(
                        db,
                        user_id=user_id,
                        email=email,
                        reason="bounce",
                        source_provider="smartlead",
                        source_campaign_id=campaign.id,
                    )
                    if result:
                        added += 1
                elif status in ("unsubscribed", "unsubscribe"):
                    result = add_suppression(
                        db,
                        user_id=user_id,
                        email=email,
                        reason="unsubscribe",
                        source_provider="smartlead",
                        source_campaign_id=campaign.id,
                    )
                    if result:
                        added += 1

            offset += len(leads)
            if len(leads) < 100:
                break

    except Exception:
        logger.exception("Suppression sync failed for campaign %s", campaign.id)

    return added


def run_suppression_sync() -> None:
    """Sync suppressions from all active Smartlead campaigns."""
    db = SessionLocal()
    total_added = 0

    try:
        campaigns = (
            db.query(MarketingCampaign)
            .filter(
                MarketingCampaign.status.in_(["active", "paused", "completed"]),
                MarketingCampaign.provider == "smartlead",
                MarketingCampaign.provider_campaign_id.isnot(None),
            )
            .all()
        )

        logger.info("Suppression sync: checking %d campaigns", len(campaigns))

        for campaign in campaigns:
            added = asyncio.run(_sync_campaign(db, campaign, campaign.user_id))
            total_added += added

        db.commit()
        logger.info("Suppression sync complete: %d new suppressions added", total_added)

    except Exception:
        logger.exception("Suppression sync job failed")
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Push direction: sync local suppressions TO Smartlead global unsubscribe
# ---------------------------------------------------------------------------


async def _push_unsynced(db) -> int:
    """Push suppressions that haven't been synced to Smartlead's global unsubscribe list."""
    from app.models.email_suppression import EmailSuppression
    from app.services import smartlead_service as sl
    from datetime import datetime, timezone

    unsynced = (
        db.query(EmailSuppression)
        .filter_by(synced_to_smartlead=False)
        .limit(500)
        .all()
    )

    if not unsynced:
        return 0

    # Batch emails into a single API call (add_to_global_unsubscribe expects list[str])
    emails = [sup.email for sup in unsynced]
    try:
        await sl.add_to_global_unsubscribe(emails)
        now = datetime.now(timezone.utc)
        for sup in unsynced:
            sup.synced_to_smartlead = True
            sup.synced_at = now
    except Exception:
        logger.warning("Failed to push %d emails to Smartlead global unsubscribe", len(emails))
        return 0

    db.flush()
    return len(unsynced)


def run_suppression_push() -> None:
    """Push unsynced local suppressions to Smartlead. Run nightly after pull sync."""
    db = SessionLocal()
    try:
        pushed = asyncio.run(_push_unsynced(db))
        db.commit()
        logger.info("Suppression push complete: %d emails synced to Smartlead", pushed)
    except Exception:
        logger.exception("Suppression push job failed")
        db.rollback()
    finally:
        db.close()
