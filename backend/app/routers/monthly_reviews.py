from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.idea import Idea
from app.models.evidence import Evidence
from app.models.monthly_review import MonthlyReview
from app.models.score import Score
from app.models.config import SCORING_DIMENSIONS
from app.models.user import User
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


def _get_idea_or_404(idea_id: str, user_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=user_id).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.post("", response_model=MonthlyReviewResponse, status_code=201)
def create_review(
    idea_id: str,
    body: MonthlyReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    idea = _get_idea_or_404(idea_id, current_user.id, db)

    metrics_snapshot = body.metrics_snapshot
    if metrics_snapshot is None:
        metrics_snapshot = build_metrics_snapshot(db, idea)

    current_triggers = evaluate_kill_triggers(db, idea)
    fired_labels = [
        t["label"] for t in current_triggers.values()
        if t.get("fired") or t.get("state") == "red"
    ]

    # Build confidence snapshot from current score if not provided
    confidence_snapshot = body.score_confidence_snapshot
    if confidence_snapshot is None:
        score = (
            db.query(Score)
            .filter_by(idea_id=idea_id, user_id=current_user.id)
            .order_by(Score.scored_at.desc())
            .first()
        )
        if score:
            confidence_snapshot = {
                dim: getattr(score, f"{dim}_confidence", "low")
                for dim in SCORING_DIMENSIONS
            }

    review = MonthlyReview(
        idea_id=idea_id,
        user_id=current_user.id,
        review_date=body.review_date,
        review_type=body.review_type,
        score_confidence_snapshot=confidence_snapshot,
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

    if body.decision in ("kill", "park"):
        target = "killed" if body.decision == "kill" else "parked"
        try:
            transition_status(db, idea, target)
        except ValueError:
            pass
    elif body.decision == "graduate_to_standard":
        idea.validation_mode = "standard"
        from app.services.idea_service import seed_kill_triggers, DEFAULT_KILL_TRIGGERS
        idea.kill_triggers = DEFAULT_KILL_TRIGGERS.copy()
        db.add(idea)
        db.commit()

    return MonthlyReviewResponse.model_validate(review)


@router.get("", response_model=MonthlyReviewListResponse)
def list_reviews(
    idea_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    reviews = (
        db.query(MonthlyReview)
        .filter_by(idea_id=idea_id, user_id=current_user.id)
        .order_by(MonthlyReview.review_date.desc())
        .all()
    )
    return MonthlyReviewListResponse(
        items=[MonthlyReviewResponse.model_validate(r) for r in reviews],
        total=len(reviews),
    )


@router.post("/generate-summary", response_model=ReviewSummaryResponse)
def generate_summary(
    idea_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    idea = _get_idea_or_404(idea_id, current_user.id, db)

    score = (
        db.query(Score)
        .filter_by(idea_id=idea_id, user_id=current_user.id)
        .order_by(Score.scored_at.desc())
        .first()
    )
    scores_summary = None
    if score:
        weights = get_weights_map(db, current_user.id)
        dims = {}
        for dim in SCORING_DIMENSIONS:
            val = getattr(score, f"{dim}_score", None)
            if val is not None:
                dims[dim] = {"score": val, "weight": weights.get(dim, 0)}
        scores_summary = {
            "weighted_total": score.weighted_total,
            "dimensions": dims,
        }

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

    current_triggers = evaluate_kill_triggers(db, idea)
    trigger_states = []
    for key, t in current_triggers.items():
        trigger_states.append({
            "key": key,
            "label": t.get("label", key),
            "state": t.get("state", "green"),
            "fired": t.get("fired", False),
        })

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    evidence_rows = (
        db.query(Evidence)
        .filter_by(idea_id=idea_id, user_id=current_user.id, content_purged=False)
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

    prev_reviews = (
        db.query(MonthlyReview)
        .filter_by(idea_id=idea_id, user_id=current_user.id)
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

    from app.services.agent_task_service import get_model_for_task
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
                model=get_model_for_task("review_summary"),
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
        prompt_used=result.prompt_used,
    )
