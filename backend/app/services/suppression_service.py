"""Email suppression screening and management.

Every outbound send must check is_suppressed() before dispatching.
Suppressions are per-tenant (scoped by user_id) and cross-campaign:
a bounce in campaign A blocks sends in campaign B for the same user.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.email_suppression import EmailSuppression

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    """Normalize an email address for suppression matching."""
    return email.strip().lower()


def is_suppressed(db: Session, user_id: str, email: str) -> bool:
    """Check if an email is on the suppression list for this user."""
    return (
        db.query(EmailSuppression.id)
        .filter(
            EmailSuppression.user_id == user_id,
            EmailSuppression.email == normalize_email(email),
        )
        .first()
    ) is not None


def bulk_screen(db: Session, user_id: str, emails: list[str]) -> set[str]:
    """Screen a list of emails and return the set of suppressed ones for this user."""
    if not emails:
        return set()
    normalized = [normalize_email(e) for e in emails]
    suppressed_rows = (
        db.query(EmailSuppression.email)
        .filter(
            EmailSuppression.user_id == user_id,
            EmailSuppression.email.in_(normalized),
        )
        .all()
    )
    return {row.email for row in suppressed_rows}


def add_suppression(
    db: Session,
    *,
    user_id: str,
    email: str,
    reason: str,
    source_provider: str | None = None,
    source_campaign_id: str | None = None,
    provider_event_id: str | None = None,
) -> EmailSuppression | None:
    """Add an email to the suppression list for this user. Returns None if already suppressed."""
    norm = normalize_email(email)
    existing = db.query(EmailSuppression).filter_by(user_id=user_id, email=norm).first()
    if existing:
        logger.debug("Email %s already suppressed for user %s (reason=%s)", norm, user_id, existing.reason)
        return None

    suppression = EmailSuppression(
        user_id=user_id,
        email=norm,
        reason=reason,
        source_provider=source_provider,
        source_campaign_id=source_campaign_id,
        provider_event_id=provider_event_id,
    )
    db.add(suppression)
    db.flush()
    logger.info("Suppressed email=%s user=%s reason=%s provider=%s", norm, user_id, reason, source_provider)
    return suppression


def remove_suppression(db: Session, user_id: str, email: str) -> bool:
    """Remove an email from the suppression list for this user. Returns True if found and removed."""
    norm = normalize_email(email)
    row = db.query(EmailSuppression).filter_by(user_id=user_id, email=norm).first()
    if not row:
        return False
    db.delete(row)
    db.flush()
    logger.info("Removed suppression for email=%s user=%s", norm, user_id)
    return True


def sync_bounces_from_provider(
    db: Session,
    user_id: str,
    bounces: list[dict],
    source_provider: str,
    campaign_id: str | None = None,
) -> int:
    """Bulk-import bounces from a provider into the suppression list.

    Each bounce dict should have at least {"email": "..."}.
    Optional fields: "provider_event_id".

    Returns count of new suppressions added.
    """
    added = 0
    for bounce in bounces:
        email = bounce.get("email")
        if not email:
            continue
        result = add_suppression(
            db,
            user_id=user_id,
            email=email,
            reason="bounce",
            source_provider=source_provider,
            source_campaign_id=campaign_id,
            provider_event_id=bounce.get("provider_event_id"),
        )
        if result:
            added += 1
    return added
