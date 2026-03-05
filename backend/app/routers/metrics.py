from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.idea import Idea
from app.models.metric_entry import MetricEntry
from app.schemas.metric_entry import (
    MetricEntryCreate,
    MetricEntryResponse,
    MetricEntryListResponse,
    MetricsDashboardResponse,
)
from app.services.metrics_service import VALID_METRIC_KEYS, build_metrics_dashboard

router = APIRouter(prefix="/api/ideas/{idea_id}/metrics", tags=["metrics"])


def _get_idea_or_404(idea_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=settings.DEFAULT_USER_ID).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.post("", response_model=MetricEntryResponse, status_code=201)
def create_metric(idea_id: str, body: MetricEntryCreate, db: Session = Depends(get_db)):
    _get_idea_or_404(idea_id, db)

    if body.metric_key not in VALID_METRIC_KEYS:
        raise HTTPException(
            422,
            f"Unknown metric_key '{body.metric_key}'. "
            f"Valid keys: {sorted(VALID_METRIC_KEYS)}",
        )

    entry = MetricEntry(
        idea_id=idea_id,
        user_id=settings.DEFAULT_USER_ID,
        **body.model_dump(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return MetricEntryResponse.model_validate(entry)


@router.get("", response_model=MetricEntryListResponse)
def list_metrics(
    idea_id: str,
    category: Optional[str] = Query(None),
    metric_key: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    _get_idea_or_404(idea_id, db)

    q = db.query(MetricEntry).filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID)
    if category:
        q = q.filter(MetricEntry.category == category)
    if metric_key:
        q = q.filter(MetricEntry.metric_key == metric_key)

    items = q.order_by(MetricEntry.period_end.desc()).all()
    return MetricEntryListResponse(
        items=[MetricEntryResponse.model_validate(e) for e in items],
        total=len(items),
    )


@router.get("/dashboard", response_model=MetricsDashboardResponse)
def get_dashboard(idea_id: str, db: Session = Depends(get_db)):
    idea = _get_idea_or_404(idea_id, db)
    dashboard = build_metrics_dashboard(db, idea)

    # Serialize MetricEntry objects in history lists
    for section in ("retention_metrics", "economics_metrics"):
        for metric in dashboard[section]:
            metric["history"] = [
                MetricEntryResponse.model_validate(e) for e in metric["history"]
            ]

    return MetricsDashboardResponse(**dashboard)


@router.delete("/{entry_id}", status_code=204)
def delete_metric(idea_id: str, entry_id: str, db: Session = Depends(get_db)):
    _get_idea_or_404(idea_id, db)

    entry = db.query(MetricEntry).filter_by(
        id=entry_id, idea_id=idea_id, user_id=settings.DEFAULT_USER_ID
    ).first()
    if not entry:
        raise HTTPException(404, "Metric entry not found")

    db.delete(entry)
    db.commit()
