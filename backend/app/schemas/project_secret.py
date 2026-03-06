from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectSecretCreate(BaseModel):
    key_name: str
    value: str
    environment: str = "preview"


class ProjectSecretKeyResponse(BaseModel):
    """Returned when listing secrets — value is never exposed."""
    id: str
    idea_id: str
    environment: str
    key_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectSecretValueResponse(BaseModel):
    """Returned when reading a single secret — includes decrypted value."""
    key_name: str
    environment: str
    value: str


class ProjectSecretListResponse(BaseModel):
    items: list[ProjectSecretKeyResponse]
    total: int
