from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class WeightUpdate(BaseModel):
    dimension: str
    weight: float = Field(..., ge=0, le=100)


class WeightsUpdateRequest(BaseModel):
    weights: list[WeightUpdate]


class WeightResponse(BaseModel):
    model_config = {"from_attributes": True}

    dimension: str
    weight: float


class WeightsResponse(BaseModel):
    weights: list[WeightResponse]
    total_weight: float
