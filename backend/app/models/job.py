from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.session import Base


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workflow_type: Mapped[str] = mapped_column(String(64), index=True)
    input_payload: Mapped[dict] = mapped_column(JSON)
    output_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128), default=lambda: str(uuid4()))
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    queue_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    demo_scenario: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    logs: Mapped[list["JobLog"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobLog.id"
    )


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    job: Mapped[Job] = relationship(back_populates="logs")
