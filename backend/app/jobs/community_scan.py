"""RQ entry point for community scan jobs."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import redis
from rq import Queue

from app.config import settings
from app.database import SessionLocal
from app.models.research_job import JobStatus, ResearchJob
from app.services.research_service import run_scan_pipeline_sync

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
# Backoff schedule in seconds: 30s, 2min, 10min
BACKOFF_SECONDS = [30, 120, 600]


def run_community_scan(job_id: str) -> None:
    """RQ entry point. Creates its own DB session, runs the async pipeline."""
    db = SessionLocal()
    try:
        job = db.query(ResearchJob).filter_by(id=job_id).first()
        if not job:
            logger.error("ResearchJob %s not found", job_id)
            return

        # Mark running
        job.status = JobStatus.running
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        run_scan_pipeline_sync(db, job)

    except Exception as exc:
        logger.exception("Community scan failed for job %s", job_id)
        db.rollback()

        # Re-fetch job after rollback
        job = db.query(ResearchJob).filter_by(id=job_id).first()
        if job:
            job.retry_count = (job.retry_count or 0) + 1
            job.error_message = str(exc)[:2000]

            if job.retry_count >= MAX_RETRIES:
                job.status = JobStatus.dead_letter
                job.completed_at = datetime.now(timezone.utc)
            else:
                job.status = JobStatus.queued
                # Re-enqueue with backoff
                delay_secs = BACKOFF_SECONDS[min(job.retry_count - 1, len(BACKOFF_SECONDS) - 1)]
                try:
                    conn = redis.from_url(settings.REDIS_URL)
                    q = Queue("default", connection=conn)
                    q.enqueue_in(
                        timedelta(seconds=delay_secs),
                        "app.jobs.community_scan.run_community_scan",
                        job.id,
                    )
                    logger.info(
                        "Re-enqueued job %s (retry %d) with %ds delay",
                        job.id, job.retry_count, delay_secs,
                    )
                except Exception:
                    logger.exception("Failed to re-enqueue job %s", job.id)
                    job.status = JobStatus.failed
                    job.completed_at = datetime.now(timezone.utc)

            db.commit()
    finally:
        db.close()
