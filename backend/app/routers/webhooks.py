"""Inbound webhook endpoints for Resend and Stripe.

Each endpoint verifies the provider's signature before processing.
Valid events are recorded as OperationalEvents so the CEO agent
and metrics collector can see them.

Both handlers are idempotent: they deduplicate on the provider's
event ID to prevent duplicate OperationalEvents from retries.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone

import redis
from fastapi import APIRouter, Header, HTTPException, Request, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.launch_instance import LaunchInstance
from app.models.operational_event import OperationalEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dedupe_by_provider_event_id(
    db: Session, launch_id: str, provider_event_id: str,
) -> OperationalEvent | None:
    """Fast-path check using the provider_event_id column (backed by unique index).

    The unique partial index on (launch_id, provider_event_id) is the real
    protection against concurrent inserts; this is just a cheap pre-check to
    avoid unnecessary INSERT attempts on serial retries.
    """
    if not provider_event_id:
        return None
    return (
        db.query(OperationalEvent)
        .filter(
            OperationalEvent.launch_id == launch_id,
            OperationalEvent.provider_event_id == provider_event_id,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Resend webhook
# ---------------------------------------------------------------------------

_RESEND_EVENT_MAP: dict[str, str] = {
    "email.bounced": "email_bounced",
    "email.complained": "email_bounced",  # treat complaints like bounces
    "email.delivered": "email_sent",
    "email.received": "email_received",  # inbound email for support triage
}


def _verify_resend_signature(
    body: bytes,
    msg_id: str | None,
    signature: str | None,
    timestamp: str | None,
) -> None:
    """Verify Resend webhook signature (Svix HMAC-SHA256).

    Resend/Svix sends:
      svix-id: <message_id>
      svix-timestamp: <unix_seconds>
      svix-signature: v1,<base64_sig>

    Signed content is "{msg_id}.{timestamp}.{body}" per the Svix spec.
    """
    if not settings.RESEND_WEBHOOK_SECRET:
        raise HTTPException(503, "Resend webhook secret not configured")

    if not signature or not timestamp or not msg_id:
        raise HTTPException(401, "Missing svix signature headers")

    # Reject timestamps older than 5 minutes to prevent replay
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        raise HTTPException(401, "Invalid timestamp")
    if abs(time.time() - ts) > 300:
        raise HTTPException(401, "Timestamp too old")

    # Resend uses svix: secret is base64-encoded after "whsec_" prefix
    secret_bytes = settings.RESEND_WEBHOOK_SECRET
    if secret_bytes.startswith("whsec_"):
        secret_bytes = secret_bytes[6:]
    try:
        key = base64.b64decode(secret_bytes)
    except Exception:
        raise HTTPException(500, "Invalid webhook secret configuration")

    # Svix spec: sign "{msg_id}.{timestamp}.{body}"
    msg = f"{msg_id}.{timestamp}.{body.decode('utf-8')}"
    expected = base64.b64encode(
        hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
    ).decode("utf-8")

    # signature format: "v1,<sig>" (space-separated, may have multiple)
    sigs = [s.strip().removeprefix("v1,") for s in signature.split(" ") if s.strip().startswith("v1,")]
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise HTTPException(401, "Invalid signature")


def _find_launch_by_email_metadata(db: Session, payload: dict) -> str | None:
    """Extract launch_id from Resend email metadata/tags."""
    # Resend includes custom headers/tags in the webhook payload
    tags = payload.get("tags") or {}
    if isinstance(tags, dict):
        launch_id = tags.get("launch_id")
        if launch_id:
            return launch_id

    # Fallback: check custom metadata
    data = payload.get("data") or payload
    meta = data.get("metadata") or data.get("custom_metadata") or {}
    if isinstance(meta, dict):
        return meta.get("launch_id")

    return None


@router.post("/resend", status_code=200)
async def resend_webhook(
    request: Request,
    db: Session = Depends(get_db),
    svix_id: str | None = Header(None, alias="svix-id"),
    svix_signature: str | None = Header(None, alias="svix-signature"),
    svix_timestamp: str | None = Header(None, alias="svix-timestamp"),
):
    body = await request.body()
    _verify_resend_signature(body, svix_id, svix_signature, svix_timestamp)

    payload = await request.json()
    event_type = payload.get("type", "")
    mapped_type = _RESEND_EVENT_MAP.get(event_type)

    if not mapped_type:
        # Acknowledge but ignore events we don't care about
        return {"status": "ignored", "event_type": event_type}

    data = payload.get("data") or {}
    launch_id = _find_launch_by_email_metadata(db, payload)

    if not launch_id:
        logger.warning("Resend webhook %s has no launch_id in metadata, skipping event creation", event_type)
        return {"status": "skipped", "reason": "no_launch_id"}

    # Verify launch exists
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if not launch:
        logger.warning("Resend webhook references unknown launch_id=%s", launch_id)
        return {"status": "skipped", "reason": "unknown_launch"}

    # Deduplicate on svix message ID
    provider_event_id = svix_id or ""
    existing = _dedupe_by_provider_event_id(db, launch_id, provider_event_id)
    is_duplicate = existing is not None

    if not is_duplicate:
        event = OperationalEvent(
            launch_id=launch_id,
            event_type=mapped_type,
            provider_event_id=provider_event_id or None,
            payload={
                "provider": "resend",
                "provider_event_id": provider_event_id,
                "resend_event_type": event_type,
                "email_id": data.get("email_id") or data.get("id"),
                "to": data.get("to"),
                "bounce_type": data.get("bounce", {}).get("bounce_type") if isinstance(data.get("bounce"), dict) else None,
            },
        )
        db.add(event)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            is_duplicate = True

    # For non-inbound events, duplicates can exit early
    if is_duplicate and mapped_type != "email_received":
        logger.info("Resend webhook %s already processed, skipping", provider_event_id)
        return {"status": "duplicate", "event_id": existing.id if existing else None}

    if not is_duplicate:
        logger.info("Created %s event for launch=%s from Resend webhook", mapped_type, launch_id)

        # Bounces: check bounce rate and pause outbound if threshold exceeded,
        # then trigger an immediate CEO evaluation
        if mapped_type == "email_bounced":
            from app.services.bounce_detector import check_and_pause
            check_and_pause(db, launch_id)

            from app.services.interrupt_emitter import trigger_and_enqueue
            trigger_and_enqueue(db, launch_id, mapped_type)

    # For inbound emails, ensure a triage task exists and is enqueued.
    # This runs even on duplicate event retries so that a prior failure
    # (DB commit succeeded but Redis enqueue failed) can be repaired.
    # The idempotency_key on the task prevents double-creation.
    if mapped_type == "email_received":
        from app.services.agent_task_service import create_task
        from app.services.task_enqueue import enqueue_task

        idem_key = f"triage:{provider_event_id}" if provider_event_id else None

        try:
            task = create_task(
                db,
                idea_id=launch.idea_id,
                user_id=launch.user_id,
                task_type="triage_inbox",
                idempotency_key=idem_key,
                input_params={
                    "customer_email": data.get("from") or data.get("sender") or "",
                    "subject": data.get("subject") or "",
                    "body": data.get("text") or data.get("html") or data.get("body") or "",
                    "message_id": data.get("id") or data.get("message_id") or "",
                },
            )
            # Set launch_id and agent_type. For idempotent re-finds these
            # are already set, but the update is harmless.
            task.launch_id = launch_id
            task.agent_type = "support"

            # Only enqueue if the task is still waiting to be picked up.
            # If a prior attempt already enqueued it and the worker claimed
            # it, re-enqueueing would cause duplicate execution.
            if task.status == "queued":
                enqueue_task(db, task)
            else:
                db.commit()
                logger.info("Triage task %s already in status %s, skipping enqueue", task.id, task.status)
        except Exception:
            db.rollback()
            logger.exception("Failed to create/enqueue triage_inbox for launch=%s", launch_id)
            raise HTTPException(503, "Failed to enqueue support triage task")

    event_id = event.id if not is_duplicate else (existing.id if existing else None)
    return {"status": "processed" if not is_duplicate else "repaired", "event_type": mapped_type, "event_id": event_id}


# ---------------------------------------------------------------------------
# Stripe webhook
# ---------------------------------------------------------------------------


def _verify_stripe_signature(body: bytes, signature: str | None) -> None:
    """Verify Stripe webhook signature (v1 scheme).

    Stripe sends Stripe-Signature header with format:
      t=<timestamp>,v1=<sig>[,v1=<sig>...]

    We compute HMAC-SHA256(secret, "{timestamp}.{body}") and compare.
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Stripe webhook secret not configured")

    if not signature:
        raise HTTPException(401, "Missing Stripe-Signature header")

    # Parse header
    parts: dict[str, list[str]] = {}
    for item in signature.split(","):
        key, _, val = item.strip().partition("=")
        parts.setdefault(key, []).append(val)

    timestamp = (parts.get("t") or [None])[0]
    sigs = parts.get("v1", [])

    if not timestamp or not sigs:
        raise HTTPException(401, "Malformed Stripe-Signature header")

    # Reject old timestamps (5 minutes)
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        raise HTTPException(401, "Invalid timestamp in signature")
    if abs(time.time() - ts) > 300:
        raise HTTPException(401, "Timestamp too old")

    expected = hmac.new(
        settings.STRIPE_WEBHOOK_SECRET.encode("utf-8"),
        f"{timestamp}.{body.decode('utf-8')}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise HTTPException(401, "Invalid signature")


_STRIPE_FAILURE_EVENTS: set[str] = {
    "invoice.payment_failed",
    "charge.failed",
    "payment_intent.payment_failed",
}


@router.post("/stripe", status_code=200)
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db),
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
):
    body = await request.body()
    _verify_stripe_signature(body, stripe_signature)

    payload = await request.json()
    event_type = payload.get("type", "")

    if event_type not in _STRIPE_FAILURE_EVENTS:
        return {"status": "ignored", "event_type": event_type}

    data = payload.get("data", {}).get("object", {})
    metadata = data.get("metadata") or {}
    launch_id = metadata.get("launch_id")

    if not launch_id:
        logger.warning("Stripe webhook %s has no launch_id in metadata, skipping", event_type)
        return {"status": "skipped", "reason": "no_launch_id"}

    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if not launch:
        logger.warning("Stripe webhook references unknown launch_id=%s", launch_id)
        return {"status": "skipped", "reason": "unknown_launch"}

    # Deduplicate on Stripe event ID
    stripe_event_id = payload.get("id", "")
    existing = _dedupe_by_provider_event_id(db, launch_id, stripe_event_id)
    if existing:
        logger.info("Stripe webhook %s already processed (event=%s), skipping", stripe_event_id, existing.id)
        return {"status": "duplicate", "event_id": existing.id}

    event = OperationalEvent(
        launch_id=launch_id,
        event_type="error",
        provider_event_id=stripe_event_id or None,
        payload={
            "provider": "stripe",
            "provider_event_id": stripe_event_id,
            "stripe_event_type": event_type,
            "amount": data.get("amount"),
            "currency": data.get("currency"),
            "failure_code": data.get("failure_code") or data.get("last_payment_error", {}).get("code"),
            "failure_message": data.get("failure_message") or data.get("last_payment_error", {}).get("message"),
            "customer_id": data.get("customer"),
        },
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("Stripe webhook %s lost race (unique constraint), treating as duplicate", stripe_event_id)
        return {"status": "duplicate", "event_id": None}

    logger.info("Created error event for launch=%s from Stripe webhook (%s)", launch_id, event_type)

    # Payment failures trigger an immediate CEO evaluation
    from app.services.interrupt_emitter import trigger_and_enqueue
    trigger_and_enqueue(db, launch_id, "error")

    return {"status": "processed", "event_type": event_type, "event_id": event.id}


# ---------------------------------------------------------------------------
# Smartlead webhook
# ---------------------------------------------------------------------------

_SMARTLEAD_EVENT_MAP: dict[str, str] = {
    "EMAIL_SENT": "email_sent",
    "EMAIL_OPENED": "email_opened",
    "EMAIL_REPLIED": "email_replied",
    "EMAIL_BOUNCED": "email_bounced",
    "EMAIL_UNSUBSCRIBED": "email_unsubscribed",
    "LEAD_CATEGORY_UPDATED": "lead_status_changed",
    "SPAM_COMPLAINT": "email_bounced",  # treat complaints as bounces for suppression
}


def _verify_smartlead_signature(body: bytes, signature: str | None) -> None:
    """Verify Smartlead webhook HMAC-SHA256 signature."""
    if not settings.SMARTLEAD_WEBHOOK_SECRET:
        raise HTTPException(503, "Smartlead webhook secret not configured")
    if not signature:
        raise HTTPException(401, "Missing X-Smartlead-Signature header")

    expected = hmac.new(
        settings.SMARTLEAD_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid Smartlead signature")


@router.post("/smartlead", status_code=200)
async def smartlead_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_smartlead_signature: str | None = Header(None, alias="x-smartlead-signature"),
):
    body = await request.body()
    _verify_smartlead_signature(body, x_smartlead_signature)

    payload = await request.json()
    event_type = payload.get("event_type", "")
    mapped_type = _SMARTLEAD_EVENT_MAP.get(event_type)

    if not mapped_type:
        return {"status": "ignored", "event_type": event_type}

    data = payload.get("data") or payload
    sl_event_id = payload.get("event_id") or payload.get("id") or ""

    # Resolve launch_id from campaign
    sl_campaign_id = str(data.get("campaign_id") or data.get("seq_id") or "")
    launch_id = None
    if sl_campaign_id:
        from app.models.marketing_campaign import MarketingCampaign
        campaign = (
            db.query(MarketingCampaign)
            .filter_by(provider_campaign_id=sl_campaign_id)
            .first()
        )
        if campaign:
            launch_id = campaign.launch_id

    if not launch_id:
        logger.warning("Smartlead webhook %s: no launch_id resolvable from campaign %s", event_type, sl_campaign_id)
        return {"status": "skipped", "reason": "no_launch_id"}

    # Verify launch exists
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if not launch:
        return {"status": "skipped", "reason": "unknown_launch"}

    # Deduplicate — only skip the OperationalEvent INSERT, never skip side effects
    provider_event_id = f"sl:{sl_event_id}" if sl_event_id else None
    is_duplicate = False
    event_id = None

    if provider_event_id:
        existing = _dedupe_by_provider_event_id(db, launch_id, provider_event_id)
        is_duplicate = existing is not None
        if existing:
            event_id = existing.id

    if not is_duplicate:
        event = OperationalEvent(
            launch_id=launch_id,
            event_type=mapped_type,
            provider_event_id=provider_event_id,
            payload={
                "provider": "smartlead",
                "provider_event_id": sl_event_id,
                "smartlead_event_type": event_type,
                "campaign_id": sl_campaign_id,
                "lead_email": data.get("email") or data.get("to_email") or "",
                "lead_id": data.get("lead_id"),
            },
        )
        db.add(event)
        try:
            db.commit()
            event_id = event.id
        except IntegrityError:
            db.rollback()
            is_duplicate = True

        if not is_duplicate:
            logger.info("Created %s event for launch=%s from Smartlead webhook", mapped_type, launch_id)

    # --- Side effects run regardless of duplicate status (all idempotent) ---

    lead_email = (data.get("email") or data.get("to_email") or "").lower()

    # Prospect status update (idempotent: only advances status, never regresses)
    if lead_email and campaign:
        from app.models.campaign_prospect import CampaignProspect
        prospect = (
            db.query(CampaignProspect)
            .filter_by(campaign_id=campaign.id, email=lead_email)
            .first()
        )
        if prospect:
            now = datetime.now(timezone.utc)
            if mapped_type == "email_sent" and prospect.status == "pending":
                prospect.status = "sent"
                prospect.sent_at = prospect.sent_at or now
            elif mapped_type == "email_bounced" and prospect.status != "bounced":
                prospect.status = "bounced"
                prospect.bounced_at = prospect.bounced_at or now
            elif mapped_type == "email_replied" and prospect.status != "replied":
                prospect.status = "replied"
                prospect.replied_at = prospect.replied_at or now
            elif mapped_type == "email_unsubscribed" and prospect.status != "unsubscribed":
                prospect.status = "unsubscribed"
            db.commit()

    # Recompute campaign counters from OperationalEvent count (idempotent)
    if campaign:
        from sqlalchemy import func
        for evt_type, col_name in [
            ("email_sent", "total_sent"),
            ("email_bounced", "total_bounced"),
            ("email_replied", "total_replied"),
            ("email_unsubscribed", "total_unsubscribed"),
        ]:
            count = (
                db.query(func.count(OperationalEvent.id))
                .filter(
                    OperationalEvent.launch_id == launch_id,
                    OperationalEvent.event_type == evt_type,
                    OperationalEvent.payload["campaign_id"].as_string() == sl_campaign_id,
                )
                .scalar()
            ) or 0
            setattr(campaign, col_name, count)
        db.commit()

    # Bounces: add to suppression list (upsert, idempotent) + check bounce rate
    if mapped_type == "email_bounced" and lead_email:
        from app.services.suppression_service import add_suppression
        add_suppression(
            db,
            user_id=launch.user_id,
            email=lead_email,
            reason="bounce",
            source_provider="smartlead",
            source_campaign_id=campaign.id if campaign else None,
            provider_event_id=sl_event_id,
        )
        db.commit()

        from app.services.bounce_detector import check_and_pause
        check_and_pause(db, launch_id)

    # Replies: enqueue triage_campaign_reply task (idempotency key prevents double)
    if mapped_type == "email_replied" and lead_email:
        _enqueue_campaign_reply_triage(db, launch, data, sl_event_id, campaign)

    # Unsubscribes: add to suppression list (upsert, idempotent)
    if mapped_type == "email_unsubscribed" and lead_email:
        from app.services.suppression_service import add_suppression
        add_suppression(
            db,
            user_id=launch.user_id,
            email=lead_email,
            reason="unsubscribe",
            source_provider="smartlead",
            source_campaign_id=campaign.id if campaign else None,
            provider_event_id=sl_event_id,
        )
        db.commit()

    return {
        "status": "processed" if not is_duplicate else "repaired",
        "event_type": mapped_type,
        "event_id": event_id,
    }


# ---------------------------------------------------------------------------
# Campaign reply triage helper
# ---------------------------------------------------------------------------


def _enqueue_campaign_reply_triage(
    db: Session,
    launch,
    payload: dict,
    provider_event_id: str,
    campaign=None,
) -> None:
    """Enqueue a triage_campaign_reply task for a prospect reply.

    Uses a dedicated task type (not triage_inbox) because cold outreach
    replies are qualification conversations, not support tickets. The prompt
    branches on reply intent: interested, objection, unsubscribe, OOO.
    """
    from app.services.agent_task_service import create_task
    from app.services.task_enqueue import enqueue_task

    lead_email = (payload.get("email") or payload.get("to_email") or payload.get("lead_email") or "").lower()
    reply_body = payload.get("reply_text") or payload.get("body") or payload.get("message") or ""
    idem_key = f"campaign_reply:{provider_event_id}" if provider_event_id else None

    try:
        task = create_task(
            db,
            idea_id=launch.idea_id,
            user_id=launch.user_id,
            task_type="triage_campaign_reply",
            idempotency_key=idem_key,
            input_params={
                "from_email": lead_email,
                "reply_body": reply_body[:5000],
                "campaign_id": campaign.id if campaign else None,
                "sequence_step": payload.get("sequence_number"),
                "subject": payload.get("subject") or "",
                "provider_event_id": provider_event_id,
            },
        )
        task.launch_id = launch.id
        task.agent_type = "marketing"

        if task.status == "queued":
            enqueue_task(db, task)
        else:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to create/enqueue triage_campaign_reply for launch=%s",
            launch.id,
        )


