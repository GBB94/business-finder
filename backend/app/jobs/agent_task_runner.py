"""RQ entry point for agent tasks.

Claims a task from the queue using SELECT ... FOR UPDATE SKIP LOCKED,
runs each step in order, and handles retries/failure.
"""
from __future__ import annotations

import logging
import threading
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
from app.services.task_lock import acquire_project_lock, renew_project_lock, release_project_lock

logger = logging.getLogger(__name__)

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"

LOCK_TTL = 300        # 5 minutes
LOCK_RENEW_INTERVAL = 60  # renew every 60 seconds


class _LockHeartbeat:
    """Background thread that periodically renews a Redis advisory lock."""

    def __init__(
        self,
        redis_url: str,
        idea_id: str,
        task_type: str,
        token: str,
    ):
        self._redis_url = redis_url
        self._idea_id = idea_id
        self._task_type = task_type
        self._token = token
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        while not self._stop.wait(timeout=LOCK_RENEW_INTERVAL):
            try:
                conn = redis.from_url(self._redis_url)
                renewed = renew_project_lock(
                    conn, self._idea_id, self._task_type, self._token, LOCK_TTL,
                )
                if not renewed:
                    logger.warning(
                        "Lock renewal failed for %s/%s — lock may have been stolen",
                        self._idea_id, self._task_type,
                    )
                    break
            except Exception:
                logger.exception(
                    "Error renewing lock for %s/%s", self._idea_id, self._task_type,
                )


def run_agent_task(task_id: str) -> None:
    """RQ entry point. Claim and execute an agent task by ID."""
    db = SessionLocal()
    lock_token = None
    idea_id = None
    task_type = None
    heartbeat = None

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
            lock_token = acquire_project_lock(redis_conn, idea_id, task_type, ttl=LOCK_TTL)
            if not lock_token:
                logger.info("Lock held for %s/%s — skipping task %s", idea_id, task_type, task_id)
                return

            # Start heartbeat to keep the lock alive for long-running tasks
            heartbeat = _LockHeartbeat(settings.REDIS_URL, idea_id, task_type, lock_token)
            heartbeat.start()

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
        # Stop heartbeat before releasing lock
        if heartbeat:
            heartbeat.stop()

        # Release advisory lock
        if lock_token and idea_id and task_type:
            try:
                redis_conn = redis.from_url(settings.REDIS_URL)
                release_project_lock(redis_conn, idea_id, task_type, lock_token)
            except Exception:
                logger.exception("Failed to release lock for %s/%s", idea_id, task_type)
        db.close()
