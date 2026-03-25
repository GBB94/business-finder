"""Discovery pipeline service.

Core logic for creating CandidateIdea records from pain clusters,
deduplicating against existing candidates, and promoting candidates
to full Ideas.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.adapters.base import RawPost
from app.models.candidate_idea import CandidateIdea
from app.models.candidate_source_post import CandidateSourcePost
from app.models.evidence import Evidence, GateLabel, EvidenceType, SourceType, Sentiment
from app.models.idea import Idea
from app.services.idea_service import seed_kill_triggers
from app.services.opportunity_analysis_service import OPPORTUNITY_ANALYSIS_PROMPT_VERSION

logger = logging.getLogger(__name__)

# Initial dedup threshold. Tune after first 3-4 scan runs.
DEDUP_THRESHOLD = 0.45

_STOP_WORDS = {"the", "a", "an", "is", "are", "to", "for", "of", "and", "or", "in", "on", "with", "it"}


def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity between two strings (lowercased, stop words removed)."""
    ta = set(a.lower().split()) - _STOP_WORDS
    tb = set(b.lower().split()) - _STOP_WORDS
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_duplicate(
    signal: str,
    existing: list[CandidateIdea],
    threshold: float = DEDUP_THRESHOLD,
) -> bool:
    """Check if a problem signal is too similar to an existing candidate."""
    return any(
        _jaccard(signal, c.problem_signal) >= threshold
        for c in existing
        if c.status != "dismissed" or c.dismiss_reason != "resurface_later"
    )


def create_candidate_from_cluster(
    db: Session,
    user_id: str,
    cluster: dict,
    job_id: str,
    post_map: dict[str, RawPost],
    model_version: str,
) -> CandidateIdea:
    """Create a CandidateIdea with provenance source posts from a pain cluster."""
    candidate = CandidateIdea(
        user_id=user_id,
        source="scanner",
        status="pending_review",
        problem_signal=cluster["problem_signal"],
        target_audience=cluster["target_audience"],
        pain_intensity_score=cluster.get("intensity_score"),
        pain_type=cluster.get("pain_type"),
        source_communities=cluster.get("communities_covered", []),
        cross_community=cluster.get("cross_community", False),
        spending_signals=cluster.get("spending_signals", []),
        competitor_mentions=cluster.get("competitor_mentions", []),
        competition_signal=cluster.get("competition_signal", "unknown"),
        raw_themes=cluster.get("themes", []),
        sample_post_count=cluster.get("sample_count", 0),
        prompt_version=OPPORTUNITY_ANALYSIS_PROMPT_VERSION,
        model_version=model_version,
        scan_job_id=job_id,
        derived_content_purged=False,
    )
    db.add(candidate)
    db.flush()

    for post_id in cluster.get("source_post_ids", []):
        raw = post_map.get(post_id)
        if not raw:
            continue
        db.add(CandidateSourcePost(
            candidate_id=candidate.id,
            source_id=raw.source_id,
            source_type=raw.source_type,
            source_url=raw.source_url,
            subreddit=raw.subreddit,
            title=raw.title,
            engagement_score=raw.score + raw.comment_count,
        ))

    return candidate


def promote_candidate(
    db: Session,
    candidate: CandidateIdea,
    idea: Idea,
) -> Idea:
    """Link a candidate to its promoted Idea and copy source posts as Evidence."""
    candidate.status = "promoted"
    candidate.promoted_idea_id = idea.id
    candidate.reviewed_at = datetime.now(timezone.utc)

    _SENTIMENT_MAP = {
        "positive": Sentiment.positive,
        "negative": Sentiment.negative,
        "neutral": Sentiment.neutral,
        "mixed": Sentiment.mixed,
    }

    for sp in candidate.source_posts:
        if sp.content_purged:
            continue
        db.add(Evidence(
            idea_id=idea.id,
            user_id=idea.user_id,
            gate=GateLabel.discovery,
            evidence_type=EvidenceType.community_signal,
            title=sp.title,
            content={"source_id": sp.source_id, "engagement": sp.engagement_score},
            source_url=sp.source_url,
            source_type=SourceType.reddit if sp.source_type == "reddit" else SourceType.hn,
            sentiment=_SENTIMENT_MAP.get(sp.sentiment, Sentiment.neutral),
        ))

    db.flush()
    return idea


def dismiss_candidate(
    db: Session,
    candidate: CandidateIdea,
    dismiss_reason: str,
    review_note: Optional[str] = None,
) -> CandidateIdea:
    """Dismiss a candidate with a required reason."""
    candidate.status = "dismissed"
    candidate.dismiss_reason = dismiss_reason
    candidate.review_note = review_note
    candidate.reviewed_at = datetime.now(timezone.utc)
    db.flush()
    return candidate
