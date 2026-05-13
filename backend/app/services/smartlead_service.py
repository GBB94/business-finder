"""Smartlead API client for cold outbound email campaigns.

Smartlead is mailbox-centric: you register sending mailboxes, assign them to
campaigns, and the platform handles warmup, rotation, and deliverability.

All methods are async. Errors raise SmartleadError with the upstream status.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://server.smartlead.ai/api/v1"


class SmartleadError(RuntimeError):
    """Raised when a Smartlead API call fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _api_key() -> str:
    if not settings.SMARTLEAD_API_KEY:
        raise SmartleadError("SMARTLEAD_API_KEY not configured")
    return settings.SMARTLEAD_API_KEY


async def _request(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Make an authenticated request to the Smartlead API."""
    url = f"{_BASE_URL}{path}"
    query = {"api_key": _api_key()}
    if params:
        query.update(params)

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(method, url, params=query, json=json)

    if resp.status_code >= 400:
        logger.error("Smartlead %s %s => %d: %s", method, path, resp.status_code, resp.text[:500])
        raise SmartleadError(
            f"Smartlead API error {resp.status_code}: {resp.text[:200]}",
            status_code=resp.status_code,
        )
    return resp.json()


# ---------------------------------------------------------------------------
# Mailbox management
# ---------------------------------------------------------------------------


async def add_email_account(
    *,
    from_name: str,
    from_email: str,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    warmup_enabled: bool = True,
    warmup_limit: int | None = None,
) -> dict:
    """Register a sending mailbox with Smartlead.

    Returns the created email account object including its ID.
    """
    payload: dict[str, Any] = {
        "from_name": from_name,
        "from_email": from_email,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "username": username,
        "password": password,
        "warmup_enabled": warmup_enabled,
    }
    if warmup_limit is not None:
        payload["warmup_limit"] = warmup_limit
    else:
        payload["warmup_limit"] = settings.WARMUP_EMAILS_PER_DAY

    return await _request("POST", "/email-accounts", json=payload)


async def get_email_account(account_id: int) -> dict:
    """Get details for a specific email account."""
    return await _request("GET", f"/email-accounts/{account_id}")


async def list_email_accounts() -> list[dict]:
    """List all registered email accounts."""
    result = await _request("GET", "/email-accounts")
    return result if isinstance(result, list) else result.get("data", [])


async def update_warmup(account_id: int, *, enabled: bool, limit: int | None = None) -> dict:
    """Enable/disable warmup for an email account."""
    payload: dict[str, Any] = {"warmup_enabled": enabled}
    if limit is not None:
        payload["warmup_limit"] = limit
    return await _request("POST", f"/email-accounts/{account_id}/warmup", json=payload)


async def start_warmup(
    account_id: int,
    warmup_emails_per_day: int = 5,
    reply_rate_percent: int = 30,
) -> None:
    """Enable warmup for a mailbox with specific settings."""
    await _request(
        "POST",
        f"/email-accounts/{account_id}/warmup",
        json={
            "warmup_enabled": True,
            "warmup_limit": warmup_emails_per_day,
            "warmup_reply_rate_percent": reply_rate_percent,
        },
    )


async def get_warmup_status(account_id: int) -> dict:
    """Check warmup progress for a mailbox.

    Returns: {days_warmed, ready, reputation_score, ...}
    """
    result = await _request("GET", f"/email-accounts/{account_id}/warmup")
    return result


# ---------------------------------------------------------------------------
# Campaign management
# ---------------------------------------------------------------------------


async def create_campaign(name: str) -> dict:
    """Create a new Smartlead campaign. Returns the campaign object with its ID."""
    return await _request("POST", "/campaigns/create", json={"name": name})


async def get_campaign(campaign_id: int) -> dict:
    """Get campaign details."""
    return await _request("GET", f"/campaigns/{campaign_id}")


async def update_campaign_status(campaign_id: int, status: str) -> dict:
    """Update campaign status: START, PAUSE, STOP."""
    return await _request("POST", f"/campaigns/{campaign_id}/status", json={"status": status})


async def set_campaign_schedule(campaign_id: int, schedule: dict) -> dict:
    """Set sending schedule for a campaign."""
    return await _request("POST", f"/campaigns/{campaign_id}/schedule", json=schedule)


async def add_email_account_to_campaign(campaign_id: int, account_id: int) -> dict:
    """Assign a sending mailbox to a campaign."""
    return await _request(
        "POST",
        f"/campaigns/{campaign_id}/email-accounts",
        json={"email_account_ids": [account_id]},
    )


# ---------------------------------------------------------------------------
# Sequence management
# ---------------------------------------------------------------------------


async def save_campaign_sequence(campaign_id: int, sequences: list[dict]) -> dict:
    """Save email sequences for a campaign.

    Each sequence dict: {"seq_number": 1, "subject": "...", "email_body": "...", "seq_delay_days": 0}
    """
    return await _request(
        "POST",
        f"/campaigns/{campaign_id}/sequences",
        json={"sequences": sequences},
    )


# ---------------------------------------------------------------------------
# Lead management
# ---------------------------------------------------------------------------


async def add_leads_to_campaign(campaign_id: int, leads: list[dict]) -> dict:
    """Add prospect leads to a campaign.

    Each lead dict: {"email": "...", "first_name": "...", "last_name": "...", "company": "..."}
    """
    return await _request(
        "POST",
        f"/campaigns/{campaign_id}/leads",
        json={"lead_list": leads},
    )


async def get_campaign_leads(campaign_id: int, *, offset: int = 0, limit: int = 100) -> dict:
    """Get leads in a campaign with pagination."""
    return await _request(
        "GET",
        f"/campaigns/{campaign_id}/leads",
        params={"offset": offset, "limit": limit},
    )


# ---------------------------------------------------------------------------
# Analytics / polling
# ---------------------------------------------------------------------------


async def get_campaign_analytics(campaign_id: int) -> dict:
    """Get campaign-level analytics (sent, delivered, bounced, replied, etc.)."""
    return await _request("GET", f"/campaigns/{campaign_id}/analytics")


async def get_master_inbox(*, offset: int = 0, limit: int = 50) -> list[dict]:
    """Poll the Smartlead master inbox for replies.

    Used by the CEO nightly loop to check for prospect responses.
    """
    result = await _request(
        "GET",
        "/master-inbox",
        params={"offset": offset, "limit": limit},
    )
    return result if isinstance(result, list) else result.get("data", [])


async def get_unread_replies(
    email_account_id: int,
    campaign_ids: list[int] | None = None,
) -> list[dict]:
    """Fetch unread replies for a mailbox, optionally filtered by campaigns.

    Used by the CEO nightly backfill to catch replies whose webhook failed.
    """
    params: dict[str, Any] = {}
    if campaign_ids:
        params["campaign_ids"] = ",".join(str(c) for c in campaign_ids)
    result = await _request(
        "GET",
        f"/email-accounts/{email_account_id}/replies",
        params=params,
    )
    data = result if isinstance(result, list) else result.get("data", [])
    return [r for r in data if not r.get("is_read")]


async def mark_reply_read(reply_id: int) -> None:
    """Mark a reply as read in Smartlead."""
    await _request("POST", f"/replies/{reply_id}/mark-read")


async def add_to_global_unsubscribe(emails: list[str]) -> None:
    """Sync local suppressions to Smartlead's global block list.

    Ensures Smartlead never sends to suppressed addresses even if
    the local pre-send check is somehow bypassed.
    """
    if not emails:
        return
    await _request(
        "POST",
        "/global-unsubscribes",
        json={"emails": emails},
    )
