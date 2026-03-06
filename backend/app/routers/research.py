from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.evidence import Evidence, EvidenceType
from app.models.idea import Idea
from app.models.research_job import ResearchJob
from app.schemas.research import (
    PurgeRequest,
    ResearchJobListResponse,
    ResearchJobResponse,
    ScanRequest,
)
from app.services.research_service import enqueue_community_scan

router = APIRouter(
    prefix="/api/ideas/{idea_id}/research",
    tags=["research"],
)


def _get_idea_or_404(idea_id: str, db: Session) -> Idea:
    idea = db.query(Idea).filter_by(id=idea_id, user_id=settings.DEFAULT_USER_ID).first()
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@router.post("/scan", response_model=ResearchJobResponse, status_code=202)
def start_scan(idea_id: str, body: ScanRequest, db: Session = Depends(get_db)):
    _get_idea_or_404(idea_id, db)
    job = enqueue_community_scan(
        db=db,
        idea_id=idea_id,
        queries=body.queries,
        sources=body.sources,
    )
    return ResearchJobResponse.model_validate(job)


@router.get("/jobs", response_model=ResearchJobListResponse)
def list_jobs(
    idea_id: str,
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    _get_idea_or_404(idea_id, db)

    q = db.query(ResearchJob).filter_by(
        idea_id=idea_id, user_id=settings.DEFAULT_USER_ID
    )
    if status:
        q = q.filter(ResearchJob.status == status)
    if job_type:
        q = q.filter(ResearchJob.job_type == job_type)

    q = q.order_by(ResearchJob.created_at.desc())
    items = q.all()
    return ResearchJobListResponse(
        items=[ResearchJobResponse.model_validate(j) for j in items],
        total=len(items),
    )


@router.get("/jobs/{job_id}", response_model=ResearchJobResponse)
def get_job(idea_id: str, job_id: str, db: Session = Depends(get_db)):
    _get_idea_or_404(idea_id, db)

    job = db.query(ResearchJob).filter_by(
        id=job_id, idea_id=idea_id, user_id=settings.DEFAULT_USER_ID
    ).first()
    if not job:
        raise HTTPException(404, "Research job not found")
    return ResearchJobResponse.model_validate(job)


@router.post("/purge")
def purge_evidence(idea_id: str, body: PurgeRequest, db: Session = Depends(get_db)):
    _get_idea_or_404(idea_id, db)

    cutoff = datetime.now(timezone.utc) - timedelta(days=body.older_than_days)

    items = (
        db.query(Evidence)
        .filter(
            Evidence.idea_id == idea_id,
            Evidence.user_id == settings.DEFAULT_USER_ID,
            Evidence.evidence_type == EvidenceType.community_signal,
            Evidence.created_at < cutoff,
            Evidence.content_purged == False,  # noqa: E712
        )
        .all()
    )

    count = 0
    for ev in items:
        ev.content = None
        ev.content_purged = True
        ev.purge_reason = "manual_purge"
        count += 1

    db.commit()
    return {"purged_count": count}
