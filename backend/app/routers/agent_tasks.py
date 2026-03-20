from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import redis
from rq import Queue

from app.config import settings
from app.jobs.agent_task_runner import _queue_for_task

logger = logging.getLogger(__name__)
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.agent_task import AgentTask
from app.models.idea import Idea
from app.models.launch_instance import LaunchInstance
from app.models.user import User
from app.schemas.agent_task import (
    AgentTaskCreate,
    AgentTaskResponse,
    AgentTaskListResponse,
)
from app.services.agent_task_service import create_task, cancel_task, VALID_TASK_TYPES

router = APIRouter(prefix="/api/ideas/{idea_id}/tasks", tags=["agent-tasks"])

# Task types that belong to LaunchPad and require a launch_id
LAUNCHPAD_TASK_TYPES = {
    "provision", "scaffold", "deploy", "promote",
    "metrics_collection", "ceo_nightly",
}


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
    idea = _get_idea_or_404(idea_id, current_user.id, db)

    if body.task_type not in VALID_TASK_TYPES:
        raise HTTPException(
            422,
            f"Unknown task_type '{body.task_type}'. "
            f"Valid types: {sorted(VALID_TASK_TYPES)}",
        )

    # LaunchPad task types require a launch_id
    if body.task_type in LAUNCHPAD_TASK_TYPES:
        if not body.launch_id:
            raise HTTPException(
                422,
                f"Task type '{body.task_type}' requires a launch_id.",
            )
        launch = db.query(LaunchInstance).filter_by(
            id=body.launch_id, user_id=current_user.id,
        ).first()
        if not launch:
            raise HTTPException(404, "Launch not found")
        # Verify the launch belongs to the idea in the URL
        if launch.idea_id != idea_id:
            raise HTTPException(
                400,
                "Launch does not belong to this idea.",
            )
    elif body.launch_id:
        # Non-LaunchPad task with optional launch_id: still validate ownership
        launch = db.query(LaunchInstance).filter_by(
            id=body.launch_id, user_id=current_user.id
        ).first()
        if not launch:
            raise HTTPException(404, "Launch not found")

    task = create_task(
        db,
        idea_id=idea_id,
        user_id=current_user.id,
        task_type=body.task_type,
        priority=body.priority,
        idempotency_key=body.idempotency_key,
        input_params=body.input_params,
    )

    # Set LaunchPad fields if provided
    if body.launch_id:
        task.launch_id = body.launch_id
    if body.agent_type:
        task.agent_type = body.agent_type
    db.commit()
    db.refresh(task)

    # Enqueue to the correct queue based on task type
    if task.status == "queued":
        try:
            conn = redis.from_url(settings.REDIS_URL)
            queue_name = _queue_for_task(body.task_type)
            q = Queue(queue_name, connection=conn)
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
