"""Discovery scan scheduler.

Enqueues nightly discovery scans for all users with active watchlist entries.
Wire into the existing nightly trigger alongside run_all_nightly.
"""
from __future__ import annotations

import logging

import redis
from rq import Queue

from app.config import settings
from app.database import SessionLocal
from app.models.watchlist_entry import WatchlistEntry

logger = logging.getLogger(__name__)


def schedule_discovery_scans() -> None:
    """Enqueue a discovery scan job for each user with active watchlist entries."""
    db = SessionLocal()
    try:
        users = (
            db.query(WatchlistEntry.user_id)
            .filter_by(active=True)
            .distinct()
            .all()
        )
        if not users:
            logger.info("No users with active watchlist entries")
            return

        conn = redis.from_url(settings.REDIS_URL)
        q = Queue("discovery", connection=conn)
        for (user_id,) in users:
            q.enqueue(
                "app.jobs.discovery_scan.run_discovery_scan_for_user",
                user_id,
            )
            logger.info("Enqueued discovery scan for user %s", user_id)

    except Exception:
        logger.exception("Failed to schedule discovery scans")
    finally:
        db.close()
