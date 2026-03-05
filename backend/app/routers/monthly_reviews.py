from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.idea import Idea
from app.models.monthly_review import MonthlyReview
from app.schemas.monthly_review import (
    MonthlyReviewCreate,
    MonthlyReviewResponse,
    MonthlyReviewListResponse,
)
from app.services.idea_service import transition_status

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

    review = MonthlyReview(
        idea_id=idea_id,
        user_id=settings.DEFAULT_USER_ID,
        review_date=body.review_date,
        metrics_snapshot=body.metrics_snapshot,
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
