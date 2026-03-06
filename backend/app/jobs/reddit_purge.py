"""Nightly Reddit content purge job.

Checks each Reddit-sourced evidence item against the Reddit API.
If the source post has been deleted ([deleted]/[removed] body or author,
or 404), purges all downstream content from the evidence record and
triggers recomputation of any Sales Safari reports.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models.evidence import Evidence, SourceType

logger = logging.getLogger(__name__)

_DELETED_MARKERS = {"[deleted]", "[removed]"}


def _extract_reddit_post_id(source_url: str | None) -> str | None:
    """Extract the Reddit post ID from a source URL like https://reddit.com/r/.../comments/ABC123/..."""
    if not source_url:
        return None
    parts = source_url.split("/comments/")
    if len(parts) < 2:
        return None
    post_id = parts[1].split("/")[0]
    return post_id if post_id else None


def _is_deleted(post_data: dict) -> bool:
    """Check if a Reddit post/comment has been deleted or removed."""
    selftext = post_data.get("selftext", "")
    author = post_data.get("author", "")
    if selftext in _DELETED_MARKERS:
        return True
    if author in _DELETED_MARKERS:
        return True
    if post_data.get("removed_by_category"):
        return True
    return False


def _purge_evidence(ev: Evidence, reason: str) -> None:
    """Fully purge content from an evidence record."""
    ev.content = None
    ev.content_purged = True
    ev.purge_reason = reason
    ev.source_url = None
    ev.tags = None


def run_reddit_purge() -> None:
    """Check all Reddit-sourced evidence and purge if source is deleted.

    Also recomputes Sales Safari reports by marking them for re-synthesis.
    """
    db = SessionLocal()
    purged_count = 0
    ideas_needing_recompute: set[str] = set()

    try:
        # Get all non-purged Reddit evidence
        reddit_evidence = (
            db.query(Evidence)
            .filter_by(
                source_type=SourceType.reddit,
                content_purged=False,
                user_id=settings.DEFAULT_USER_ID,
            )
            .all()
        )

        if not reddit_evidence:
            logger.info("Reddit purge: no Reddit evidence to check")
            return

        logger.info("Reddit purge: checking %d evidence items", len(reddit_evidence))

        # Authenticate with Reddit API if credentials available
        token = None
        if settings.REDDIT_CLIENT_ID and settings.REDDIT_CLIENT_SECRET:
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(
                        "https://www.reddit.com/api/v1/access_token",
                        data={"grant_type": "client_credentials"},
                        auth=(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET),
                        headers={"User-Agent": settings.REDDIT_USER_AGENT},
                    )
                    resp.raise_for_status()
                    token = resp.json()["access_token"]
            except Exception:
                logger.exception("Reddit purge: failed to authenticate, skipping")
                return

        with httpx.Client(timeout=10.0) as client:
            for ev in reddit_evidence:
                post_id = _extract_reddit_post_id(ev.source_url)
                if not post_id:
                    continue

                try:
                    if token:
                        resp = client.get(
                            f"https://oauth.reddit.com/api/info?id=t3_{post_id}",
                            headers={
                                "Authorization": f"Bearer {token}",
                                "User-Agent": settings.REDDIT_USER_AGENT,
                            },
                        )
                    else:
                        resp = client.get(
                            f"https://www.reddit.com/api/info.json?id=t3_{post_id}",
                            headers={"User-Agent": settings.REDDIT_USER_AGENT},
                        )

                    if resp.status_code == 404:
                        _purge_evidence(ev, "Source post returned 404 (deleted)")
                        purged_count += 1
                        ideas_needing_recompute.add(ev.idea_id)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    children = data.get("data", {}).get("children", [])
                    if not children:
                        _purge_evidence(ev, "Source post no longer exists in Reddit API")
                        purged_count += 1
                        ideas_needing_recompute.add(ev.idea_id)
                        continue

                    post_data = children[0].get("data", {})
                    if _is_deleted(post_data):
                        _purge_evidence(ev, "Source content deleted per Reddit Data API Terms")
                        purged_count += 1
                        ideas_needing_recompute.add(ev.idea_id)

                except Exception:
                    logger.exception("Reddit purge: failed to check post %s", post_id)

        # Purge Sales Safari reports that reference purged ideas
        for idea_id in ideas_needing_recompute:
            safari_reports = (
                db.query(Evidence)
                .filter(
                    Evidence.idea_id == idea_id,
                    Evidence.user_id == settings.DEFAULT_USER_ID,
                    Evidence.title.like("Sales Safari Report:%"),
                    Evidence.content_purged == False,
                )
                .all()
            )
            for report in safari_reports:
                _purge_evidence(
                    report,
                    "Recompute required: upstream Reddit evidence was purged",
                )
                purged_count += 1

        db.commit()
        logger.info(
            "Reddit purge complete: %d items purged, %d ideas need report recompute",
            purged_count,
            len(ideas_needing_recompute),
        )

    except Exception:
        logger.exception("Reddit purge job failed")
        db.rollback()
    finally:
        db.close()
