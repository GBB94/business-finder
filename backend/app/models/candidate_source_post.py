from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class CandidateSourcePost(Base):
    __tablename__ = "candidate_source_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidate_ideas.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    subreddit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)

    relevance_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    engagement_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentiment: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    content_purged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    purge_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    candidate = relationship("CandidateIdea", back_populates="source_posts")
