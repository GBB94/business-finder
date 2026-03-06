from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.founder_profile import FounderProfile
from app.models.idea import Idea, IdeaStatus
from app.models.score import Score
from app.models.user import User
from app.schemas.founder_profile import (
    FounderProfileUpsert,
    FounderProfileResponse,
)
from app.services.scoring_service import apply_auto_constraints

router = APIRouter(prefix="/api/profile", tags=["founder-profile"])


def _compute_runway(profile: FounderProfile) -> Optional[float]:
    if profile.monthly_burn_rate and profile.monthly_burn_rate > 0:
        return round(profile.current_savings / profile.monthly_burn_rate, 1)
    return None


def _respond(profile: FounderProfile) -> FounderProfileResponse:
    resp = FounderProfileResponse.model_validate(profile)
    resp.runway_months_remaining = _compute_runway(profile)
    return resp


@router.get("", response_model=FounderProfileResponse)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = (
        db.query(FounderProfile)
        .filter_by(user_id=current_user.id)
        .first()
    )
    if not profile:
        profile = FounderProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return _respond(profile)


@router.put("", response_model=FounderProfileResponse)
def upsert_profile(
    body: FounderProfileUpsert,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile = (
        db.query(FounderProfile)
        .filter_by(user_id=current_user.id)
        .first()
    )
    if not profile:
        profile = FounderProfile(user_id=current_user.id)
        db.add(profile)

    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(profile, k, v)

    db.commit()
    db.refresh(profile)

    active_statuses = [s for s in IdeaStatus if s not in (IdeaStatus.killed, IdeaStatus.parked)]
    ideas = (
        db.query(Idea)
        .filter(Idea.user_id == current_user.id, Idea.status.in_(active_statuses))
        .all()
    )
    for idea in ideas:
        score = (
            db.query(Score)
            .filter_by(idea_id=idea.id, user_id=current_user.id)
            .first()
        )
        if score:
            apply_auto_constraints(db, score, commit=False)

    db.commit()
    return _respond(profile)
