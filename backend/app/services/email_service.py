"""Email delivery via Resend for LaunchPad notifications."""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    html: str,
    from_email: str | None = None,
) -> str | None:
    """Send an email via Resend. Returns the Resend message ID on success, None on failure.

    Fails silently with a warning log if RESEND_API_KEY is not configured,
    so the CEO loop doesn't crash when email isn't set up yet.
    """
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured, skipping email send to=%s subject=%s", to, subject)
        return None

    try:
        import resend

        resend.api_key = settings.RESEND_API_KEY
        result = resend.Emails.send({
            "from": from_email or settings.RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        msg_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        logger.info("Sent email to=%s subject=%s id=%s", to, subject, msg_id)
        return msg_id
    except Exception:
        logger.exception("Failed to send email to=%s subject=%s", to, subject)
        return None
