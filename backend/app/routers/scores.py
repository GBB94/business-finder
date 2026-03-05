from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.idea import Idea
from app.models.score import Score
from app.models.config import SCORING_DIMENSIONS
from app.schemas.score import (
    ScoreCreate,
    ScoreUpdate,
    ScoreResponse,
    DimensionScoreResponse,
)
from app.services.scoring_service import get_weights_map, update_score_dimensions

router = APIRouter(prefix="/api/ideas/{idea_id}/scores", tags=["scores"])


def _build_response(score: Score, weights: dict[str, float]) -> ScoreResponse:
    dims = []
    for dim in SCORING_DIMENSIONS:
        val = getattr(score, f"{dim}_score", None)
        note = getattr(score, f"{dim}_note", None)
        w = weights.get(dim, 0.0)
        contrib = round((val / 5.0) * w, 2) if val is not None else None
        dims.append(
            DimensionScoreResponse(
                dimension=dim, score=val, note=note, weight=w, weighted_contribution=contrib
            )
        )
    resp = ScoreResponse.model_validate(score)
    resp.dimensions = dims
    return resp


def _get_idea_or_404(idea_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=settings.DEFAULT_USER_ID).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.get("", response_model=Optional[ScoreResponse])
def get_score(idea_id: str, db: Session = Depends(get_db)):
    _get_idea_or_404(idea_id, db)
    score = (
        db.query(Score)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID)
        .order_by(Score.scored_at.desc())
        .first()
    )
    if not score:
        return None
    weights = get_weights_map(db)
    return _build_response(score, weights)


@router.post("", response_model=ScoreResponse, status_code=201)
def create_score(idea_id: str, body: ScoreCreate, db: Session = Depends(get_db)):
    _get_idea_or_404(idea_id, db)
    # One score per idea per user — replace if exists
    existing = (
        db.query(Score)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID)
        .first()
    )
    if existing:
        db.delete(existing)
        db.flush()

    score = Score(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID)
    db.add(score)
    db.flush()

    weights = get_weights_map(db)
    score = update_score_dimensions(
        db, score, [d.model_dump() for d in body.dimensions], weights
    )
    return _build_response(score, weights)


@router.patch("", response_model=ScoreResponse)
def patch_score(idea_id: str, body: ScoreUpdate, db: Session = Depends(get_db)):
    _get_idea_or_404(idea_id, db)
    score = (
        db.query(Score)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID)
        .first()
    )
    if not score:
        raise HTTPException(404, "No score exists for this idea. POST first.")

    weights = get_weights_map(db)
    score = update_score_dimensions(
        db, score, [d.model_dump() for d in body.dimensions], weights
    )
    return _build_response(score, weights)
