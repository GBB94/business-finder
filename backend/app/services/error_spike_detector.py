"""Error spike detection for LaunchPad projects.

Checks recent error event counts in a sliding window and creates
an error_spike OperationalEvent when the threshold is exceeded.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.launch_instance import LaunchInstance
from app.models.operational_event import OperationalEvent

logger = logging.getLogger(__name__)

# Event types that count as errors
ERROR_EVENT_TYPES = {"error", "deploy_failed", "deploy_timeout"}


def check_error_spike(db: Session, launch_id: str) -> OperationalEvent | None:
    """Check if error count in the recent window exceeds the threshold.

    If a spike is detected, creates an error_spike OperationalEvent
    and returns it. Returns None if no spike.

    Deduplication: skips if an error_spike was already created within
    the same window (prevents flood of spike events).
    """
    window_start = datetime.now(timezone.utc) - timedelta(
        minutes=settings.ERROR_SPIKE_WINDOW_MINUTES
    )

    # Check if we already fired a spike event in this window
    recent_spike = (
        db.query(OperationalEvent)
        .filter(
            OperationalEvent.launch_id == launch_id,
            OperationalEvent.event_type == "error_spike",
            OperationalEvent.created_at >= window_start,
        )
        .first()
    )
    if recent_spike:
        return None  # Already reported

    # Count recent errors
    error_count = (
        db.query(func.count(OperationalEvent.id))
        .filter(
            OperationalEvent.launch_id == launch_id,
            OperationalEvent.event_type.in_(ERROR_EVENT_TYPES),
            OperationalEvent.created_at >= window_start,
        )
        .scalar()
    ) or 0

    if error_count < settings.ERROR_SPIKE_THRESHOLD:
        return None

    # Spike detected: create event
    event = OperationalEvent(
        launch_id=launch_id,
        event_type="error_spike",
        payload={
            "error_count": error_count,
            "window_minutes": settings.ERROR_SPIKE_WINDOW_MINUTES,
            "threshold": settings.ERROR_SPIKE_THRESHOLD,
        },
    )
    db.add(event)
    db.flush()

    logger.warning(
        "Error spike detected for launch=%s: %d errors in %d minutes (threshold: %d)",
        launch_id,
        error_count,
        settings.ERROR_SPIKE_WINDOW_MINUTES,
        settings.ERROR_SPIKE_THRESHOLD,
    )

    # Trigger immediate CEO evaluation for error spikes
    from app.services.interrupt_emitter import trigger_and_enqueue
    trigger_and_enqueue(db, launch_id, "error_spike")

    return event


def check_all_active_projects(db: Session) -> list[OperationalEvent]:
    """Run error spike detection for all active launches."""
    active_launches = (
        db.query(LaunchInstance)
        .filter(LaunchInstance.status.in_(["preview", "active"]))
        .all()
    )

    spikes: list[OperationalEvent] = []
    for launch in active_launches:
        try:
            spike = check_error_spike(db, launch.id)
            if spike:
                spikes.append(spike)
        except Exception:
            logger.exception("Error spike check failed for launch=%s", launch.id)

    if spikes:
        db.commit()
        logger.info("Detected %d error spikes across %d active projects", len(spikes), len(active_launches))

    return spikes
