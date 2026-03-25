"""Candidate-aware scan job.

Used for 'Scan Deeper' on a candidate and for founder auto_scan.
Uses the candidate's problem_signal and target_audience as context
substitutes where community_scan would use an Idea object.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.adapters.hn_adapter import HNAdapter
from app.adapters.reddit_adapter import RedditAdapter
from app.adapters.base import RawPost
from app.database import SessionLocal
from app.models.candidate_idea import CandidateIdea
from app.models.candidate_source_post import CandidateSourcePost
from app.models.research_job import ResearchJob, JobStatus
from app.services.analysis_service import analyze_community_posts

logger = logging.getLogger(__name__)


async def _run_candidate_scan_pipeline(db, job: ResearchJob) -> None:
    """Candidate-aware scan pipeline. Does NOT require a real Idea object."""
    candidate_id = (job.input_params or {}).get("candidate_id")
    if not candidate_id:
        raise ValueError("candidate_id required in input_params for candidate scans")

    candidate = db.query(CandidateIdea).filter_by(id=candidate_id).first()
    if not candidate:
        raise ValueError(f"CandidateIdea {candidate_id} not found")

    params = job.input_params or {}
    queries = params.get("queries", [])
    sources = params.get("sources", ["hn", "reddit"])

    all_posts: list[RawPost] = []
    if "reddit" in sources:
        adapter = RedditAdapter()
        posts = await adapter.search(queries, limit=25)
        all_posts.extend(posts)
    if "hn" in sources:
        hn_posts = await HNAdapter().search(queries, limit=25)
        all_posts.extend(hn_posts)

    # Deduplicate
    seen: set[str] = set()
    unique_posts = []
    for p in all_posts:
        key = f"{p.source_type}:{p.source_id}"
        if key not in seen:
            seen.add(key)
            unique_posts.append(p)

    if not unique_posts:
        job.status = JobStatus.completed
        job.results = {"post_count": 0, "evidence_created": 0}
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return

    from app.services.agent_task_service import get_model_for_task

    analysis = await analyze_community_posts(
        idea_name=candidate.problem_signal,
        idea_audience=candidate.target_audience,
        idea_problem=candidate.problem_signal,
        idea_solution=candidate.suggested_solution or "",
        posts=unique_posts,
        model=get_model_for_task("community_scan"),
    )

    evidence_count = 0
    post_map = {p.source_id: p for p in unique_posts}
    for sp in analysis.scored_posts:
        if sp.relevance_score < 5:
            continue
        raw = post_map.get(sp.source_id)
        if not raw:
            continue
        db.add(CandidateSourcePost(
            candidate_id=candidate.id,
            source_id=sp.source_id,
            source_type=sp.source_type,
            source_url=sp.source_url,
            subreddit=raw.subreddit,
            title=raw.title,
            relevance_score=sp.relevance_score,
            engagement_score=raw.score + raw.comment_count,
            sentiment=sp.sentiment,
        ))
        evidence_count += 1

    job.status = JobStatus.completed
    job.results = {
        "post_count": len(unique_posts),
        "evidence_created": evidence_count,
        "themes": analysis.themes,
        "model_version": analysis.model_version,
    }
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


def run_candidate_scan(job_id: str) -> None:
    """RQ entry point for candidate scans."""
    db = SessionLocal()
    try:
        job = db.query(ResearchJob).filter_by(id=job_id).first()
        if not job:
            logger.error("Candidate scan job %s not found", job_id)
            return

        job.status = JobStatus.running
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        asyncio.run(_run_candidate_scan_pipeline(db, job))

    except Exception as exc:
        logger.exception("Candidate scan job %s failed", job_id)
        job = db.query(ResearchJob).filter_by(id=job_id).first()
        if job:
            job.status = JobStatus.failed
            job.error_message = str(exc)[:2000]
            db.commit()
    finally:
        db.close()
