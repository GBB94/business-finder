from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import date, datetime, timezone

import redis
from rq import Queue
from sqlalchemy.orm import Session

from app.adapters.hn_adapter import HNAdapter
from app.adapters.reddit_adapter import RedditAdapter
from app.config import settings
from app.models.evidence import Evidence, EvidenceType, GateLabel, Sentiment, SourceType
from app.models.idea import Idea
from app.models.research_job import JobStatus, JobType, ResearchJob
from app.services.analysis_service import AnalysisResult, analyze_community_posts

logger = logging.getLogger(__name__)


def _idempotency_key(idea_id: str, queries: list[str], sources: list[str]) -> str:
    payload = f"{idea_id}:{sorted(queries)}:{sorted(sources)}:{date.today()}"
    return hashlib.sha256(payload.encode()).hexdigest()


def enqueue_community_scan(
    db: Session,
    idea_id: str,
    queries: list[str],
    sources: list[str] | None = None,
    user_id: str | None = None,
) -> ResearchJob:
    """Create a ResearchJob record and enqueue it to RQ."""
    sources = sources or ["hn", "reddit"]
    idem_key = _idempotency_key(idea_id, queries, sources)

    existing = (
        db.query(ResearchJob)
        .filter(ResearchJob.idempotency_key.like(f"{idem_key}%"))
        .filter(ResearchJob.status.in_([JobStatus.queued, JobStatus.running, JobStatus.completed]))
        .first()
    )
    if existing:
        return existing

    prior_attempts = (
        db.query(ResearchJob)
        .filter(ResearchJob.idempotency_key.like(f"{idem_key}%"))
        .count()
    )
    retry_key = idem_key if prior_attempts == 0 else f"{idem_key}:r{prior_attempts}"

    if not user_id:
        raise ValueError("user_id is required")

    job = ResearchJob(
        id=str(uuid.uuid4()),
        idea_id=idea_id,
        user_id=user_id,
        job_type=JobType.community_scan,
        status=JobStatus.queued,
        input_params={"queries": queries, "sources": sources},
        idempotency_key=retry_key,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        conn = redis.from_url(settings.REDIS_URL)
        q = Queue("default", connection=conn)
        q.enqueue(
            "app.jobs.community_scan.run_community_scan",
            job.id,
        )
    except Exception:
        logger.exception("Failed to enqueue job %s — Redis may be unavailable", job.id)
        job.status = JobStatus.failed
        job.error_message = "Failed to connect to job queue. Is Redis running?"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    return job


async def _run_scan_pipeline(db: Session, job: ResearchJob) -> None:
    """Core scan pipeline — runs inside the RQ job."""
    idea = db.query(Idea).filter_by(id=job.idea_id).first()
    if not idea:
        raise ValueError(f"Idea {job.idea_id} not found")

    params = job.input_params or {}
    queries = params.get("queries", [])
    sources = params.get("sources", ["hn", "reddit"])

    tasks = []
    if "hn" in sources:
        tasks.append(HNAdapter().search(queries, limit=25))
    if "reddit" in sources:
        tasks.append(RedditAdapter().search(queries, limit=25))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_posts = []
    for result in results:
        if isinstance(result, Exception):
            logger.error("Adapter error: %s", result)
            continue
        all_posts.extend(result)

    seen = set()
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

    analysis = await analyze_community_posts(
        idea_name=idea.name,
        idea_audience=idea.audience,
        idea_problem=idea.problem_statement,
        idea_solution=idea.proposed_solution,
        posts=unique_posts,
    )

    evidence_count = 0
    for sp in analysis.scored_posts:
        if sp.relevance_score < 5:
            continue

        source_type_val = SourceType.hn if sp.source_type == "hn" else SourceType.reddit
        sentiment_val = _map_sentiment(sp.sentiment)

        evidence_title = sp.summary[:500] if sp.summary else "Community Signal"

        ev = Evidence(
            idea_id=idea.id,
            user_id=job.user_id,
            gate=GateLabel.discovery,
            evidence_type=EvidenceType.community_signal,
            title=evidence_title,
            content={
                "summary": sp.summary,
                "relevance_score": sp.relevance_score,
                "themes": analysis.themes,
                "original_score": sp.original_score,
            },
            source_url=sp.source_url,
            source_type=source_type_val,
            sentiment=sentiment_val,
            connector_version="community_scan_v1",
            model_version=analysis.model_version,
            ingested_at=datetime.now(timezone.utc),
        )
        db.add(ev)
        evidence_count += 1

    if analysis.sales_safari_summary:
        report_ev = Evidence(
            idea_id=idea.id,
            user_id=job.user_id,
            gate=GateLabel.discovery,
            evidence_type=EvidenceType.community_signal,
            title=f"Sales Safari Report: {idea.name}"[:500],
            content={
                "report": analysis.sales_safari_summary,
                "themes": analysis.themes,
                "language_patterns": analysis.language_patterns,
                "objections": analysis.objections,
                "post_count": len(unique_posts),
            },
            source_type=SourceType.other,
            sentiment=Sentiment.neutral,
            connector_version="community_scan_v1",
            model_version=analysis.model_version,
            ingested_at=datetime.now(timezone.utc),
        )
        db.add(report_ev)

    job.status = JobStatus.completed
    job.results = {
        "post_count": len(unique_posts),
        "evidence_created": evidence_count,
        "themes": analysis.themes,
        "model_version": analysis.model_version,
    }
    job.completed_at = datetime.now(timezone.utc)
    db.commit()


def run_scan_pipeline_sync(db: Session, job: ResearchJob) -> None:
    """Synchronous wrapper for the async pipeline."""
    asyncio.run(_run_scan_pipeline(db, job))


def _map_sentiment(s: str) -> Sentiment:
    mapping = {
        "positive": Sentiment.positive,
        "negative": Sentiment.negative,
        "neutral": Sentiment.neutral,
        "mixed": Sentiment.mixed,
    }
    return mapping.get(s, Sentiment.neutral)
