from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.idea import Idea
from app.models.evidence import Evidence
from app.models.user import User
from app.schemas.evidence import (
    EvidenceCreate,
    EvidenceResponse,
    EvidenceListResponse,
)

router = APIRouter(prefix="/api/ideas/{idea_id}/evidence", tags=["evidence"])


def _get_idea_or_404(idea_id: str, user_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=user_id).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.post("", response_model=EvidenceResponse, status_code=201)
def add_evidence(
    idea_id: str,
    body: EvidenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    ev = Evidence(
        idea_id=idea_id,
        user_id=current_user.id,
        **body.model_dump(),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return EvidenceResponse.model_validate(ev)


@router.get("", response_model=EvidenceListResponse)
def list_evidence(
    idea_id: str,
    gate: Optional[str] = Query(None),
    evidence_type: Optional[str] = Query(None),
    sort_dir: str = Query("desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)

    q = db.query(Evidence).filter_by(idea_id=idea_id, user_id=current_user.id)
    if gate:
        q = q.filter(Evidence.gate == gate)
    if evidence_type:
        q = q.filter(Evidence.evidence_type == evidence_type)

    q = q.order_by(
        Evidence.created_at.desc() if sort_dir == "desc" else Evidence.created_at.asc()
    )
    items = q.all()
    return EvidenceListResponse(
        items=[EvidenceResponse.model_validate(e) for e in items],
        total=len(items),
    )


@router.get("/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(
    idea_id: str,
    evidence_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_idea_or_404(idea_id, current_user.id, db)
    ev = db.query(Evidence).filter_by(
        id=evidence_id, idea_id=idea_id, user_id=current_user.id
    ).first()
    if not ev:
        raise HTTPException(404, "Evidence not found")
    return EvidenceResponse.model_validate(ev)
