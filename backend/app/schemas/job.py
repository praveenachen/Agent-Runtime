from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.job import JobStatus
from app.schemas.workflows import WorkflowType


class JobCreate(BaseModel):
    workflow_type: WorkflowType
    input_payload: dict[str, Any]
    max_retries: int = Field(default=2, ge=0, le=5)


class JobLogRead(BaseModel):
    id: int
    level: str
    message: str
    created_at: datetime
    context: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class JobRead(BaseModel):
    id: str
    workflow_type: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    status: JobStatus
    error_message: str | None = None
    retry_count: int
    max_retries: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    latency_ms: int | None = None
    logs: list[JobLogRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class JobListItem(BaseModel):
    id: str
    workflow_type: str
    status: JobStatus
    retry_count: int
    max_retries: int
    created_at: datetime
    completed_at: datetime | None = None
    latency_ms: int | None = None

    model_config = {"from_attributes": True}

