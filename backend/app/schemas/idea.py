from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

OfferLadderRungType = Literal["service", "productized_service", "software"]
ProductUseFrequencyType = Literal["daily", "weekly", "monthly"]
PaymentModelType = Literal["stripe_direct", "paddle_mor", "lemonsqueezy_mor", "other"]
IdeaStatusType = Literal[
    "discovery", "scoring", "validating", "building",
    "retention", "growing", "killed", "parked",
]
GateStatusType = Literal["not_started", "in_progress", "passed", "failed"]


class IdeaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    one_liner: str = ""
    audience: str = ""
    problem_statement: str = ""
    proposed_solution: str = ""
    offer_ladder_rung: OfferLadderRungType = "software"
    target_price_point: Optional[float] = None
    product_use_frequency: Optional[ProductUseFrequencyType] = None
    activation_event: Optional[str] = None
    payment_model: Optional[PaymentModelType] = None
    expected_international_pct: Optional[int] = None


class IdeaUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    one_liner: Optional[str] = None
    audience: Optional[str] = None
    problem_statement: Optional[str] = None
    proposed_solution: Optional[str] = None
    offer_ladder_rung: Optional[OfferLadderRungType] = None
    target_price_point: Optional[float] = None
    product_use_frequency: Optional[ProductUseFrequencyType] = None
    activation_event: Optional[str] = None
    payment_model: Optional[PaymentModelType] = None
    expected_international_pct: Optional[int] = None
    kill_triggers: Optional[dict] = None
    gate_1_status: Optional[GateStatusType] = None
    gate_2_status: Optional[GateStatusType] = None
    gate_3_status: Optional[GateStatusType] = None


class IdeaStatusTransition(BaseModel):
    new_status: IdeaStatusType


class IdeaResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    user_id: str
    name: str
    one_liner: str
    audience: str
    problem_statement: str
    proposed_solution: str
    offer_ladder_rung: str
    target_price_point: Optional[float]
    product_use_frequency: Optional[str]
    activation_event: Optional[str]
    payment_model: Optional[str]
    expected_international_pct: Optional[int]
    status: str
    gate_1_status: str
    gate_2_status: str
    gate_3_status: str
    kill_date: Optional[datetime]
    kill_triggers: Optional[dict]
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime]
    archive_note: Optional[str] = None
    weighted_total: Optional[float] = None
    days_in_stage: Optional[int] = None


class ArchiveRequest(BaseModel):
    decision_note: str = Field(..., min_length=1)


class IdeaListResponse(BaseModel):
    items: list[IdeaResponse]
    total: int
