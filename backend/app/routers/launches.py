from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.agent_task import AgentTask
from app.models.audit_log import AuditLog
from app.models.daily_log import DailyLog
from app.models.idea import Idea
from app.models.launch_instance import LaunchInstance
from app.models.operational_event import OperationalEvent
from app.models.project_metrics_daily import ProjectMetricsDaily
from app.models.user import User
from app.services.agent_task_service import create_task
from app.services.task_enqueue import enqueue_task
from app.schemas.agent_task import AgentTaskResponse, AgentTaskListResponse
from app.schemas.launch import (
    AuditLogListResponse,
    AuditLogResponse,
    DailyLogListResponse,
    DailyLogResponse,
    LaunchCreate,
    LaunchListResponse,
    LaunchResponse,
    LaunchUpdate,
    OperationalEventListResponse,
    OperationalEventResponse,
    ProjectMetricsDailyListResponse,
    ProjectMetricsDailyResponse,
)

router = APIRouter(prefix="/api/launches", tags=["launches"])

VALID_STATUSES = {"provisioning", "preview", "active", "paused", "killed"}

# Allowed status transitions
ALLOWED_TRANSITIONS = {
    "provisioning": {"preview", "killed"},
    "preview": {"active", "killed"},
    "active": {"paused", "killed"},
    "paused": {"active", "killed"},
    "killed": set(),  # terminal
}


def _get_launch_or_404(launch_id: str, user_id: str, db: Session) -> LaunchInstance:
    launch = db.query(LaunchInstance).filter_by(id=launch_id, user_id=user_id).first()
    if not launch:
        raise HTTPException(404, "Launch not found")
    return launch


def _to_response(launch: LaunchInstance, db: Session) -> LaunchResponse:
    idea = db.query(Idea).filter_by(id=launch.idea_id).first()
    resp = LaunchResponse.model_validate(launch)
    resp.idea_name = idea.name if idea else None
    return resp


