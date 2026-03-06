from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Boolean, DateTime, Enum, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GateLabel(str, enum.Enum):
    gate_1 = "1"
    gate_2 = "2"
    gate_3 = "3"
    discovery = "discovery"
    scoring = "scoring"


class EvidenceType(str, enum.Enum):
    community_signal = "community_signal"
    customer_conversation = "customer_conversation"
    landing_page_metric = "landing_page_metric"
    pre_sale = "pre_sale"
    competitor_datapoint = "competitor_datapoint"
    keyword_data = "keyword_data"
    retention_metric = "retention_metric"
    financial_metric = "financial_metric"
    outreach_metric = "outreach_metric"
    note = "note"


class SourceType(str, enum.Enum):
    reddit = "reddit"
    hn = "hn"
    github = "github"
    g2_manual = "g2_manual"
    capterra_manual = "capterra_manual"
    kw_manual = "kw_manual"
    stripe = "stripe"
    conversation = "conversation"
    note = "note"
    other = "other"


class Sentiment(str, enum.Enum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"
    mixed = "mixed"


def _utcnow():
    return datetime.now(timezone.utc)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id: Mapped[str] = mapped_column(String(36), ForeignKey("ideas.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    gate: Mapped[str] = mapped_column(Enum(GateLabel), nullable=False)
    evidence_type: Mapped[str] = mapped_column(Enum(EvidenceType), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    content_purged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    purge_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    source_type: Mapped[str] = mapped_column(Enum(SourceType), nullable=False, default=SourceType.other)
    sentiment: Mapped[str] = mapped_column(Enum(Sentiment), nullable=False, default=Sentiment.neutral)

    connector_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    idea = relationship("Idea", back_populates="evidence")
