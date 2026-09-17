from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.errors import ErrorCode
from app.models.job import JobStatus
from app.schemas.workflows import INPUT_MODELS, WorkflowType


class JobCreate(BaseModel):
    workflow_type: WorkflowType
    input_payload: dict[str, Any]
    max_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    idempotency_key: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[!-~]+$"
    )
    correlation_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[!-~]+$"
    )

    @model_validator(mode="after")
    def validate_input(self):
        self.input_payload = (
            INPUT_MODELS[self.workflow_type].model_validate(self.input_payload).model_dump()
        )
        return self


class ErrorRead(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool


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
    correlation_id: str
    idempotency_key: str | None = None
    error: ErrorRead | None = None
    attempt_count: int
    timeout_seconds: int
    queue_latency_ms: int | None = None
    next_attempt_at: datetime

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
