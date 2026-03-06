from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.idea import Idea
from app.models.score import Score
from app.models.evidence import Evidence
from app.models.config import SCORING_DIMENSIONS
from app.schemas.score import (
    ScoreCreate,
    ScoreUpdate,
    ScoreResponse,
    DimensionScoreResponse,
    SynthesizeRequest,
    SynthesisResponse,
    ConsistencyCheckRequest,
    InconsistencyItem,
    ConsistencyResponse,
)
from app.services.scoring_service import get_weights_map, update_score_dimensions, apply_auto_constraints
from app.services.synthesis_service import (
    synthesize_evidence_for_dimension,
    check_score_consistency,
    ConfigurationError,
)

logger = logging.getLogger(__name__)

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
                dimension=dim, score=val, note=note, weight=w, weighted_contribution=contrib,
                auto_computed=(dim == "founder_constraints"),
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
    score = apply_auto_constraints(db, score)
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
    score = apply_auto_constraints(db, score)
    return _build_response(score, weights)


DIMENSION_LABELS = {
    "problem_severity": "Problem Severity",
    "market_evidence": "Market Evidence",
    "revenue_model": "Revenue Model",
    "distribution_feasibility": "Distribution Feasibility",
    "purchaser_quality": "Purchaser Quality",
    "build_complexity": "Build Complexity",
    "founder_market_fit": "Founder-Market Fit",
    "time_to_revenue": "Time to Revenue",
    "founder_constraints": "Founder Constraints",
    "competition_level": "Competition Level",
    "defensibility_potential": "Defensibility Potential",
}


@router.post("/synthesize", response_model=SynthesisResponse)
def synthesize(idea_id: str, body: SynthesizeRequest, db: Session = Depends(get_db)):
    if body.dimension not in SCORING_DIMENSIONS:
        raise HTTPException(400, f"Unknown dimension: {body.dimension}")

    idea = _get_idea_or_404(idea_id, db)

    # Load current score + note for this dimension
    score = (
        db.query(Score)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID)
        .order_by(Score.scored_at.desc())
        .first()
    )
    current_score = getattr(score, f"{body.dimension}_score", None) if score else None
    current_note = getattr(score, f"{body.dimension}_note", None) if score else None

    # Load non-purged evidence
    evidence_rows = (
        db.query(Evidence)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID, content_purged=False)
        .order_by(Evidence.created_at.desc())
        .all()
    )

    evidence_items = [
        {
            "id": ev.id,
            "title": ev.title,
            "evidence_type": ev.evidence_type.value if hasattr(ev.evidence_type, "value") else ev.evidence_type,
            "content": ev.content,
            "source_type": ev.source_type.value if hasattr(ev.source_type, "value") else ev.source_type,
            "sentiment": ev.sentiment.value if hasattr(ev.sentiment, "value") else ev.sentiment,
            "tags": ev.tags,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        }
        for ev in evidence_rows
    ]

    try:
        result = asyncio.run(
            synthesize_evidence_for_dimension(
                idea_name=idea.name,
                idea_audience=idea.audience,
                idea_problem=idea.problem_statement,
                idea_solution=idea.proposed_solution,
                dimension=body.dimension,
                dimension_label=DIMENSION_LABELS.get(body.dimension, body.dimension),
                current_score=current_score,
                current_note=current_note,
                evidence_items=evidence_items,
            )
        )
    except ConfigurationError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        logger.exception("Synthesis failed for idea=%s dimension=%s", idea_id, body.dimension)
        raise HTTPException(502, "AI synthesis failed. Please try again.")

    return SynthesisResponse(
        dimension=body.dimension,
        summary=result.summary,
        key_findings=result.key_findings,
        evidence_cited=result.evidence_cited,
        gaps=result.gaps,
        model_version=result.model_version,
    )


@router.post("/check-consistency", response_model=ConsistencyResponse)
def check_consistency(idea_id: str, body: ConsistencyCheckRequest, db: Session = Depends(get_db)):
    idea = _get_idea_or_404(idea_id, db)

    weights = get_weights_map(db)

    # Use the draft scores sent from the UI
    scores_list = [
        {
            "dimension": d.dimension,
            "score": d.score,
            "note": d.note,
            "weight": weights.get(d.dimension, 0.0),
        }
        for d in body.dimensions
    ]

    if not scores_list:
        raise HTTPException(400, "No scored dimensions provided.")

    # Load non-purged evidence
    evidence_rows = (
        db.query(Evidence)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID, content_purged=False)
        .order_by(Evidence.created_at.desc())
        .all()
    )

    evidence_items = [
        {
            "id": ev.id,
            "title": ev.title,
            "evidence_type": ev.evidence_type.value if hasattr(ev.evidence_type, "value") else ev.evidence_type,
            "content": ev.content,
            "source_type": ev.source_type.value if hasattr(ev.source_type, "value") else ev.source_type,
            "sentiment": ev.sentiment.value if hasattr(ev.sentiment, "value") else ev.sentiment,
            "tags": ev.tags,
        }
        for ev in evidence_rows
    ]

    try:
        result = asyncio.run(
            check_score_consistency(
                idea_name=idea.name,
                idea_audience=idea.audience,
                idea_problem=idea.problem_statement,
                idea_solution=idea.proposed_solution,
                scores=scores_list,
                evidence_items=evidence_items,
            )
        )
    except ConfigurationError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        logger.exception("Consistency check failed for idea=%s", idea_id)
        raise HTTPException(502, "AI consistency check failed. Please try again.")

    return ConsistencyResponse(
        inconsistencies=[
            InconsistencyItem(**inc) for inc in result.inconsistencies
        ],
        overall_assessment=result.overall_assessment,
        model_version=result.model_version,
    )
