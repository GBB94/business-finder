"""Nightly discovery scan job.

Scans watchlist entries (subreddits + HN types) for pain signals,
clusters them via Claude, and creates CandidateIdea records.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.adapters.base import RawPost
from app.adapters.hn_adapter import HNAdapter
from app.adapters.reddit_adapter import RedditAdapter
from app.database import SessionLocal
from app.models.candidate_idea import CandidateIdea
from app.models.research_job import ResearchJob, JobType, JobStatus
from app.models.watchlist_entry import WatchlistEntry
from app.services.discovery_service import is_duplicate, create_candidate_from_cluster
from app.services.opportunity_analysis_service import analyze_for_opportunities

logger = logging.getLogger(__name__)

# Generic pain signal queries for discovery scanning
PAIN_SIGNAL_QUERIES = [
    "frustrated with",
    "looking for alternative to",
    "wish there was a tool",
    "wasting time on",
    "paying too much for",
    "manual process",
    "broken workflow",
    "need help with",
    "anyone solved",
    "hate using",
    "switching from",
    "built my own",
    "spending hours on",
    "can't find a good",
    "workaround for",
]


async def _run_discovery_pipeline(
    db: Session, user_id: str, entries: list[WatchlistEntry]
) -> dict:
    """Core discovery pipeline. Scans entries, analyzes posts, creates candidates."""
    reddit = RedditAdapter()
    hn = HNAdapter()
    all_posts: list[RawPost] = []
    post_map: dict[str, RawPost] = {}
    rate_limit_events = 0
    partial_entries: list[str] = []

    for entry in entries:
        entry_posts: list[RawPost] = []

        if entry.source_type == "subreddit":
            for query in PAIN_SIGNAL_QUERIES:
                posts = await reddit.search_subreddit(
                    entry.source_name, [query], limit=15
                )
                if posts is None:
                    rate_limit_events += 1
                else:
                    entry_posts.extend(posts)
            if rate_limit_events > len(PAIN_SIGNAL_QUERIES) // 2:
                partial_entries.append(entry.source_name)
        else:
            # HN entry
            tags = HNAdapter.TAG_MAP.get(entry.source_type, "story")
            posts = await hn.search(PAIN_SIGNAL_QUERIES, limit=50, tags=tags)
            entry_posts.extend(posts)

        # Deduplicate across entries
        for p in entry_posts:
            key = f"{p.source_type}:{p.source_id}"
            if key not in post_map:
                post_map[key] = p
                all_posts.append(p)

        entry.last_scanned_at = datetime.now(timezone.utc)

    if not all_posts:
        db.commit()
        return {
            "entries_scanned": len(entries),
            "posts_fetched": 0,
            "clusters_found": 0,
            "candidates_created": 0,
            "rate_limit_events": rate_limit_events,
            "partial_entries": partial_entries,
        }

    from app.services.agent_task_service import get_model_for_task

    model = get_model_for_task("community_scan")
    result = await analyze_for_opportunities(all_posts, model)

    # Load existing candidates for dedup check (last 30 days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    existing = (
        db.query(CandidateIdea)
        .filter(
            CandidateIdea.user_id == user_id,
            CandidateIdea.created_at >= cutoff,
        )
        .all()
    )

    # Create research job record
    job = ResearchJob(
        id=str(uuid.uuid4()),
        user_id=user_id,
        idea_id=None,
        job_type=JobType.discovery_scan,
        status=JobStatus.completed,
        input_params={"entries": [e.source_name for e in entries]},
        idempotency_key=hashlib.sha256(
            f"discovery:{user_id}:{date.today()}".encode()
        ).hexdigest(),
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.flush()

    candidates_created = 0
    for cluster in result.pain_clusters:
        if cluster.get("intensity_score", 0) < 5:
            continue
        if is_duplicate(cluster["problem_signal"], existing):
            continue
        candidate = create_candidate_from_cluster(
            db, user_id, cluster, job.id, post_map, model or "",
        )
        existing.append(candidate)
        candidates_created += 1

    job.results = {
        "entries_scanned": len(entries),
        "posts_fetched": len(all_posts),
        "clusters_found": len(result.pain_clusters),
        "candidates_created": candidates_created,
        "rate_limit_events": rate_limit_events,
        "partial_entries": partial_entries,
    }
    db.commit()
    return job.results


def run_discovery_scan_for_user(user_id: str) -> None:
    """RQ entry point. Scans all active watchlist entries for a user."""
    db = SessionLocal()
    try:
        entries = (
            db.query(WatchlistEntry)
            .filter_by(user_id=user_id, active=True)
            .all()
        )
        if not entries:
            logger.info("No active watchlist entries for user %s", user_id)
            return

        results = asyncio.run(_run_discovery_pipeline(db, user_id, entries))
        logger.info(
            "Discovery scan for user %s: %d posts, %d candidates created",
            user_id, results.get("posts_fetched", 0), results.get("candidates_created", 0),
        )
    except Exception:
        logger.exception("Discovery scan failed for user %s", user_id)
        db.rollback()
    finally:
        db.close()
