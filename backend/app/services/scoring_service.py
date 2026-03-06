from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.config import ScoringWeight, SCORING_DIMENSIONS
from app.models.founder_profile import FounderProfile
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


AUTO_COMPUTED_DIMENSIONS = {"founder_constraints"}


def update_score_dimensions(
    db: Session,
    score: Score,
    dimensions: list[dict],
    weights: dict[str, float],
) -> Score:
    for d in dimensions:
        dim = d["dimension"]
        if dim not in SCORING_DIMENSIONS or dim in AUTO_COMPUTED_DIMENSIONS:
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


# ── Auto-computed founder constraints ────────────────────────────

_RUNWAY_TIERS = [(12, 5), (9, 4), (6, 3), (3, 2)]
_HOURS_TIERS = [(25, 5), (20, 4), (15, 3), (10, 2)]


def _tier(value: float, thresholds: list[tuple[int, int]]) -> int:
    for threshold, tier in thresholds:
        if value >= threshold:
            return tier
    return 1


def compute_founder_constraints(profile: FounderProfile) -> tuple[int, str]:
    if profile.monthly_burn_rate and profile.monthly_burn_rate > 0:
        runway = round(profile.current_savings / profile.monthly_burn_rate, 1)
    else:
        runway = 99.0  # no burn = infinite runway

    total_hours = (
        profile.available_hours_per_week_building
        + profile.available_hours_per_week_selling
    )

    r_tier = _tier(runway, _RUNWAY_TIERS)
    h_tier = _tier(total_hours, _HOURS_TIERS)
    score = min(r_tier, h_tier)

    note = f"Auto: {runway}mo runway (tier {r_tier}), {total_hours} hrs/wk (tier {h_tier}) → score {score}"
    return score, note


def apply_auto_constraints(db: Session, score: Score, *, commit: bool = True) -> Score:
    """Compute and set founder_constraints from the founder profile.

    If no profile exists, the dimension is nulled with an explanatory note
    so that manual values can never masquerade as auto-computed.

    When *commit* is False the caller is responsible for committing.
    """
    from app.models.idea import Idea

    idea = db.query(Idea).filter_by(id=score.idea_id).first()
    if not idea:
        return score

    profile = (
        db.query(FounderProfile)
        .filter_by(user_id=idea.user_id)
        .first()
    )

    if profile:
        val, note = compute_founder_constraints(profile)
        score.founder_constraints_score = val
        score.founder_constraints_note = note
    else:
        score.founder_constraints_score = None
        score.founder_constraints_note = "No founder profile — set up your profile to auto-compute."

    weights = get_weights_map(db, idea.user_id)
    score.weighted_total = compute_weighted_total(score, weights)

    db.add(score)
    if commit:
        db.commit()
        db.refresh(score)
    return score