# ---------------------------------------------------------------------------
# ShellMail webhook (inbound support email)
# ---------------------------------------------------------------------------


def _verify_shellmail_signature(body: bytes, signature: str | None) -> None:
    """Verify ShellMail webhook HMAC-SHA256 signature."""
    if not settings.SHELLMAIL_WEBHOOK_SECRET:
        raise HTTPException(503, "ShellMail webhook secret not configured")
    if not signature:
        raise HTTPException(401, "Missing X-ShellMail-Signature header")

    expected = hmac.new(
        settings.SHELLMAIL_WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "Invalid ShellMail signature")


@router.post("/shellmail", status_code=200)
async def shellmail_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_shellmail_signature: str | None = Header(None, alias="x-shellmail-signature"),
):
    """Handle inbound support emails from ShellMail.

    Creates an email_received event and enqueues a triage_inbox task,
    same pattern as the Resend inbound handler.
    """
    body = await request.body()
    _verify_shellmail_signature(body, x_shellmail_signature)

    payload = await request.json()
    data = payload.get("data") or payload

    # Resolve launch from inbox address
    inbox_address = data.get("to") or data.get("recipient") or ""
    sm_event_id = payload.get("event_id") or payload.get("id") or ""

    # Look up launch by matching the ShellMail inbox stored in project secrets
    launch_id = None
    launch = None
    if inbox_address:
        from app.models.project_secret import ProjectSecret
        from app.services.secret_service import decrypt_value
        # Find the secret that stores this ShellMail inbox address
        secrets = (
            db.query(ProjectSecret)
            .filter(ProjectSecret.key_name == "SHELLMAIL_SUPPORT_ADDRESS")
            .all()
        )
        for secret in secrets:
            try:
                decrypted = decrypt_value(secret.encrypted_value)
                if decrypted.lower() == inbox_address.lower():
                    from app.models.launch_instance import LaunchInstance as LI
                    li = db.query(LI).filter_by(idea_id=secret.idea_id, status="active").first()
                    if li:
                        launch_id = li.id
                        launch = li
                        break
            except Exception:
                continue

    if not launch_id or not launch:
        logger.warning("ShellMail webhook: could not resolve launch for inbox %s", inbox_address)
        return {"status": "skipped", "reason": "no_launch_id"}

    # Deduplicate
    provider_event_id = f"sm:{sm_event_id}" if sm_event_id else None
    if provider_event_id:
        existing = _dedupe_by_provider_event_id(db, launch_id, provider_event_id)
        if existing:
            # Still try to enqueue triage (repair pattern)
            pass
        else:
            event = OperationalEvent(
                launch_id=launch_id,
                event_type="email_received",
                provider_event_id=provider_event_id,
                payload={
                    "provider": "shellmail",
                    "provider_event_id": sm_event_id,
                    "from": data.get("from") or data.get("sender") or "",
                    "subject": data.get("subject") or "",
                    "inbox": inbox_address,
                },
            )
            db.add(event)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()

    # Enqueue triage_inbox task (same pattern as Resend inbound)
    from app.services.agent_task_service import create_task
    from app.services.task_enqueue import enqueue_task

    idem_key = f"triage:sm:{sm_event_id}" if sm_event_id else None

    try:
        task = create_task(
            db,
            idea_id=launch.idea_id,
            user_id=launch.user_id,
            task_type="triage_inbox",
            idempotency_key=idem_key,
            input_params={
                "customer_email": data.get("from") or data.get("sender") or "",
                "subject": data.get("subject") or "",
                "body": data.get("text") or data.get("html") or data.get("body") or "",
                "message_id": data.get("id") or data.get("message_id") or "",
                "source_provider": "shellmail",
            },
        )
        task.launch_id = launch_id
        task.agent_type = "support"

        if task.status == "queued":
            enqueue_task(db, task)
        else:
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to create/enqueue triage_inbox for ShellMail launch=%s", launch_id)
        raise HTTPException(503, "Failed to enqueue support triage task")

    return {"status": "processed", "event_type": "email_received"}
