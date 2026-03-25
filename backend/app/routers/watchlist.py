from __future__ import annotations

import logging

import redis
from fastapi import APIRouter, Depends, HTTPException
from rq import Queue
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.watchlist_entry import WatchlistEntry
from app.schemas.watchlist import (
    WatchlistEntryCreate,
    WatchlistEntryUpdate,
    WatchlistEntryResponse,
    WatchlistEntryListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=WatchlistEntryListResponse)
def list_entries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entries = (
        db.query(WatchlistEntry)
        .filter_by(user_id=current_user.id)
        .order_by(WatchlistEntry.created_at.desc())
        .all()
    )
    return WatchlistEntryListResponse(
        items=[WatchlistEntryResponse.model_validate(e) for e in entries],
        total=len(entries),
    )


@router.post("", response_model=WatchlistEntryResponse, status_code=201)
def create_entry(
    body: WatchlistEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = WatchlistEntry(
        user_id=current_user.id,
        source_type=body.source_type,
        source_name=body.source_name,
        description=body.description,
        scan_frequency_days=body.scan_frequency_days,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return WatchlistEntryResponse.model_validate(entry)


@router.patch("/{entry_id}", response_model=WatchlistEntryResponse)
def update_entry(
    entry_id: str,
    body: WatchlistEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = (
        db.query(WatchlistEntry)
        .filter_by(id=entry_id, user_id=current_user.id)
        .first()
    )
    if not entry:
        raise HTTPException(404, "Watchlist entry not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return WatchlistEntryResponse.model_validate(entry)


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = (
        db.query(WatchlistEntry)
        .filter_by(id=entry_id, user_id=current_user.id)
        .first()
    )
    if not entry:
        raise HTTPException(404, "Watchlist entry not found")
    db.delete(entry)
    db.commit()


@router.post("/{entry_id}/scan", status_code=202)
def trigger_scan(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger an immediate discovery scan for this watchlist entry."""
    entry = (
        db.query(WatchlistEntry)
        .filter_by(id=entry_id, user_id=current_user.id)
        .first()
    )
    if not entry:
        raise HTTPException(404, "Watchlist entry not found")

    try:
        conn = redis.from_url(settings.REDIS_URL)
        q = Queue("discovery", connection=conn)
        q.enqueue(
            "app.jobs.discovery_scan.run_discovery_scan_for_user",
            current_user.id,
        )
    except Exception:
        logger.exception("Failed to enqueue discovery scan")
        raise HTTPException(503, "Failed to enqueue scan job")

    return {"status": "queued", "entry_id": entry_id}
