"""Support thread management endpoints."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.launch_instance import LaunchInstance
from app.models.support_thread import SupportThread
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/launches", tags=["support"])


# ── Schemas ────────────────────────────────────────────────────────────────

class SupportThreadResponse(BaseModel):
    id: str
    launch_id: str
    customer_email: str
    subject: Optional[str] = None
    status: str
    messages: list = []
    confidence_score: Optional[float] = None
    escalated_at: Optional[str] = None
    escalation_reason: Optional[str] = None
    feature_request_extracted: bool = False
    evidence_id: Optional[str] = None
    message_count: int = 0
    created_at: str
    updated_at: Optional[str] = None

    model_config = {"from_attributes": True}


class SupportThreadListResponse(BaseModel):
    items: list[SupportThreadResponse]
    total: int


class ResolveThreadRequest(BaseModel):
    pass


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_launch_or_404(launch_id: str, user_id: str, db: Session) -> LaunchInstance:
    launch = db.query(LaunchInstance).filter_by(id=launch_id, user_id=user_id).first()
    if not launch:
        raise HTTPException(404, "Launch not found")
    return launch


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/{launch_id}/support-threads", response_model=SupportThreadListResponse)
def list_support_threads(
    launch_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_launch_or_404(launch_id, current_user.id, db)

    q = db.query(SupportThread).filter(SupportThread.launch_id == launch_id)
    if status:
        q = q.filter(SupportThread.status == status)
    total = q.count()
    threads = q.order_by(SupportThread.updated_at.desc().nullslast(), SupportThread.created_at.desc()).offset(offset).limit(limit).all()
    return SupportThreadListResponse(
        items=[SupportThreadResponse.model_validate(t) for t in threads],
        total=total,
    )


@router.get("/{launch_id}/support-threads/{thread_id}", response_model=SupportThreadResponse)
def get_support_thread(
    launch_id: str,
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_launch_or_404(launch_id, current_user.id, db)

    thread = db.query(SupportThread).filter_by(id=thread_id, launch_id=launch_id).first()
    if not thread:
        raise HTTPException(404, "Support thread not found")
    return SupportThreadResponse.model_validate(thread)


@router.post("/{launch_id}/support-threads/{thread_id}/resolve", response_model=SupportThreadResponse)
def resolve_thread(
    launch_id: str,
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_launch_or_404(launch_id, current_user.id, db)

    thread = db.query(SupportThread).filter_by(id=thread_id, launch_id=launch_id).first()
    if not thread:
        raise HTTPException(404, "Support thread not found")
    if thread.status == "resolved":
        raise HTTPException(400, "Thread is already resolved")

    thread.status = "resolved"
    db.commit()
    db.refresh(thread)
    return SupportThreadResponse.model_validate(thread)
