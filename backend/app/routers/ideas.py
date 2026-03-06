from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.idea import Idea
from app.models.score import Score
from app.schemas.idea import (
    IdeaCreate,
    IdeaUpdate,
    IdeaStatusTransition,
    IdeaResponse,
    IdeaListResponse,
)
from app.services.idea_service import (
    transition_status,
    seed_kill_triggers,
    compute_days_in_stage,
    evaluate_kill_triggers,
    archive_idea,
    unarchive_idea,
)

router = APIRouter(prefix="/api/ideas", tags=["ideas"])


def _enrich(idea: Idea, db: Session) -> IdeaResponse:
    latest_score = None
    if idea.scores:
        latest_score = max(idea.scores, key=lambda s: s.scored_at)
    wt = latest_score.weighted_total if latest_score else None
    days = compute_days_in_stage(idea)

    resp = IdeaResponse.model_validate(idea)
    resp.weighted_total = wt
    resp.days_in_stage = days
    return resp


def _refresh_triggers(idea: Idea, db: Session) -> None:
    """Evaluate and persist kill trigger updates. Call only on mutations."""
    if not idea.kill_triggers:
        return
    updated_triggers = evaluate_kill_triggers(db, idea)
    if updated_triggers != idea.kill_triggers:
        idea.kill_triggers = updated_triggers
        db.add(idea)
        db.commit()
        db.refresh(idea)


@router.post("", response_model=IdeaResponse, status_code=201)
def create_idea(body: IdeaCreate, db: Session = Depends(get_db)):
    idea = Idea(
        user_id=settings.DEFAULT_USER_ID,
        **body.model_dump(),
    )
    seed_kill_triggers(idea)
    db.add(idea)
    db.commit()
    db.refresh(idea)
    _refresh_triggers(idea, db)
    return _enrich(idea, db)


@router.get("", response_model=IdeaListResponse)
def list_ideas(
    status: Optional[str] = Query(None),
    archived: bool = Query(False),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    db: Session = Depends(get_db),
):
    q = db.query(Idea).filter(Idea.user_id == settings.DEFAULT_USER_ID)
    if status:
        q = q.filter(Idea.status == status)
    if not archived:
        q = q.filter(Idea.archived_at.is_(None))
    else:
        q = q.filter(Idea.archived_at.isnot(None))

    col = getattr(Idea, sort_by, Idea.created_at)
    q = q.order_by(col.desc() if sort_dir == "desc" else col.asc())

    ideas = q.all()
    return IdeaListResponse(
        items=[_enrich(i, db) for i in ideas],
        total=len(ideas),
    )


def _get_idea_or_404(idea_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=settings.DEFAULT_USER_ID).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.get("/{idea_id}", response_model=IdeaResponse)
def get_idea(idea_id: str, db: Session = Depends(get_db)):
    return _enrich(_get_idea_or_404(idea_id, db), db)


@router.put("/{idea_id}", response_model=IdeaResponse)
def update_idea(idea_id: str, body: IdeaUpdate, db: Session = Depends(get_db)):
    idea = _get_idea_or_404(idea_id, db)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(idea, k, v)
    db.add(idea)
    db.commit()
    db.refresh(idea)
    _refresh_triggers(idea, db)
    return _enrich(idea, db)


@router.post("/{idea_id}/transition", response_model=IdeaResponse)
def transition_idea(
    idea_id: str, body: IdeaStatusTransition, db: Session = Depends(get_db)
):
    idea = _get_idea_or_404(idea_id, db)
    try:
        idea = transition_status(db, idea, body.new_status)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _refresh_triggers(idea, db)
    return _enrich(idea, db)


@router.post("/{idea_id}/archive", response_model=IdeaResponse)
def archive(idea_id: str, db: Session = Depends(get_db)):
    idea = _get_idea_or_404(idea_id, db)
    idea = archive_idea(db, idea)
    return _enrich(idea, db)


@router.post("/{idea_id}/unarchive", response_model=IdeaResponse)
def unarchive(idea_id: str, db: Session = Depends(get_db)):
    idea = _get_idea_or_404(idea_id, db)
    idea = unarchive_idea(db, idea)
    return _enrich(idea, db)
