from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.config import ScoringWeight
from app.schemas.scoring_weight import (
    WeightsUpdateRequest,
    WeightResponse,
    WeightsResponse,
)

router = APIRouter(prefix="/api/scoring-weights", tags=["scoring-weights"])


def _build_response(db: Session) -> WeightsResponse:
    rows = (
        db.query(ScoringWeight)
        .filter_by(user_id=settings.DEFAULT_USER_ID)
        .all()
    )
    weights = [WeightResponse(dimension=r.dimension, weight=r.weight) for r in rows]
    total = sum(w.weight for w in weights)
    return WeightsResponse(weights=weights, total_weight=round(total, 2))


@router.get("", response_model=WeightsResponse)
def get_weights(db: Session = Depends(get_db)):
    return _build_response(db)


@router.put("", response_model=WeightsResponse)
def update_weights(body: WeightsUpdateRequest, db: Session = Depends(get_db)):
    for wu in body.weights:
        row = (
            db.query(ScoringWeight)
            .filter_by(user_id=settings.DEFAULT_USER_ID, dimension=wu.dimension)
            .first()
        )
        if not row:
            raise HTTPException(404, f"Dimension '{wu.dimension}' not found")
        row.weight = wu.weight
    db.commit()
    return _build_response(db)
