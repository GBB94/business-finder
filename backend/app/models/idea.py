from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Float, Integer, DateTime, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OfferLadderRung(str, enum.Enum):
    service = "service"
    productized_service = "productized_service"
    software = "software"


class ProductUseFrequency(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class PaymentModel(str, enum.Enum):
    stripe_direct = "stripe_direct"
    paddle_mor = "paddle_mor"
    lemonsqueezy_mor = "lemonsqueezy_mor"
    other = "other"


class IdeaStatus(str, enum.Enum):
    discovery = "discovery"
    scoring = "scoring"
    validating = "validating"
    building = "building"
    retention = "retention"
    growing = "growing"
    killed = "killed"
    parked = "parked"


class GateStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    passed = "passed"
    failed = "failed"


def _utcnow():
    return datetime.now(timezone.utc)


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    one_liner: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False, default="")
    proposed_solution: Mapped[str] = mapped_column(Text, nullable=False, default="")

    offer_ladder_rung: Mapped[str] = mapped_column(
        Enum(OfferLadderRung), nullable=False, default=OfferLadderRung.software
    )
    target_price_point: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    product_use_frequency: Mapped[Optional[str]] = mapped_column(
        Enum(ProductUseFrequency), nullable=True
    )
    activation_event: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payment_model: Mapped[Optional[str]] = mapped_column(
        Enum(PaymentModel), nullable=True
    )
    expected_international_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(IdeaStatus), nullable=False, default=IdeaStatus.discovery
    )

    gate_1_status: Mapped[str] = mapped_column(
        Enum(GateStatus), nullable=False, default=GateStatus.not_started
    )
    gate_2_status: Mapped[str] = mapped_column(
        Enum(GateStatus), nullable=False, default=GateStatus.not_started
    )
    gate_3_status: Mapped[str] = mapped_column(
        Enum(GateStatus), nullable=False, default=GateStatus.not_started
    )

    validation_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="standard")

    kill_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    kill_triggers: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    archive_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scores = relationship("Score", back_populates="idea", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="idea", cascade="all, delete-orphan")
    research_jobs = relationship("ResearchJob", back_populates="idea")
    monthly_reviews = relationship("MonthlyReview", back_populates="idea", cascade="all, delete-orphan")
    metric_entries = relationship("MetricEntry", back_populates="idea", cascade="all, delete-orphan")
