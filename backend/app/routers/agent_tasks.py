from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import redis
from rq import Queue

from app.config import settings

logger = logging.getLogger(__name__)
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.agent_task import AgentTask
from app.models.idea import Idea
from app.models.user import User
from app.schemas.agent_task import (
    AgentTaskCreate,
    AgentTaskResponse,
    AgentTaskListResponse,
)
from app.services.agent_task_service import create_task, cancel_task, VALID_TASK_TYPES

router = APIRouter(prefix="/api/ideas/{idea_id}/tasks", tags=["agent-tasks"])


def _get_idea_or_404(idea_id: str, user_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=user_id).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.post("", response_model=AgentTaskResponse, status_code=201)
def create_agent_task(
    idea_id: str,
    body: AgentTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    if body.task_type not in VALID_TASK_TYPES:
        raise HTTPException(
            422,
            f"Unknown task_type '{body.task_type}'. "
            f"Valid types: {sorted(VALID_TASK_TYPES)}",
        )

    task = create_task(
        db,
        idea_id=idea_id,
        user_id=current_user.id,
        task_type=body.task_type,
        priority=body.priority,
        idempotency_key=body.idempotency_key,
        input_params=body.input_params,
    )

    # Enqueue to RQ agent_tasks queue
    if task.status == "queued":
        try:
            conn = redis.from_url(settings.REDIS_URL)
            q = Queue("agent_tasks", connection=conn)
            q.enqueue(
                "app.jobs.agent_task_runner.run_agent_task",
                task.id,
            )
        except Exception:
            logger.exception("Failed to enqueue agent task %s to Redis", task.id)
            task.status = "failed"
            task.error_message = "Failed to enqueue task — Redis unavailable"
            db.commit()
            db.refresh(task)

    return AgentTaskResponse.model_validate(task)


@router.get("", response_model=AgentTaskListResponse)
def list_agent_tasks(
    idea_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    tasks = (
        db.query(AgentTask)
        .filter_by(idea_id=idea_id, user_id=current_user.id)
        .order_by(AgentTask.created_at.desc())
        .all()
    )
    return AgentTaskListResponse(
        items=[AgentTaskResponse.model_validate(t) for t in tasks],
        total=len(tasks),
    )


@router.get("/{task_id}", response_model=AgentTaskResponse)
def get_agent_task(
    idea_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    task = db.query(AgentTask).filter_by(
        id=task_id, idea_id=idea_id, user_id=current_user.id
    ).first()
    if not task:
        raise HTTPException(404, "Agent task not found")
    return AgentTaskResponse.model_validate(task)


@router.post("/{task_id}/cancel", response_model=AgentTaskResponse)
def cancel_agent_task(
    idea_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    task = db.query(AgentTask).filter_by(
        id=task_id, idea_id=idea_id, user_id=current_user.id
    ).first()
    if not task:
        raise HTTPException(404, "Agent task not found")

    try:
        task = cancel_task(db, task)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return AgentTaskResponse.model_validate(task)
