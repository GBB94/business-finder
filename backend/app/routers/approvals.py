from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.agent_task import AgentTask
from app.models.approval_grant import ApprovalGrant
from app.models.launch_instance import LaunchInstance
from app.models.user import User
from app.schemas.approval import (
    ApprovalGrantListResponse,
    ApprovalGrantResponse,
    ApprovalTaskResponse,
    ApproveRequest,
    PendingApprovalListResponse,
)
from app.services import approval_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def _get_cached_token(task_id: str) -> str | None:
    """Retrieve a cached approval token from Redis.

    Returns the raw token if found, None otherwise. The token auto-expires
    with the approval TTL so stale tokens are never returned.
    """
    try:
        import redis as redis_lib
        from app.config import settings
        conn = redis_lib.from_url(settings.REDIS_URL)
        token = conn.get(f"approval_token:{task_id}")
        return token.decode() if token else None
    except Exception:
        logger.debug("Could not retrieve cached token for task=%s", task_id)
        return None


# ── Fixed-path routes (must be registered before /{task_id}) ───────────────

@router.get("/pending", response_model=PendingApprovalListResponse)
def list_pending_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all agent tasks owned by the user that are pending approval."""
    pending_tasks = (
        db.query(AgentTask)
        .filter(
            AgentTask.user_id == current_user.id,
            AgentTask.approval_status == "pending_approval",
        )
        .order_by(AgentTask.created_at.desc())
        .all()
    )

    items = []
    for task in pending_tasks:
        summary = (task.input_params or {}).get("approval_summary", task.task_type)
        channel = (task.input_params or {}).get("channel_or_provider")

        items.append(ApprovalTaskResponse(
            id=task.id,
            task_id=task.id,
            launch_id=task.launch_id or "",
            task_type=task.task_type,
            channel_or_provider=channel,
            summary=summary,
            details=task.input_params,
            artifact_id=task.approval_artifact_id,
            expires_at=task.approval_expires_at,
            created_at=task.created_at,
        ))

    return PendingApprovalListResponse(items=items, total=len(items))


@router.get("/grants", response_model=ApprovalGrantListResponse)
def list_grants(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all approval grants for launches owned by the authenticated user."""
    user_launch_ids = [
        lid for (lid,) in
        db.query(LaunchInstance.id).filter(LaunchInstance.user_id == current_user.id).all()
    ]
    if not user_launch_ids:
        return ApprovalGrantListResponse(items=[], total=0)

    grants = (
        db.query(ApprovalGrant)
        .filter(ApprovalGrant.launch_id.in_(user_launch_ids))
        .order_by(ApprovalGrant.granted_at.desc())
        .all()
    )
    return ApprovalGrantListResponse(
        items=[ApprovalGrantResponse.model_validate(g) for g in grants],
        total=len(grants),
    )


@router.delete("/grants/{grant_id}", status_code=204)
def revoke_grant(
    grant_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    grant = db.query(ApprovalGrant).filter_by(id=grant_id).first()
    if not grant:
        raise HTTPException(404, "Grant not found")

    # Verify ownership through launch
    launch = db.query(LaunchInstance).filter_by(
        id=grant.launch_id, user_id=current_user.id
    ).first()
    if not launch:
        raise HTTPException(404, "Grant not found")

    if grant.revoked_at is not None:
        raise HTTPException(400, "Grant already revoked")

    try:
        approval_service.revoke_grant(db, grant_id, "Revoked by founder from dashboard")
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Parameterized routes ───────────────────────────────────────────────────

@router.get("/{task_id}")
def get_approval_detail(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(AgentTask).filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
        raise HTTPException(404, "Approval task not found")

    # Retrieve the cached token from Redis (only for the detail endpoint,
    # never in the list endpoint). This is the fallback when email delivery
    # failed. The token lives only in Redis with a TTL, not in the database.
    cached_token = None
    if task.approval_status == "pending_approval":
        cached_token = _get_cached_token(task.id)

    return ApprovalTaskResponse(
        id=task.id,
        task_id=task.id,
        launch_id=task.launch_id or "",
        task_type=task.task_type,
        channel_or_provider=(task.input_params or {}).get("channel_or_provider"),
        summary=(task.input_params or {}).get("approval_summary", task.task_type),
        details=task.input_params,
        artifact_id=task.approval_artifact_id,
        expires_at=task.approval_expires_at,
        approval_token=cached_token,
        created_at=task.created_at,
    )


@router.post("/{task_id}/approve", status_code=200)
def approve_task(
    task_id: str,
    body: ApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Verify the task belongs to the user
    task = db.query(AgentTask).filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
        raise HTTPException(404, "Approval task not found")

    try:
        approved_task = approval_service.verify_and_approve(
            db, task_id, body.approval_token, artifact_id=body.artifact_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Optionally create a standing grant for approve-once task types
    grant = None
    if body.create_grant and task.launch_id:
        grant = approval_service.create_grant(
            db,
            launch_id=task.launch_id,
            task_type=task.task_type,
            granted_by=current_user.id,
            original_task_id=task.id,
            channel_or_provider=(task.input_params or {}).get("channel_or_provider"),
        )

    result = {"ok": True, "task_id": task_id, "status": approved_task.approval_status}
    if grant:
        result["grant_id"] = grant.id
    return result


@router.post("/{task_id}/reject")
def reject_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.query(AgentTask).filter_by(id=task_id, user_id=current_user.id).first()
    if not task:
        raise HTTPException(404, "Approval task not found")

    try:
        approval_service.reject_approval(db, task_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"ok": True, "task_id": task_id, "status": "rejected"}
