from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.config import ScoringWeight, SCORING_DIMENSIONS
from app.models.score import Score
from app.config import settings

DISQUALIFIER_DIMENSIONS = [
    "problem_severity",
    "revenue_model",
    "distribution_feasibility",
]


def get_weights_map(db: Session, user_id: Optional[str] = None) -> dict[str, float]:
    uid = user_id or settings.DEFAULT_USER_ID
    rows = db.query(ScoringWeight).filter_by(user_id=uid).all()
    return {r.dimension: r.weight for r in rows}


def compute_weighted_total(score: Score, weights: dict[str, float]) -> float:
    total = 0.0
    for dim in SCORING_DIMENSIONS:
        val = getattr(score, f"{dim}_score", None)
        w = weights.get(dim, 0.0)
        if val is not None and w > 0:
            total += (val / 5.0) * w
    return round(total, 2)


def check_disqualifiers(score: Score) -> list[str]:
    fired = []
    for dim in DISQUALIFIER_DIMENSIONS:
        val = getattr(score, f"{dim}_score", None)
        if val is not None and val <= 2:
            fired.append(dim)
    return fired


def update_score_dimensions(
    db: Session,
    score: Score,
    dimensions: list[dict],
    weights: dict[str, float],
) -> Score:
    for d in dimensions:
        dim = d["dimension"]
        if dim not in SCORING_DIMENSIONS:
            continue
        setattr(score, f"{dim}_score", d["score"])
        if "note" in d and d["note"] is not None:
            setattr(score, f"{dim}_note", d["note"])

    score.weighted_total = compute_weighted_total(score, weights)
    score.disqualifiers_checked = check_disqualifiers(score)

    db.add(score)
    db.commit()
    db.refresh(score)
    return score
