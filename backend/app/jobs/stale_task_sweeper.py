"""Periodic sweeper that recovers orphaned tasks.

A task can become orphaned if the process dies after committing the task
row but before the Redis enqueue completes (or if the RQ job is lost).
This sweeper finds tasks stuck in 'queued' or 'claimed' beyond a
threshold and re-enqueues them.

Run via RQ scheduler or cron:
    rq enqueue --queue=default app.jobs.stale_task_sweeper.sweep_stale_tasks
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import redis as redis_lib
from rq import Queue
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.agent_task import AgentTask

logger = logging.getLogger(__name__)

# Tasks stuck in 'queued' longer than this are considered orphaned
QUEUED_STALE_MINUTES = 10

# Tasks stuck in 'claimed' longer than this (worker died mid-claim)
CLAIMED_STALE_MINUTES = 15


def sweep_stale_tasks() -> dict:
    """Find and re-enqueue orphaned tasks. Returns a summary dict."""
    from app.jobs.agent_task_runner import _queue_for_task

    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    recovered = 0
    failed = 0

    try:
        # Find tasks that have been queued too long without a worker picking them up
        stale_queued = (
            db.query(AgentTask)
            .filter(
                AgentTask.status == "queued",
                AgentTask.created_at < now - timedelta(minutes=QUEUED_STALE_MINUTES),
            )
            .all()
        )

        # Find tasks claimed but never started (worker crashed after claim)
        stale_claimed = (
            db.query(AgentTask)
            .filter(
                AgentTask.status == "claimed",
                AgentTask.claimed_at < now - timedelta(minutes=CLAIMED_STALE_MINUTES),
            )
            .all()
        )

        stale_tasks = stale_queued + stale_claimed

        if not stale_tasks:
            logger.info("No stale tasks found")
            return {"recovered": 0, "failed": 0, "total_checked": 0}

        logger.warning("Found %d stale tasks, attempting recovery", len(stale_tasks))

        conn = redis_lib.from_url(settings.REDIS_URL)

        for task in stale_tasks:
            try:
                # Reset to queued so the runner can claim it fresh
                if task.status == "claimed":
                    task.status = "queued"
                    task.claimed_by = None
                    task.claimed_at = None
                    db.commit()

                queue_name = _queue_for_task(task.task_type)
                q = Queue(queue_name, connection=conn)
                q.enqueue("app.jobs.agent_task_runner.run_agent_task", task.id)
                recovered += 1
                logger.info(
                    "Re-enqueued stale task %s (%s) to queue=%s",
                    task.id, task.task_type, queue_name,
                )
            except Exception:
                logger.exception("Failed to recover stale task %s", task.id)
                # If we can't enqueue after multiple sweep cycles, the task's
                # retry_count will eventually push it to dead_letter via the
                # runner. Don't mark it failed here to allow future sweeps.
                failed += 1

        summary = {
            "recovered": recovered,
            "failed": failed,
            "total_checked": len(stale_tasks),
        }
        logger.info("Sweep complete: %s", summary)
        return summary

    finally:
        db.close()