def _write_audit(
    db: Session,
    launch_id: str,
    actor: str,
    action: str,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(AuditLog(
        launch_id=launch_id,
        actor=actor,
        action=action,
        details=details,
        ip_address=ip_address,
    ))


# ── CRUD ────────────────────────────────────────────────────────────────────

@router.post("", response_model=LaunchResponse, status_code=201)
def create_launch(
    body: LaunchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    idea = db.query(Idea).filter_by(id=body.idea_id, user_id=current_user.id).first()
    if not idea:
        raise HTTPException(404, "Idea not found")

    launch = LaunchInstance(
        idea_id=body.idea_id,
        user_id=current_user.id,
        status="provisioning",
        daily_budget_cap=body.daily_budget_cap,
    )
    db.add(launch)
    db.flush()

    launch.secret_ref = f"project-{launch.id}"

    _write_audit(db, launch.id, "founder", "launch_created", {
        "idea_id": body.idea_id,
        "daily_budget_cap": body.daily_budget_cap,
    })

    # Create and enqueue the provision task
    task = create_task(
        db,
        idea_id=body.idea_id,
        user_id=current_user.id,
        task_type="provision",
        input_params={
            "launch_id": launch.id,
            "idea_name": idea.name,
        },
    )
    # Set launch_id on the task (create_task doesn't know about it)
    task.launch_id = launch.id
    task.agent_type = "engineering"

    if not enqueue_task(db, task):
        launch.status = "killed"
        _write_audit(db, launch.id, "system", "task_failed", {
            "reason": "Redis unavailable during launch creation",
        })
        db.commit()

    db.refresh(launch)

    return _to_response(launch, db)


@router.get("", response_model=LaunchListResponse)
def list_launches(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(LaunchInstance).filter(LaunchInstance.user_id == current_user.id)
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(422, f"Invalid status filter: {status}")
        q = q.filter(LaunchInstance.status == status)
    q = q.order_by(LaunchInstance.created_at.desc())
    launches = q.all()
    return LaunchListResponse(
        items=[_to_response(l, db) for l in launches],
        total=len(launches),
    )


@router.get("/portfolio/metrics")
def portfolio_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get latest metrics for all active launches (portfolio view)."""
    launches = (
        db.query(LaunchInstance)
        .filter(
            LaunchInstance.user_id == current_user.id,
            LaunchInstance.status.in_(["active", "preview", "paused"]),
        )
        .all()
    )

    from sqlalchemy import func
    from app.models.support_thread import SupportThread

    result = []
    for launch in launches:
        idea = db.query(Idea).filter_by(id=launch.idea_id).first()

        # Latest metrics row
        latest = (
            db.query(ProjectMetricsDaily)
            .filter_by(launch_id=launch.id)
            .order_by(ProjectMetricsDaily.date.desc())
            .first()
        )

        # Support thread counts
        open_threads = (
            db.query(func.count(SupportThread.id))
            .filter(
                SupportThread.launch_id == launch.id,
                SupportThread.status.in_(["open", "escalated"]),
            )
            .scalar()
        ) or 0

        escalated_threads = (
            db.query(func.count(SupportThread.id))
            .filter(
                SupportThread.launch_id == launch.id,
                SupportThread.status == "escalated",
            )
            .scalar()
        ) or 0

        result.append({
            "launch_id": launch.id,
            "idea_name": idea.name if idea else None,
            "status": launch.status,
            "daily_budget_cap": launch.daily_budget_cap,
            "total_spend_to_date": launch.total_spend_to_date,
            "created_at": launch.created_at.isoformat() if launch.created_at else None,
            "preview_url": launch.preview_url,
            "production_url": launch.production_url,
            "latest_metrics": {
                "date": latest.date.isoformat() if latest else None,
                "signups": latest.signups if latest else 0,
                "active_users": latest.active_users if latest else 0,
                "activation_rate": latest.activation_rate if latest else None,
                "revenue_cents": latest.revenue_cents if latest else 0,
                "total_spend_cents": latest.total_spend_cents if latest else 0,
                "error_count": latest.error_count if latest else 0,
            } if latest else None,
            "support": {
                "open_threads": open_threads,
                "escalated_threads": escalated_threads,
            },
        })

    return {"items": result, "total": len(result)}


@router.get("/{launch_id}", response_model=LaunchResponse)
def get_launch(
    launch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    launch = _get_launch_or_404(launch_id, current_user.id, db)
    return _to_response(launch, db)


@router.patch("/{launch_id}", response_model=LaunchResponse)
def update_launch(
    launch_id: str,
    body: LaunchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    launch = _get_launch_or_404(launch_id, current_user.id, db)

    if body.status is not None and body.status != launch.status:
        allowed = ALLOWED_TRANSITIONS.get(launch.status, set())
        if body.status not in allowed:
            raise HTTPException(
                400,
                f"Cannot transition from '{launch.status}' to '{body.status}'. "
                f"Allowed: {sorted(allowed) if allowed else 'none (terminal state)'}",
            )
        old_status = launch.status
        launch.status = body.status
        _write_audit(db, launch.id, "founder", f"project_{body.status}", {
            "from_status": old_status,
            "to_status": body.status,
        })

    if body.daily_budget_cap is not None:
        old_budget = launch.daily_budget_cap
        launch.daily_budget_cap = body.daily_budget_cap
        _write_audit(db, launch.id, "founder", "budget_changed", {
            "old_budget": old_budget,
            "new_budget": body.daily_budget_cap,
        })

    db.add(launch)
    db.commit()
    db.refresh(launch)
    return _to_response(launch, db)


# ── Sub-resources ───────────────────────────────────────────────────────────

@router.get("/{launch_id}/events", response_model=OperationalEventListResponse)
def list_events(
    launch_id: str,
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_launch_or_404(launch_id, current_user.id, db)

    q = db.query(OperationalEvent).filter(OperationalEvent.launch_id == launch_id)
    if event_type:
        q = q.filter(OperationalEvent.event_type == event_type)
    total = q.count()
    events = q.order_by(OperationalEvent.created_at.desc()).offset(offset).limit(limit).all()
    return OperationalEventListResponse(
        items=[OperationalEventResponse.model_validate(e) for e in events],
        total=total,
    )


@router.get("/{launch_id}/metrics", response_model=ProjectMetricsDailyListResponse)
def get_metrics(
    launch_id: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_launch_or_404(launch_id, current_user.id, db)

    q = db.query(ProjectMetricsDaily).filter(ProjectMetricsDaily.launch_id == launch_id)
    if start_date:
        q = q.filter(ProjectMetricsDaily.date >= start_date)
    if end_date:
        q = q.filter(ProjectMetricsDaily.date <= end_date)
    rows = q.order_by(ProjectMetricsDaily.date.asc()).all()
    return ProjectMetricsDailyListResponse(
        items=[ProjectMetricsDailyResponse.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.get("/{launch_id}/daily-logs", response_model=DailyLogListResponse)
def list_daily_logs(
    launch_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_launch_or_404(launch_id, current_user.id, db)

    logs = (
        db.query(DailyLog)
        .filter(DailyLog.launch_id == launch_id)
        .order_by(DailyLog.date.desc())
        .all()
    )
    return DailyLogListResponse(
        items=[DailyLogResponse.model_validate(l) for l in logs],
        total=len(logs),
    )


@router.get("/{launch_id}/audit-log", response_model=AuditLogListResponse)
def list_audit_log(
    launch_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_launch_or_404(launch_id, current_user.id, db)

    q = db.query(AuditLog).filter(AuditLog.launch_id == launch_id)
    total = q.count()
    entries = q.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()
    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(e) for e in entries],
        total=total,
    )


# ── Manual task triggers ───────────────────────────────────────────────────

# Task types that can be triggered manually from the dashboard
TRIGGERABLE_TASK_TYPES = {
    "scaffold", "deploy", "promote",
    "metrics_collection", "ceo_nightly",
    "send_cold_emails", "post_social", "write_content",
    "triage_inbox", "draft_support_response", "check_escalations",
}

# Agent type assignment
_AGENT_TYPE_MAP: dict[str, str] = {
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


class TriggerRequest(BaseModel):
    task_type: str
    input_params: Optional[dict] = None


@router.post("/{launch_id}/trigger", response_model=AgentTaskResponse, status_code=201)
def trigger_task(
    launch_id: str,
    body: TriggerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a task for this launch from the dashboard."""
    launch = _get_launch_or_404(launch_id, current_user.id, db)

    if body.task_type not in TRIGGERABLE_TASK_TYPES:
        raise HTTPException(
            422,
            f"Cannot manually trigger '{body.task_type}'. "
            f"Allowed: {sorted(TRIGGERABLE_TASK_TYPES)}",
        )

    if launch.status == "killed":
        raise HTTPException(400, "Cannot trigger tasks on a killed launch")

    task = create_task(
        db,
        idea_id=launch.idea_id,
        user_id=current_user.id,
        task_type=body.task_type,
        input_params=body.input_params or {},
    )
    task.launch_id = launch_id
    task.agent_type = _AGENT_TYPE_MAP.get(body.task_type, "engineering")

    _write_audit(db, launch_id, "founder", "task_created", {
        "task_type": body.task_type,
        "task_id": task.id,
        "manual_trigger": True,
    })

    enqueue_task(db, task)
    db.refresh(task)

    return AgentTaskResponse.model_validate(task)


@router.get("/{launch_id}/tasks", response_model=AgentTaskListResponse)
def list_launch_tasks(
    launch_id: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recent tasks for this launch."""
    _get_launch_or_404(launch_id, current_user.id, db)

    tasks = (
        db.query(AgentTask)
        .filter_by(launch_id=launch_id, user_id=current_user.id)
        .order_by(AgentTask.created_at.desc())
        .limit(limit)
        .all()
    )
    return AgentTaskListResponse(
        items=[AgentTaskResponse.model_validate(t) for t in tasks],
        total=len(tasks),
    )
