"""Real-time interrupt emitter for critical operational events.

When a critical event occurs (error spike, email bounce, payment failure),
this service triggers an immediate CEO evaluation instead of waiting for
the nightly run. Deduplicates to avoid flooding: at most one interrupt
evaluation per project per cooldown window.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.agent_task import AgentTask
from app.models.launch_instance import LaunchInstance
from app.models.operational_event import OperationalEvent

logger = logging.getLogger(__name__)

# Event types that warrant an immediate CEO evaluation
CRITICAL_EVENT_TYPES = {"error_spike", "email_bounced", "error"}

# Cooldown: don't fire another interrupt evaluation if one ran within this window
INTERRUPT_COOLDOWN_MINUTES = 30


def trigger_and_enqueue(
    db: Session,
    launch_id: str,
    event_type: str,
) -> bool:
    """Create and enqueue a CEO interrupt evaluation for a critical event.

    If Redis enqueue fails after the task is committed, the task and event
    are deleted so no stranded row is left behind.  Returns True if the
    full create-and-enqueue sequence succeeded.
    """
    if event_type not in CRITICAL_EVENT_TYPES:
        return False

    launch = db.query(LaunchInstance).filter_by(id=launch_id).first()
    if not launch or launch.status not in ("preview", "active"):
        return False

    # Cooldown: only suppress if a prior *interrupt-triggered* evaluation
    # was already created within the window.  Scheduled or manual CEO runs
    # must not block interrupts because the critical event may have occurred
    # after that evaluation completed.
    cooldown_start = datetime.now(timezone.utc) - timedelta(minutes=INTERRUPT_COOLDOWN_MINUTES)
    recent_interrupt = (
        db.query(OperationalEvent)
        .filter(
            OperationalEvent.launch_id == launch_id,
            OperationalEvent.event_type == "ceo_interrupt_triggered",
            OperationalEvent.created_at >= cooldown_start,
        )
        .first()
    )
    if recent_interrupt:
        logger.debug(
            "Skipping CEO interrupt for launch=%s: recent interrupt exists (event=%s)",
            launch_id, recent_interrupt.id,
        )
        return False

    # Create the task (create_task commits internally)
    from app.services.agent_task_service import create_task

    task = create_task(
        db,
        idea_id=launch.idea_id,
        user_id=launch.user_id,
        task_type="ceo_nightly",
        input_params={"trigger": "interrupt", "trigger_event_type": event_type},
    )
    task.launch_id = launch_id
    task.agent_type = "ceo"

    event = OperationalEvent(
        launch_id=launch_id,
        event_type="ceo_interrupt_triggered",
        payload={
            "trigger_event_type": event_type,
            "task_id": task.id,
        },
    )
    db.add(event)
    db.commit()

    # Enqueue to Redis
    try:
        import redis as redis_lib
        from rq import Queue
        from app.jobs.agent_task_runner import _queue_for_task

        conn = redis_lib.from_url(settings.REDIS_URL)
        q = Queue(_queue_for_task("ceo_nightly"), connection=conn)
        q.enqueue("app.jobs.agent_task_runner.run_agent_task", task.id)
        logger.info(
            "CEO interrupt triggered and enqueued for launch=%s by %s event (task=%s)",
            launch_id, event_type, task.id,
        )
        return True

    except Exception:
        # Redis failed. Delete the task and event so nothing is stranded.
        # The next critical event will retry the whole sequence.
        logger.exception(
            "Redis enqueue failed for CEO interrupt task %s, cleaning up", task.id,
        )
        try:
            # Delete steps first (FK constraint)
            for step in task.steps:
                db.delete(step)
            db.delete(task)
            db.delete(event)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to clean up stranded interrupt task %s", task.id)
        return False
