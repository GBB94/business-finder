from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AgentTaskCreate(BaseModel):
    task_type: str
    priority: int = 0
    idempotency_key: Optional[str] = None
    input_params: Optional[dict] = None
    launch_id: Optional[str] = None
    agent_type: Optional[str] = None


class AgentTaskStepResponse(BaseModel):
    id: str
    task_id: str
    step_order: int
    step_name: str
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AgentTaskResponse(BaseModel):
    id: str
    idea_id: Optional[str] = None
    user_id: str
    task_type: str
    status: str
    priority: int
    idempotency_key: Optional[str] = None
    input_params: Optional[dict] = None
    output: Optional[dict] = None
    error_message: Optional[str] = None
    retry_count: int
    max_retries: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    steps: list[AgentTaskStepResponse] = []

    model_config = {"from_attributes": True}


class AgentTaskListResponse(BaseModel):
    items: list[AgentTaskResponse]
    total: int
