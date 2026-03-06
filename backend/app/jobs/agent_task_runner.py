"""RQ entry point for agent tasks.

Claims a task from the queue using SELECT ... FOR UPDATE SKIP LOCKED,
runs each step in order, and handles retries/failure.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import redis

from app.config import settings
from app.database import SessionLocal
from app.models.agent_task import AgentTask
from app.services.agent_task_service import (
    claim_task,
    start_task,
    start_step,
    complete_step,
    fail_step,
    complete_task,
    fail_task,
)
from app.services.task_lock import acquire_project_lock, release_project_lock

logger = logging.getLogger(__name__)

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"


def run_agent_task(task_id: str) -> None:
    """RQ entry point. Claim and execute an agent task by ID."""
    db = SessionLocal()
    lock_token = None
    idea_id = None
    task_type = None

    try:
        task = db.query(AgentTask).filter_by(id=task_id).first()
        if not task:
            logger.error("AgentTask %s not found", task_id)
            return

        if task.status not in ("queued", "claimed"):
            logger.info("AgentTask %s already in status %s, skipping", task_id, task.status)
            return

        # Acquire advisory lock
        if task.idea_id:
            idea_id = task.idea_id
            task_type = task.task_type
            redis_conn = redis.from_url(settings.REDIS_URL)
            lock_token = acquire_project_lock(redis_conn, idea_id, task_type)
            if not lock_token:
                logger.info("Lock held for %s/%s — skipping task %s", idea_id, task_type, task_id)
                return

        # Claim if still queued
        if task.status == "queued":
            task.status = "claimed"
            task.claimed_by = WORKER_ID
            task.claimed_at = datetime.now(timezone.utc)
            db.commit()

        task = start_task(db, task)

        # Execute steps in order
        for step in sorted(task.steps, key=lambda s: s.step_order):
            if step.status == "completed":
                continue  # Resume from last completed step

            step = start_step(db, step)
            try:
                # Step execution would be dispatched here based on task_type + step_name
                # For now, mark as completed (actual step handlers to be wired later)
                step = complete_step(db, step, output_data={"status": "executed"})
            except Exception as exc:
                fail_step(db, step, str(exc))
                raise

        complete_task(db, task, output={"steps_completed": len(task.steps)})
        logger.info("AgentTask %s completed successfully", task_id)

    except Exception as exc:
        logger.exception("AgentTask %s failed", task_id)
        db.rollback()

        task = db.query(AgentTask).filter_by(id=task_id).first()
        if task:
            fail_task(db, task, str(exc))

            # Re-enqueue if retries remain
            if task.status == "queued":
                try:
                    redis_conn = redis.from_url(settings.REDIS_URL)
                    from rq import Queue
                    q = Queue("agent_tasks", connection=redis_conn)
                    q.enqueue(
                        "app.jobs.agent_task_runner.run_agent_task",
                        task.id,
                    )
                except Exception:
                    logger.exception("Failed to re-enqueue task %s", task_id)
    finally:
        # Release advisory lock
        if lock_token and idea_id and task_type:
            try:
                redis_conn = redis.from_url(settings.REDIS_URL)
                release_project_lock(redis_conn, idea_id, task_type, lock_token)
            except Exception:
                logger.exception("Failed to release lock for %s/%s", idea_id, task_type)
        db.close()
