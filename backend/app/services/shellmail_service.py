"""ShellMail API client for product support inbound email.

ShellMail provides a receiving inbox for customer support emails. It is NOT
used for outbound. Smartlead handles cold outbound; Resend handles transactional.

All methods are async. Errors raise ShellmailError.
"""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.shellmail.app/v1"


class ShellmailError(RuntimeError):
    """Raised when a ShellMail API call fails."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _api_key() -> str:
    if not settings.SHELLMAIL_API_KEY:
        raise ShellmailError("SHELLMAIL_API_KEY not configured")
    return settings.SHELLMAIL_API_KEY


async def _request(
    method: str,
    path: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Make an authenticated request to the ShellMail API."""
    url = f"{_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {_api_key()}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(method, url, headers=headers, params=params, json=json)

    if resp.status_code >= 400:
        logger.error("ShellMail %s %s => %d: %s", method, path, resp.status_code, resp.text[:500])
        raise ShellmailError(
            f"ShellMail API error {resp.status_code}: {resp.text[:200]}",
            status_code=resp.status_code,
        )
    return resp.json()


# ---------------------------------------------------------------------------
# Inbox management
# ---------------------------------------------------------------------------


async def create_inbox(
    *,
    address: str,
    display_name: str | None = None,
    webhook_url: str | None = None,
) -> dict:
    """Create a support inbox on ShellMail.

    Args:
        address: The full inbox address (e.g. "support@project.example.com")
        display_name: Human-friendly name shown in From header
        webhook_url: URL to POST inbound emails to (our /api/webhooks/shellmail endpoint)

    Returns the created inbox object including its ID.
    """
    payload = {"address": address}
    if display_name:
        payload["display_name"] = display_name
    if webhook_url:
        payload["webhook_url"] = webhook_url
    return await _request("POST", "/inboxes", json=payload)


async def get_inbox(inbox_id: str) -> dict:
    """Get inbox details."""
    return await _request("GET", f"/inboxes/{inbox_id}")


async def list_inboxes() -> list[dict]:
    """List all inboxes."""
    result = await _request("GET", "/inboxes")
    return result if isinstance(result, list) else result.get("data", [])


async def update_inbox_webhook(inbox_id: str, webhook_url: str) -> dict:
    """Update the webhook URL for an inbox."""
    return await _request("PATCH", f"/inboxes/{inbox_id}", json={"webhook_url": webhook_url})


async def delete_inbox(inbox_id: str) -> dict:
    """Delete an inbox."""
    return await _request("DELETE", f"/inboxes/{inbox_id}")


# ---------------------------------------------------------------------------
# Message retrieval
# ---------------------------------------------------------------------------


async def list_messages(inbox_id: str, *, limit: int = 50, offset: int = 0) -> list[dict]:
    """List messages in an inbox."""
    result = await _request(
        "GET",
        f"/inboxes/{inbox_id}/messages",
        params={"limit": limit, "offset": offset},
    )
    return result if isinstance(result, list) else result.get("data", [])


async def get_message(inbox_id: str, message_id: str) -> dict:
    """Get a specific message."""
    return await _request("GET", f"/inboxes/{inbox_id}/messages/{message_id}")


async def reply(inbox_id: str, thread_id: str, body: str) -> dict:
    """Reply to a message thread."""
    return await _request(
        "POST",
        f"/inboxes/{inbox_id}/threads/{thread_id}/reply",
        json={"body": body},
    )


async def mark_read(inbox_id: str, message_id: str) -> None:
    """Mark a message as read."""
    await _request("POST", f"/inboxes/{inbox_id}/messages/{message_id}/read")
