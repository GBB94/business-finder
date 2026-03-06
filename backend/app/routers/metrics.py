from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.idea import Idea
from app.models.metric_entry import MetricEntry
from app.models.user import User
from app.schemas.metric_entry import (
    MetricEntryCreate,
    MetricEntryResponse,
    MetricEntryListResponse,
    MetricsDashboardResponse,
)
from app.services.metrics_service import VALID_METRIC_KEYS, build_metrics_dashboard
from app.services.idea_service import evaluate_kill_triggers

router = APIRouter(prefix="/api/ideas/{idea_id}/metrics", tags=["metrics"])


def _get_idea_or_404(idea_id: str, user_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=user_id).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.post("", response_model=MetricEntryResponse, status_code=201)
def create_metric(
    idea_id: str,
    body: MetricEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    idea = _get_idea_or_404(idea_id, current_user.id, db)

    if body.metric_key not in VALID_METRIC_KEYS:
        raise HTTPException(
            422,
            f"Unknown metric_key '{body.metric_key}'. "
            f"Valid keys: {sorted(VALID_METRIC_KEYS)}",
        )

    entry = MetricEntry(
        idea_id=idea_id,
        user_id=current_user.id,
        **body.model_dump(),
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            f"A metric entry for '{body.metric_key}' with period_start "
            f"'{body.period_start}' already exists for this idea.",
        )
    db.refresh(entry)

    # Re-evaluate kill triggers so Overview tab stays consistent with Metrics
    idea.kill_triggers = evaluate_kill_triggers(db, idea)
    db.commit()
    db.refresh(idea)

    return MetricEntryResponse.model_validate(entry)


@router.get("", response_model=MetricEntryListResponse)
def list_metrics(
    idea_id: str,
    category: Optional[str] = Query(None),
    metric_key: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    q = db.query(MetricEntry).filter_by(idea_id=idea_id, user_id=current_user.id)
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
def get_dashboard(
    idea_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    idea = _get_idea_or_404(idea_id, current_user.id, db)
    dashboard = build_metrics_dashboard(db, idea)

    for section in ("retention_metrics", "economics_metrics"):
        for metric in dashboard[section]:
            metric["history"] = [
                MetricEntryResponse.model_validate(e) for e in metric["history"]
            ]

    return MetricsDashboardResponse(**dashboard)


@router.delete("/{entry_id}", status_code=204)
def delete_metric(
    idea_id: str,
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    idea = _get_idea_or_404(idea_id, current_user.id, db)

    entry = db.query(MetricEntry).filter_by(
        id=entry_id, idea_id=idea_id, user_id=current_user.id
    ).first()
    if not entry:
        raise HTTPException(404, "Metric entry not found")

    db.delete(entry)
    db.commit()

    # Re-evaluate kill triggers after metric removal
    idea.kill_triggers = evaluate_kill_triggers(db, idea)
    db.commit()
