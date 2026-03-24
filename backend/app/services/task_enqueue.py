"""Durable task enqueue: commit + Redis enqueue as one recoverable unit.

If enqueue fails after commit, the task is marked failed so it does not
strand in 'queued' forever and block future retries via duplicate guards.
"""
from __future__ import annotations

import logging

import redis as redis_lib
from rq import Queue
from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)


def enqueue_task(
    db: Session,
    task,
    *,
    queue_name: str | None = None,
    entry_point: str = "app.jobs.agent_task_runner.run_agent_task",
) -> bool:
    """Commit the current DB transaction, then enqueue the task to RQ.

    If Redis enqueue fails, the task is marked 'failed' so no orphan
    row blocks duplicate guards.  Returns True on success.

    The caller is responsible for setting all task fields (launch_id,
    agent_type, etc.) before calling this function.  The DB session
    should have uncommitted changes (flush is fine, commit is not).
    """
    from app.jobs.agent_task_runner import _queue_for_task

    resolved_queue = queue_name or _queue_for_task(task.task_type)

    # Step 1: commit the task row
    db.commit()
    db.refresh(task)

    # Step 2: enqueue to Redis
    try:
        conn = redis_lib.from_url(settings.REDIS_URL)
        q = Queue(resolved_queue, connection=conn)
        q.enqueue(entry_point, task.id)
        logger.info(
            "Enqueued task %s (%s) to queue=%s",
            task.id, task.task_type, resolved_queue,
        )
        return True
    except Exception:
        logger.exception(
            "Redis enqueue failed for task %s (%s), marking failed",
            task.id, task.task_type,
        )
        task.status = "failed"
        task.error_message = "Failed to enqueue task — Redis unavailable"
        db.commit()
        return False
