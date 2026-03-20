from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ApprovalTaskResponse(BaseModel):
    """A pending approval derived from an AgentTask that requires founder action."""
    id: str
    task_id: str
    launch_id: str
    task_type: str
    channel_or_provider: Optional[str] = None
    summary: str
    details: Optional[dict] = None
    artifact_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    approval_token: Optional[str] = None  # Only populated from Redis cache, never from DB
    created_at: datetime


class PendingApprovalListResponse(BaseModel):
    items: list[ApprovalTaskResponse]
    total: int


class ApproveRequest(BaseModel):
    approval_token: str
    artifact_id: Optional[str] = None
    create_grant: bool = False


class ApprovalGrantResponse(BaseModel):
    id: str
    launch_id: str
    task_type: str
    channel_or_provider: Optional[str] = None
    granted_at: datetime
    granted_by: str
    original_task_id: Optional[str] = None
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class ApprovalGrantListResponse(BaseModel):
    items: list[ApprovalGrantResponse]
    total: int
