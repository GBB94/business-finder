"""Email bounce detection and outbound pause enforcement.

When a project's bounce rate exceeds the threshold within a sliding
window, outbound email is paused for that project. This prevents domain
reputation damage from continued sends against a bad list.

The pause is per-project: only the affected launch has its outbound
blocked. Other projects continue normally.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class OutboundPausedError(RuntimeError):
    """Raised when outbound email is paused for a project due to high bounce rate."""
from app.models.launch_instance import LaunchInstance
from app.models.operational_event import OperationalEvent

logger = logging.getLogger(__name__)

# Bounce rate threshold: if bounces / total_sent exceeds this in the
# window, outbound is paused. 5% is conservative (Resend suspends at
# ~10%, AWS SES at 5%).
BOUNCE_RATE_THRESHOLD = 0.05

# Minimum sends before bounce rate is meaningful. A single bounce out
# of 2 sends is 50% but not actionable.
MIN_SENDS_FOR_EVALUATION = 10

# Sliding window for bounce rate calculation
WINDOW_HOURS = 24


def check_and_pause(db: Session, launch_id: str) -> bool:
    """Check bounce rate for a project and pause outbound if too high.

    Returns True if outbound was paused (or was already paused).
    """
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if not launch:
        return False

    # Already paused
    if launch.outbound_paused_at is not None:
        logger.debug("Outbound already paused for launch=%s", launch_id)
        return True

    window_start = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)

    # Count sends and bounces in the window
    sent_count = (
        db.query(func.count(OperationalEvent.id))
        .filter(
            OperationalEvent.launch_id == launch_id,
            OperationalEvent.event_type == "email_sent",
            OperationalEvent.created_at >= window_start,
        )
        .scalar()
    ) or 0

    bounce_count = (
        db.query(func.count(OperationalEvent.id))
        .filter(
            OperationalEvent.launch_id == launch_id,
            OperationalEvent.event_type == "email_bounced",
            OperationalEvent.created_at >= window_start,
        )
        .scalar()
    ) or 0

    total = sent_count + bounce_count
    if total < MIN_SENDS_FOR_EVALUATION:
        logger.debug(
            "Too few sends (%d) for bounce evaluation on launch=%s",
            total, launch_id,
        )
        return False

    bounce_rate = bounce_count / total
    if bounce_rate < BOUNCE_RATE_THRESHOLD:
        return False

    # Pause outbound
    reason = (
        f"Bounce rate {bounce_rate:.1%} ({bounce_count}/{total}) exceeds "
        f"{BOUNCE_RATE_THRESHOLD:.0%} threshold in {WINDOW_HOURS}h window"
    )
    launch.outbound_paused_at = datetime.now(timezone.utc)
    launch.outbound_pause_reason = reason

    db.add(AuditLog(
        launch_id=launch_id,
        actor="system",
        action="outbound_paused",
        resource_type="launch_instance",
        resource_id=launch_id,
        details={
            "bounce_rate": round(bounce_rate, 4),
            "bounce_count": bounce_count,
            "sent_count": sent_count,
            "window_hours": WINDOW_HOURS,
            "reason": reason,
        },
    ))
    db.commit()

    logger.warning(
        "Paused outbound email for launch=%s: %s",
        launch_id, reason,
    )
    return True


def is_outbound_paused(db: Session, launch_id: str) -> bool:
    """Check if outbound email is paused for a project."""
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    return launch is not None and launch.outbound_paused_at is not None


def unpause_outbound(db: Session, launch_id: str) -> bool:
    """Manually unpause outbound email for a project. Returns True if it was paused."""
    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if not launch or launch.outbound_paused_at is None:
        return False

    old_reason = launch.outbound_pause_reason
    launch.outbound_paused_at = None
    launch.outbound_pause_reason = None

    db.add(AuditLog(
        launch_id=launch_id,
        actor="founder",
        action="outbound_unpaused",
        resource_type="launch_instance",
        resource_id=launch_id,
        details={"previous_reason": old_reason},
    ))
    db.commit()

    logger.info("Unpaused outbound email for launch=%s", launch_id)
    return True
