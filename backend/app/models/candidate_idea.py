from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Float, Integer, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class CandidateIdea(Base):
    __tablename__ = "candidate_ideas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_review")

    # Signal fields
    problem_signal: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience: Mapped[str] = mapped_column(Text, nullable=False)
    pain_intensity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pain_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_communities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    cross_community: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spending_signals: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    competitor_mentions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    competition_signal: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    raw_themes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    sample_post_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Evaluation
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Founder suggestion
    founder_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_solution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Lifecycle
    scan_job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    promoted_idea_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("ideas.id"), nullable=True
    )
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dismiss_reason: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    derived_content_purged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    source_posts = relationship(
        "CandidateSourcePost", back_populates="candidate", cascade="all, delete-orphan"
    )
