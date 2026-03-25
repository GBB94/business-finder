from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis
from fastapi import APIRouter, Depends, HTTPException, Query
from rq import Queue
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.candidate_idea import CandidateIdea
from app.models.candidate_source_post import CandidateSourcePost
from app.models.idea import Idea
from app.models.research_job import ResearchJob, JobType, JobStatus
from app.models.user import User
from app.schemas.candidate import (
    CandidateCreate,
    CandidateDismiss,
    CandidateResponse,
    CandidateDetailResponse,
    CandidateSourcePostResponse,
    CandidateListResponse,
)
from app.services.discovery_service import promote_candidate, dismiss_candidate
from app.services.idea_service import seed_kill_triggers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


@router.get("", response_model=CandidateListResponse)
def list_candidates(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    pain_type: Optional[str] = Query(None),
    cross_community: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(CandidateIdea).filter_by(user_id=current_user.id)
    if status:
        q = q.filter_by(status=status)
    if source:
        q = q.filter_by(source=source)
    if pain_type:
        q = q.filter_by(pain_type=pain_type)
    if cross_community is not None:
        q = q.filter_by(cross_community=cross_community)

    candidates = q.order_by(CandidateIdea.created_at.desc()).all()
    return CandidateListResponse(
        items=[CandidateResponse.model_validate(c) for c in candidates],
        total=len(candidates),
    )


@router.post("", response_model=CandidateResponse, status_code=201)
def create_candidate(
    body: CandidateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a founder-suggested candidate idea."""
    candidate = CandidateIdea(
        user_id=current_user.id,
        source="founder_suggestion",
        status="pending_review",
        problem_signal=body.problem_signal,
        target_audience=body.target_audience,
        founder_note=body.founder_note,
        suggested_solution=body.suggested_solution,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    if body.auto_scan:
        _enqueue_candidate_scan(db, candidate, current_user.id)

    return CandidateResponse.model_validate(candidate)


@router.get("/{candidate_id}", response_model=CandidateDetailResponse)
def get_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = (
        db.query(CandidateIdea)
        .filter_by(id=candidate_id, user_id=current_user.id)
        .first()
    )
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    source_posts = (
        db.query(CandidateSourcePost)
        .filter_by(candidate_id=candidate_id)
        .order_by(CandidateSourcePost.engagement_score.desc())
        .all()
    )

    resp = CandidateDetailResponse.model_validate(candidate)
    resp.source_posts = [CandidateSourcePostResponse.model_validate(sp) for sp in source_posts]
    return resp


@router.post("/{candidate_id}/promote", response_model=CandidateResponse)
def promote(
    candidate_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Promote a candidate to a full Idea, carrying source posts as Evidence."""
    candidate = (
        db.query(CandidateIdea)
        .filter_by(id=candidate_id, user_id=current_user.id)
        .first()
    )
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    if candidate.status != "pending_review":
        raise HTTPException(400, f"Cannot promote candidate with status '{candidate.status}'")

    idea = Idea(
        user_id=current_user.id,
        name=candidate.problem_signal[:200],
        one_liner=candidate.problem_signal,
        audience=candidate.target_audience,
        problem_statement=candidate.problem_signal,
        proposed_solution=candidate.suggested_solution or "",
    )
    seed_kill_triggers(idea)
    db.add(idea)
    db.flush()

    promote_candidate(db, candidate, idea)
    db.commit()
    db.refresh(candidate)

    return CandidateResponse.model_validate(candidate)


@router.post("/{candidate_id}/scan", status_code=202)
def scan_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enqueue a deeper scan for this candidate."""
    candidate = (
        db.query(CandidateIdea)
        .filter_by(id=candidate_id, user_id=current_user.id)
        .first()
    )
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    job = _enqueue_candidate_scan(db, candidate, current_user.id)
    if not job:
        raise HTTPException(503, "Failed to enqueue scan job")

    return {"status": "queued", "job_id": job.id}


@router.post("/{candidate_id}/dismiss", response_model=CandidateResponse)
def dismiss(
    candidate_id: str,
    body: CandidateDismiss,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = (
        db.query(CandidateIdea)
        .filter_by(id=candidate_id, user_id=current_user.id)
        .first()
    )
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    if candidate.status != "pending_review":
        raise HTTPException(400, f"Cannot dismiss candidate with status '{candidate.status}'")

    dismiss_candidate(db, candidate, body.dismiss_reason, body.review_note)
    db.commit()
    db.refresh(candidate)
    return CandidateResponse.model_validate(candidate)


def _enqueue_candidate_scan(
    db: Session, candidate: CandidateIdea, user_id: str
) -> ResearchJob | None:
    """Create a research job and enqueue a candidate scan."""
    queries = [candidate.problem_signal, candidate.target_audience]

    idem_key = hashlib.sha256(
        f"candidate_scan:{candidate.id}:{datetime.now(timezone.utc).date()}".encode()
    ).hexdigest()

    # Check for existing job with same idempotency key (same candidate, same day)
    existing = db.query(ResearchJob).filter_by(idempotency_key=idem_key).first()
    if existing:
        if existing.status in ("queued", "running"):
            return existing  # already in progress
        if existing.status == "completed":
            return existing  # already done today

    job = ResearchJob(
        id=str(uuid.uuid4()),
        user_id=user_id,
        idea_id=None,
        job_type=JobType.discovery_scan,
        status=JobStatus.queued,
        input_params={
            "candidate_id": candidate.id,
            "queries": queries,
            "sources": ["hn", "reddit"],
        },
        idempotency_key=idem_key if not existing else hashlib.sha256(
            f"candidate_scan:{candidate.id}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        conn = redis.from_url(settings.REDIS_URL)
        q = Queue("discovery", connection=conn)
        q.enqueue(
            "app.jobs.candidate_scan.run_candidate_scan",
            job.id,
        )
        return job
    except Exception:
        logger.exception("Failed to enqueue candidate scan")
        job.status = JobStatus.failed
        job.error_message = "Failed to enqueue. Redis unavailable."
        db.commit()
        return None
