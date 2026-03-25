"""RQ entry point for agent tasks.

Claims a task from the queue using SELECT ... FOR UPDATE SKIP LOCKED,
runs each step in order, and handles retries/failure.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone

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
from app.services.workdir_service import create_workdir, cleanup_workdir

logger = logging.getLogger(__name__)

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"

LOCK_TTL = 300        # 5 minutes
LOCK_RENEW_INTERVAL = 60  # renew every 60 seconds

# Task types that get an ephemeral working directory
WORKDIR_TASK_TYPES: set[str] = {"scaffold", "deploy", "promote", "provision"}


class LockLostError(RuntimeError):
    """Raised when the advisory lock can no longer be renewed."""


# --- Queue routing -----------------------------------------------------------
# Map task types to their dedicated RQ queues so split workers pick them up.
TASK_QUEUE_MAP: dict[str, str] = {
    "provision": "provision",
    "scaffold": "engineering",
    "deploy": "engineering",
    "promote": "engineering",
    "metrics_collection": "ceo",
    "ceo_nightly": "ceo",
    "send_cold_emails": "marketing",
    "post_social": "marketing",
    "write_content": "marketing",
    "triage_inbox": "support",
    "draft_support_response": "support",
    "check_escalations": "support",
}

def _queue_for_task(task_type: str) -> str:
    """Return the RQ queue name for a given task type."""
    return TASK_QUEUE_MAP.get(task_type, "agent_tasks")


# --- Approval classification --------------------------------------------------
# Task types that require founder approval. "approve_once" checks for a standing
# grant first; "always_approve" always pauses for explicit approval.
APPROVE_ONCE_TYPES: set[str] = {
    "scaffold", "deploy",
    # Note: send_cold_emails and post_social only generate drafts in Phase 2.
    # Approval gates will be added when send/publish steps are implemented.
}
ALWAYS_APPROVE_TYPES: set[str] = {
    "promote",
}
# Everything else (provision, metrics_collection, ceo_nightly, community_scan,
# evidence_synthesis, consistency_check, review_summary, write_content) is auto-execute.
# Note: write_content generates drafts only (no external action), so no approval needed.


class TokenBudgetExceeded(RuntimeError):
    """Raised when a task exceeds its per-task token budget."""


# --- Step handler registry ---------------------------------------------------
# Map (task_type, step_name) → callable(db, task, step, input_data) → dict
from app.jobs.step_handlers import HANDLER_REGISTRY, ApprovalRequired
from app.services.budget_service import BudgetExceeded
STEP_HANDLERS: dict[tuple[str, str], object] = HANDLER_REGISTRY


class _LockHeartbeat:
    """Background thread that periodically renews a Redis advisory lock.

    Sets the ``lost`` event when renewal fails so the main thread can abort.
    """

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
        self.lost = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        consecutive_errors = 0
        while not self._stop.wait(timeout=LOCK_RENEW_INTERVAL):
            try:
                conn = redis.from_url(self._redis_url)
                renewed = renew_project_lock(
                    conn, self._idea_id, self._task_type, self._token, LOCK_TTL,
                )
                if not renewed:
                    logger.warning(
                        "Lock renewal failed for %s/%s — signalling abort",
                        self._idea_id, self._task_type,
                    )
                    self.lost.set()
                    break
                consecutive_errors = 0
            except Exception:
                consecutive_errors += 1
                logger.exception(
                    "Error renewing lock for %s/%s (attempt %d)",
                    self._idea_id, self._task_type, consecutive_errors,
                )
                # If Redis is unreachable for 2 consecutive intervals
                # (~2 minutes), the lock TTL (5 min) will expire soon.
                # Signal lost to prevent running without a valid lock.
                if consecutive_errors >= 2:
                    logger.warning(
                        "Redis unreachable for %d renewal attempts for %s/%s — signalling abort",
                        consecutive_errors, self._idea_id, self._task_type,
                    )
                    self.lost.set()
                    break


def _execute_step(db, task, step):
    """Dispatch a step to its registered handler, or fail if none exists."""
    handler_key = (task.task_type, step.step_name)
    handler = STEP_HANDLERS.get(handler_key)
    if handler is None:
        raise NotImplementedError(
            f"No handler registered for step '{step.step_name}' "
            f"of task type '{task.task_type}'. "
            f"Register it in STEP_HANDLERS before running this task type."
        )
    return handler(db, task, step, step.input_data)


def run_agent_task(task_id: str) -> None:
    """RQ entry point. Claim and execute an agent task by ID."""
    db = SessionLocal()
    lock_token = None
    idea_id = None
    task_type = None
    heartbeat = None
    workdir_path = None

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
                logger.info("Lock held for %s/%s — re-enqueueing task %s", idea_id, task_type, task_id)
                from rq import Queue
                q = Queue(_queue_for_task(task_type), connection=redis_conn)
                q.enqueue_in(
                    timedelta(seconds=30),
                    "app.jobs.agent_task_runner.run_agent_task",
                    task_id,
                )
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

        # --- Always-approve gate ---
        # These task types always require explicit approval. Grants are
        # never checked because the spec mandates human confirmation
        # every time (e.g., production promotions, refund processing).
        if task.task_type in ALWAYS_APPROVE_TYPES and task.approval_status != "approved":
            from app.services.approval_service import create_approval_request
            from app.jobs.step_handlers import _send_approval_notification

            artifact_id = (task.input_params or {}).get(
                "commit_sha"
            ) or (task.input_params or {}).get("artifact_id")
            raw_token = create_approval_request(db, task, artifact_id=artifact_id)
            task.status = "waiting_for_approval"
            db.commit()

            _send_approval_notification(db, task, raw_token, artifact_id)
            logger.info(
                "Task %s (%s) always requires approval, pausing",
                task_id, task.task_type,
            )
            return

        # --- Approve-once gate ---
        # Check for a standing grant. If one exists, auto-approve.
        # If not, pause for explicit approval and create a grant on
        # first approval so subsequent tasks auto-execute.
        if task.task_type in APPROVE_ONCE_TYPES and task.approval_status != "approved":
            if task.launch_id:
                from app.services.approval_service import check_grant, create_approval_request
                grant = check_grant(db, task.launch_id, task.task_type)
                if grant:
                    task.approval_status = "approved"
                    db.commit()
                    logger.info(
                        "Task %s auto-approved via grant %s", task_id, grant.id,
                    )
                else:
                    # No grant, no approval. Create approval request and pause.
                    # Bind to artifact if available (e.g. commit SHA for deploys)
                    artifact_id = (task.input_params or {}).get(
                        "commit_sha"
                    ) or (task.input_params or {}).get("artifact_id")
                    raw_token = create_approval_request(db, task, artifact_id=artifact_id)
                    task.status = "waiting_for_approval"
                    db.commit()

                    # Deliver the raw token via email + cache in Redis
                    from app.jobs.step_handlers import _send_approval_notification
                    _send_approval_notification(db, task, raw_token, artifact_id)
                    logger.info(
                        "Task %s (%s) requires approve-once approval, pausing",
                        task_id, task.task_type,
                    )
                    return

        # --- Ephemeral workdir for engineering tasks ---
        if task.task_type in WORKDIR_TASK_TYPES:
            workdir_path = create_workdir(task.id)
            task.input_params = {**(task.input_params or {}), "workdir": workdir_path}
            db.commit()
            logger.info("Assigned workdir=%s for task=%s", workdir_path, task_id)

        # --- Token budget enforcement ---
        if task.token_budget and task.tokens_used and task.tokens_used >= task.token_budget:
            raise TokenBudgetExceeded(
                f"Task {task_id} has already used {task.tokens_used} tokens "
                f"(budget: {task.token_budget})"
            )

        # Execute steps in order
        for step in sorted(task.steps, key=lambda s: s.step_order):
            # Abort if the lock was lost between steps
            if heartbeat and heartbeat.lost.is_set():
                raise LockLostError(
                    f"Advisory lock lost for {idea_id}/{task_type} — aborting to prevent duplicate execution"
                )

            if step.status == "completed":
                continue  # Resume from last completed step

            step = start_step(db, step)
            try:
                output = _execute_step(db, task, step)
                step = complete_step(db, step, output_data=output)

                # Accumulate per-step token usage into the task total
                if step.tokens_used:
                    task.tokens_used = (task.tokens_used or 0) + step.tokens_used
                    db.commit()

                # Check token budget after each step
                if task.token_budget and (task.tokens_used or 0) >= task.token_budget:
                    raise TokenBudgetExceeded(
                        f"Task {task_id} exceeded token budget after step '{step.step_name}': "
                        f"used {task.tokens_used}, budget {task.token_budget}"
                    )
            except ApprovalRequired:
                # Not a failure. The step created an approval request and
                # the task should pause until the founder approves.
                step.status = "pending"
                step.completed_at = None
                task.status = "waiting_for_approval"
                db.commit()
                logger.info(
                    "AgentTask %s paused at step '%s' — waiting for approval",
                    task_id, step.step_name,
                )
                return  # Exit cleanly, no failure handling
            except Exception as exc:
                fail_step(db, step, str(exc))
                raise

        complete_task(db, task, output={"steps_completed": len(task.steps)})
        logger.info("AgentTask %s completed successfully", task_id)

    except Exception as exc:
        logger.exception("AgentTask %s failed", task_id)
        db.rollback()

        # Non-retryable errors go straight to dead_letter
        from app.services.bounce_detector import OutboundPausedError
        is_terminal = isinstance(exc, (LockLostError, NotImplementedError, TokenBudgetExceeded, BudgetExceeded, OutboundPausedError))

        task = db.query(AgentTask).filter_by(id=task_id).first()
        if task:
            fail_task(db, task, str(exc), terminal=is_terminal)

            # Re-enqueue if fail_task re-queued it (retries remain, retryable error)
            if task.status == "queued":
                try:
                    redis_conn = redis.from_url(settings.REDIS_URL)
                    from rq import Queue
                    q = Queue(_queue_for_task(task.task_type), connection=redis_conn)
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

        # Clean up ephemeral working directory
        if workdir_path:
            cleanup_workdir(workdir_path)

        # Release advisory lock
        if lock_token and idea_id and task_type:
            try:
                redis_conn = redis.from_url(settings.REDIS_URL)
                release_project_lock(redis_conn, idea_id, task_type, lock_token)
            except Exception:
                logger.exception("Failed to release lock for %s/%s", idea_id, task_type)
        db.close()
