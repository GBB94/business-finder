"""Approval flow management for LaunchPad agent tasks."""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.agent_task import AgentTask
from app.models.approval_grant import ApprovalGrant
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

APPROVAL_TTL_HOURS = 24


def generate_approval_token(
    task_id: str,
    artifact_id: Optional[str] = None,
) -> tuple[str, str]:
    """Generate a random approval token and its SHA-256 hash.

    Returns (raw_token, token_hash). The raw token is sent to the founder
    in a URL; only the hash is stored in the database.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    logger.info(
        "Generated approval token for task=%s artifact=%s",
        task_id,
        artifact_id,
    )
    return raw_token, token_hash


def create_approval_request(
    db: Session,
    task: AgentTask,
    artifact_id: Optional[str] = None,
) -> str:
    """Set a task to pending_approval and generate a one-time approval token.

    Returns the raw token (for embedding in an approval URL).
    """
    raw_token, token_hash = generate_approval_token(task.id, artifact_id)

    task.approval_status = "pending_approval"
    task.approval_token_hash = token_hash
    task.approval_expires_at = datetime.now(timezone.utc) + timedelta(hours=APPROVAL_TTL_HOURS)
    task.approval_artifact_id = artifact_id

    # Audit log
    audit = AuditLog(
        id=str(uuid.uuid4()),
        launch_id=task.launch_id,
        actor="system",
        action="approval_requested",
        resource_type="agent_task",
        resource_id=task.id,
        details={
            "task_type": task.task_type,
            "artifact_id": artifact_id,
            "expires_at": task.approval_expires_at.isoformat(),
        },
    )
    db.add(audit)
    db.commit()

    logger.info("Created approval request for task=%s", task.id)
    return raw_token


def verify_and_approve(
    db: Session,
    task_id: str,
    token: str,
    artifact_id: Optional[str] = None,
) -> AgentTask:
    """Verify the approval token and approve the task.

    Raises ValueError if the token is invalid, expired, already used,
    or if the artifact_id does not match.
    """
    task = db.query(AgentTask).filter_by(id=task_id).first()
    if task is None:
        raise ValueError(f"Task not found: {task_id}")

    if task.approval_status != "pending_approval":
        raise ValueError(f"Task is not pending approval (status={task.approval_status})")

    if task.approval_used_at is not None:
        raise ValueError("Approval token has already been used")

    if task.approval_expires_at and datetime.now(timezone.utc) > task.approval_expires_at:
        raise ValueError("Approval token has expired")

    # Verify token hash
    provided_hash = hashlib.sha256(token.encode()).hexdigest()
    if provided_hash != task.approval_token_hash:
        raise ValueError("Invalid approval token")

    # Verify artifact match if the task has one set
    if task.approval_artifact_id and artifact_id != task.approval_artifact_id:
        raise ValueError(
            f"Artifact mismatch: expected {task.approval_artifact_id}, got {artifact_id}"
        )

    # Approve
    task.approval_status = "approved"
    task.approval_used_at = datetime.now(timezone.utc)

    # If the task was paused waiting for approval, re-queue it so the
    # runner resumes from the step that requested approval.
    was_waiting = task.status == "waiting_for_approval"
    if was_waiting:
        task.status = "queued"
        task.claimed_by = None
        task.claimed_at = None

    # Audit log
    audit = AuditLog(
        id=str(uuid.uuid4()),
        launch_id=task.launch_id,
        actor="founder",
        action="approval_granted",
        resource_type="agent_task",
        resource_id=task.id,
        details={"task_type": task.task_type, "artifact_id": artifact_id},
    )
    db.add(audit)
    db.commit()

    # Re-enqueue to the correct worker queue so the runner picks it up.
    # enqueue_task commits and enqueues as one unit. If Redis fails, the
    # task is marked 'failed' (not stranded in 'queued'). We revert the
    # approval so the founder can retry with the same token.
    if was_waiting:
        from app.services.task_enqueue import enqueue_task
        if not enqueue_task(db, task):
            task.status = "waiting_for_approval"
            task.approval_status = "pending_approval"
            task.approval_used_at = None
            db.commit()
            raise ValueError(
                "Failed to enqueue task after approval (Redis unavailable). "
                "Your approval was not consumed. Please try again."
            )

    logger.info("Approved task=%s", task.id)
    return task


def reject_approval(db: Session, task_id: str) -> AgentTask:
    """Reject a pending approval and cancel the task."""
    task = db.query(AgentTask).filter_by(id=task_id).first()
    if task is None:
        raise ValueError(f"Task not found: {task_id}")

    if task.approval_status != "pending_approval":
        raise ValueError(
            f"Task is not pending approval (approval_status={task.approval_status}). "
            f"Only tasks with approval_status='pending_approval' can be rejected."
        )

    task.approval_status = "rejected"
    task.status = "cancelled"
    task.completed_at = datetime.now(timezone.utc)

    audit = AuditLog(
        id=str(uuid.uuid4()),
        launch_id=task.launch_id,
        actor="founder",
        action="approval_rejected",
        resource_type="agent_task",
        resource_id=task.id,
        details={"task_type": task.task_type},
    )
    db.add(audit)
    db.commit()

    logger.info("Rejected approval for task=%s", task.id)
    return task


def create_grant(
    db: Session,
    launch_id: str,
    task_type: str,
    granted_by: str,
    original_task_id: str,
    channel_or_provider: Optional[str] = None,
) -> ApprovalGrant:
    """Create a standing approval grant so future tasks of this type skip approval."""
    grant = ApprovalGrant(
        id=str(uuid.uuid4()),
        launch_id=launch_id,
        task_type=task_type,
        granted_by=granted_by,
        original_task_id=original_task_id,
        channel_or_provider=channel_or_provider,
    )
    db.add(grant)

    audit = AuditLog(
        id=str(uuid.uuid4()),
        launch_id=launch_id,
        actor="founder",
        action="approval_granted",
        resource_type="approval_grant",
        resource_id=grant.id,
        details={
            "task_type": task_type,
            "channel_or_provider": channel_or_provider,
            "original_task_id": original_task_id,
        },
    )
    db.add(audit)
    db.commit()

    logger.info(
        "Created grant for launch=%s type=%s provider=%s",
        launch_id,
        task_type,
        channel_or_provider,
    )
    return grant


def check_grant(
    db: Session,
    launch_id: str,
    task_type: str,
    channel_or_provider: Optional[str] = None,
) -> Optional[ApprovalGrant]:
    """Check for an active (non-revoked) grant matching the criteria."""
    q = db.query(ApprovalGrant).filter_by(
        launch_id=launch_id,
        task_type=task_type,
    ).filter(ApprovalGrant.revoked_at.is_(None))

    if channel_or_provider:
        q = q.filter(
            (ApprovalGrant.channel_or_provider == channel_or_provider)
            | (ApprovalGrant.channel_or_provider.is_(None))
        )

    grant = q.first()
    if grant:
        logger.debug(
            "Found active grant=%s for launch=%s type=%s",
            grant.id,
            launch_id,
            task_type,
        )
    return grant


def revoke_grant(db: Session, grant_id: str, reason: str) -> ApprovalGrant:
    """Revoke an existing approval grant."""
    grant = db.query(ApprovalGrant).filter_by(id=grant_id).first()
    if grant is None:
        raise ValueError(f"Grant not found: {grant_id}")

    grant.revoked_at = datetime.now(timezone.utc)
    grant.revoke_reason = reason

    audit = AuditLog(
        id=str(uuid.uuid4()),
        launch_id=grant.launch_id,
        actor="founder",
        action="manual_override",
        resource_type="approval_grant",
        resource_id=grant.id,
        details={"reason": reason},
    )
    db.add(audit)
    db.commit()

    logger.info("Revoked grant=%s reason=%s", grant_id, reason)
    return grant
