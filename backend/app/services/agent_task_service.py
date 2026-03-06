from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.agent_task import AgentTask, AgentTaskStep

# Default step lists per task_type. Every known task type must have at least
# one step so the runner doesn't produce false-green completions.
DEFAULT_STEPS: dict[str, list[str]] = {
    "community_scan": ["fetch_posts", "analyze_posts", "create_evidence"],
    "evidence_synthesis": ["gather_evidence", "run_synthesis", "store_result"],
    "consistency_check": ["gather_scores", "run_check", "store_result"],
    "review_summary": ["gather_metrics", "generate_summary", "store_result"],
}

VALID_TASK_TYPES: set[str] = set(DEFAULT_STEPS.keys())


def create_task(
    db: Session,
    *,
    idea_id: str,
    user_id: str,
    task_type: str,
    priority: int = 0,
    idempotency_key: Optional[str] = None,
    input_params: Optional[dict] = None,
    steps: Optional[list[str]] = None,
) -> AgentTask:
    """Create a new agent task. If an idempotency_key is provided and a
    non-terminal task already exists, return the existing one."""
    if idempotency_key:
        existing = (
            db.query(AgentTask)
            .filter_by(idempotency_key=idempotency_key)
            .filter(AgentTask.status.in_(["queued", "claimed", "running", "completed"]))
            .first()
        )
        if existing:
            return existing

    task = AgentTask(
        id=str(uuid.uuid4()),
        idea_id=idea_id,
        user_id=user_id,
        task_type=task_type,
        status="queued",
        priority=priority,
        idempotency_key=idempotency_key,
        input_params=input_params,
    )
    db.add(task)
    db.flush()

    # Use explicit steps if provided, otherwise fall back to defaults for the task_type
    step_names = steps or DEFAULT_STEPS.get(task_type, [])
    for i, step_name in enumerate(step_names):
        step = AgentTaskStep(
            id=str(uuid.uuid4()),
            task_id=task.id,
            step_order=i,
            step_name=step_name,
            status="pending",
        )
        db.add(step)

    db.commit()
    db.refresh(task)
    return task


def claim_task(
    db: Session,
    worker_id: str,
    task_types: Optional[list[str]] = None,
) -> Optional[AgentTask]:
    """Claim the next queued task using FOR UPDATE SKIP LOCKED (Postgres)."""
    q = db.query(AgentTask).filter(AgentTask.status == "queued")
    if task_types:
        q = q.filter(AgentTask.task_type.in_(task_types))
    q = q.order_by(AgentTask.priority.desc(), AgentTask.created_at.asc())

    task = q.with_for_update(skip_locked=True).first()
    if task:
        task.status = "claimed"
        task.claimed_by = worker_id
        task.claimed_at = datetime.now(timezone.utc)
        db.commit()
    return task


def start_task(db: Session, task: AgentTask) -> AgentTask:
    """Transition a claimed task to running."""
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    db.commit()
    return task


def complete_step(
    db: Session,
    step: AgentTaskStep,
    output_data: Optional[dict] = None,
) -> AgentTaskStep:
    """Mark a step as completed."""
    step.status = "completed"
    step.output_data = output_data
    step.completed_at = datetime.now(timezone.utc)
    db.commit()
    return step


def fail_step(
    db: Session,
    step: AgentTaskStep,
    error_message: str,
) -> AgentTaskStep:
    """Mark a step as failed."""
    step.status = "failed"
    step.error_message = error_message[:2000]
    step.completed_at = datetime.now(timezone.utc)
    db.commit()
    return step


def start_step(db: Session, step: AgentTaskStep, input_data: Optional[dict] = None) -> AgentTaskStep:
    """Mark a step as running."""
    step.status = "running"
    step.started_at = datetime.now(timezone.utc)
    step.input_data = input_data
    db.commit()
    return step


def complete_task(
    db: Session,
    task: AgentTask,
    output: Optional[dict] = None,
) -> AgentTask:
    """Mark task as completed."""
    task.status = "completed"
    task.output = output
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    return task


def fail_task(
    db: Session,
    task: AgentTask,
    error_message: str,
    *,
    terminal: bool = False,
) -> AgentTask:
    """Mark task as failed.

    If ``terminal`` is True (e.g. missing handler, lock loss), go straight
    to dead_letter regardless of retry count.  Otherwise re-queue if
    retries remain.
    """
    task.error_message = error_message[:2000]
    task.retry_count += 1

    if terminal or task.retry_count >= task.max_retries:
        task.status = "dead_letter"
        task.completed_at = datetime.now(timezone.utc)
    else:
        task.status = "queued"
        task.claimed_by = None
        task.claimed_at = None

    db.commit()
    return task


def cancel_task(db: Session, task: AgentTask) -> AgentTask:
    """Cancel a task that hasn't started running yet."""
    if task.status not in ("queued", "claimed"):
        raise ValueError(f"Cannot cancel task in status '{task.status}'")
    task.status = "cancelled"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    return task
