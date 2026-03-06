from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.idea import Idea
from app.models.evidence import Evidence
from app.models.monthly_review import MonthlyReview
from app.models.score import Score
from app.models.config import SCORING_DIMENSIONS
from app.schemas.monthly_review import (
    MonthlyReviewCreate,
    MonthlyReviewResponse,
    MonthlyReviewListResponse,
    ReviewSummaryResponse,
)
from app.services.idea_service import transition_status, evaluate_kill_triggers
from app.services.metrics_service import build_metrics_snapshot, build_metrics_dashboard
from app.services.scoring_service import get_weights_map
from app.services.synthesis_service import generate_review_summary, ConfigurationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ideas/{idea_id}/reviews", tags=["monthly-reviews"])


def _get_idea_or_404(idea_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=settings.DEFAULT_USER_ID).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.post("", response_model=MonthlyReviewResponse, status_code=201)
def create_review(
    idea_id: str, body: MonthlyReviewCreate, db: Session = Depends(get_db)
):
    idea = _get_idea_or_404(idea_id, db)

    # Auto-populate metrics snapshot if not provided
    metrics_snapshot = body.metrics_snapshot
    if metrics_snapshot is None:
        metrics_snapshot = build_metrics_snapshot(db, idea)

    # Auto-populate kill triggers fired
    current_triggers = evaluate_kill_triggers(db, idea)
    fired_labels = [
        t["label"] for t in current_triggers.values()
        if t.get("fired") or t.get("state") == "red"
    ]

    review = MonthlyReview(
        idea_id=idea_id,
        user_id=settings.DEFAULT_USER_ID,
        review_date=body.review_date,
        metrics_snapshot=metrics_snapshot,
        kill_triggers_fired=fired_labels if fired_labels else None,
        decision=body.decision,
        reasoning=body.reasoning,
        next_hypothesis=body.next_hypothesis,
        gate_1_status_at_review=idea.gate_1_status if isinstance(idea.gate_1_status, str) else idea.gate_1_status.value,
        gate_2_status_at_review=idea.gate_2_status if isinstance(idea.gate_2_status, str) else idea.gate_2_status.value,
        gate_3_status_at_review=idea.gate_3_status if isinstance(idea.gate_3_status, str) else idea.gate_3_status.value,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    # If decision is kill or park, also transition the idea
    if body.decision in ("kill", "park"):
        target = "killed" if body.decision == "kill" else "parked"
        try:
            transition_status(db, idea, target)
        except ValueError:
            pass  # already in that state

    return MonthlyReviewResponse.model_validate(review)


@router.get("", response_model=MonthlyReviewListResponse)
def list_reviews(idea_id: str, db: Session = Depends(get_db)):
    _get_idea_or_404(idea_id, db)

    reviews = (
        db.query(MonthlyReview)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID)
        .order_by(MonthlyReview.review_date.desc())
        .all()
    )
    return MonthlyReviewListResponse(
        items=[MonthlyReviewResponse.model_validate(r) for r in reviews],
        total=len(reviews),
    )


@router.post("/generate-summary", response_model=ReviewSummaryResponse)
def generate_summary(idea_id: str, db: Session = Depends(get_db)):
    idea = _get_idea_or_404(idea_id, db)

    # Load current score
    score = (
        db.query(Score)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID)
        .order_by(Score.scored_at.desc())
        .first()
    )
    scores_summary = None
    if score:
        weights = get_weights_map(db)
        dims = {}
        for dim in SCORING_DIMENSIONS:
            val = getattr(score, f"{dim}_score", None)
            if val is not None:
                dims[dim] = {"score": val, "weight": weights.get(dim, 0)}
        scores_summary = {
            "weighted_total": score.weighted_total,
            "dimensions": dims,
        }

    # Load metrics dashboard and serialize ORM objects in history arrays
    raw_dashboard = build_metrics_dashboard(db, idea)
    for metric_list in (raw_dashboard.get("retention_metrics", []),
                        raw_dashboard.get("economics_metrics", [])):
        for m in metric_list:
            m["history"] = [
                {
                    "value": e.value,
                    "period_start": e.period_start.isoformat() if e.period_start else None,
                    "period_end": e.period_end.isoformat() if e.period_end else None,
                    "sample_size": e.sample_size,
                    "note": e.note,
                }
                for e in m.get("history", [])
            ]
    metrics_summary = raw_dashboard

    # Evaluate kill triggers
    current_triggers = evaluate_kill_triggers(db, idea)
    trigger_states = []
    for key, t in current_triggers.items():
        trigger_states.append({
            "key": key,
            "label": t.get("label", key),
            "state": t.get("state", "green"),
            "fired": t.get("fired", False),
        })

    # Load recent evidence (last 30 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    evidence_rows = (
        db.query(Evidence)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID, content_purged=False)
        .filter(Evidence.created_at >= cutoff)
        .order_by(Evidence.created_at.desc())
        .all()
    )
    recent_evidence = [
        {
            "id": ev.id,
            "title": ev.title,
            "evidence_type": ev.evidence_type.value if hasattr(ev.evidence_type, "value") else ev.evidence_type,
            "content": ev.content,
            "sentiment": ev.sentiment.value if hasattr(ev.sentiment, "value") else ev.sentiment,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        }
        for ev in evidence_rows
    ]

    # Load previous reviews
    prev_reviews = (
        db.query(MonthlyReview)
        .filter_by(idea_id=idea_id, user_id=settings.DEFAULT_USER_ID)
        .order_by(MonthlyReview.review_date.desc())
        .limit(5)
        .all()
    )
    previous_reviews = [
        {
            "review_date": str(r.review_date),
            "decision": r.decision,
            "reasoning": r.reasoning,
        }
        for r in prev_reviews
    ]

    idea_status = idea.status if isinstance(idea.status, str) else idea.status.value

    try:
        result = asyncio.run(
            generate_review_summary(
                idea_name=idea.name,
                idea_audience=idea.audience,
                idea_problem=idea.problem_statement,
                idea_solution=idea.proposed_solution,
                idea_status=idea_status,
                scores_summary=scores_summary,
                metrics_summary=metrics_summary,
                trigger_states=trigger_states,
                recent_evidence=recent_evidence,
                previous_reviews=previous_reviews,
            )
        )
    except ConfigurationError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        logger.exception("Review summary generation failed for idea=%s", idea_id)
        raise HTTPException(502, "AI summary generation failed. Please try again.")

    return ReviewSummaryResponse(
        summary=result.summary,
        metrics_assessment=result.metrics_assessment,
        trigger_status=result.trigger_status,
        key_developments=result.key_developments,
        open_questions=result.open_questions,
        model_version=result.model_version,
    )
