import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import ErrorCode, ExecutionError
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.job import Job, JobLog, JobStatus
from app.schemas.job import JobCreate

logger = get_logger(__name__)
TERMINAL = {JobStatus.completed, JobStatus.failed, JobStatus.cancelled, JobStatus.timed_out}
ALLOWED = {
    JobStatus.queued: {JobStatus.running, JobStatus.cancelled},
    JobStatus.running: TERMINAL | {JobStatus.queued},
    JobStatus.failed: {JobStatus.queued},
}


class JobService:
    def __init__(self, db: Session):
        self.db = db

    def create_job(self, payload: JobCreate) -> Job:
        canonical = payload.model_dump(exclude={"idempotency_key", "correlation_id"}, mode="json")
        fingerprint = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if payload.idempotency_key:
            existing = self.db.scalar(
                select(Job).where(Job.idempotency_key == payload.idempotency_key)
            )
            if existing:
                return self._same_request(existing, fingerprint)
        job = Job(
            workflow_type=payload.workflow_type.value,
            input_payload=payload.input_payload,
            max_retries=payload.max_retries,
            timeout_seconds=payload.timeout_seconds,
            idempotency_key=payload.idempotency_key,
            correlation_id=payload.correlation_id or str(uuid4()),
            request_hash=fingerprint,
            status=JobStatus.queued,
        )
        try:
            self.db.add(job)
            self.db.flush()
            self.add_log(job.id, "info", "Job queued", self.context(job))
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = (
                self.db.scalar(select(Job).where(Job.idempotency_key == payload.idempotency_key))
                if payload.idempotency_key
                else None
            )
            if not existing:
                raise
            return self._same_request(existing, fingerprint)
        self.db.refresh(job)
        return job

    @staticmethod
    def _same_request(job: Job, fingerprint: str) -> Job:
        if job.request_hash != fingerprint:
            raise HTTPException(409, "Idempotency key already used for a different request")
        return job

    def list_jobs(self) -> list[Job]:
        return list(self.db.scalars(select(Job).order_by(desc(Job.created_at)).limit(100)))

    def get_job(self, job_id: str) -> Job:
        job = self.db.scalar(
            select(Job)
            .options(selectinload(Job.logs))
            .where(Job.id == job_id)
            .execution_options(populate_existing=True)
        )
        if not job:
            raise HTTPException(404, "Job not found")
        return job

    def add_log(self, job_id: str, level: str, message: str, context: dict | None = None) -> None:
        self.db.add(JobLog(job_id=job_id, level=level, message=message, context=context))

    @staticmethod
    def context(job: Job) -> dict:
        return {
            "execution_id": job.id,
            "correlation_id": job.correlation_id,
            "status": job.status.value,
            "attempt": job.attempt_count,
            "handler": job.workflow_type,
            "latency_ms": job.latency_ms,
            "queue_latency_ms": job.queue_latency_ms,
            "error_code": (job.error or {}).get("code"),
            "retry_count": job.retry_count,
            "next_attempt_at": job.next_attempt_at.isoformat(),
        }

    def transition(
        self,
        job: Job,
        status: JobStatus,
        message: str,
        *,
        values: dict | None = None,
        conditions: tuple = (),
    ) -> bool:
        """Compare-and-swap status AND attempt: stale workers cannot overwrite a newer state."""
        if status not in ALLOWED.get(job.status, set()):
            return False
        now = utcnow()
        changes = dict(values or {})
        changes["status"] = status
        if status in TERMINAL:
            changes.update(completed_at=now, deadline_at=None)
        if job.status == JobStatus.running and job.started_at:
            changes["latency_ms"] = max(0, int((now - job.started_at).total_seconds() * 1000))
        result = self.db.execute(
            update(Job)
            .where(
                Job.id == job.id,
                Job.status == job.status,
                Job.attempt_count == job.attempt_count,
                *conditions,
            )
            .values(**changes)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.db.rollback()
            return False
        current = self.db.get(Job, job.id, populate_existing=True)
        context = self.context(current)
        self.add_log(job.id, "info", message, context)
        self.db.commit()
        logger.info(message, extra=context)
        return True

    def claim(self, job_id: str, expected_attempt: int) -> Job | None:
        job = self.get_job(job_id)
        now = utcnow()
        if (
            job.status != JobStatus.queued
            or job.attempt_count != expected_attempt
            or job.next_attempt_at > now
        ):
            self.db.rollback()
            return None
        claimed = self.transition(
            job,
            JobStatus.running,
            "Worker picked up job",
            values={
                "attempt_count": expected_attempt + 1,
                "started_at": now,
                "deadline_at": now + timedelta(seconds=job.timeout_seconds),
                "queue_latency_ms": max(0, int((now - job.next_attempt_at).total_seconds() * 1000)),
                "error": None,
                "error_message": None,
                "latency_ms": None,
            },
            conditions=(Job.next_attempt_at <= now,),
        )
        return job if claimed else None

    def finish(
        self, job: Job, output: dict | None = None, error: ExecutionError | None = None
    ) -> bool:
        # Keep the claimed attempt on this object; do not refresh it before the CAS.
        now = utcnow()
        if job.deadline_at and now >= job.deadline_at:
            error = ExecutionError(ErrorCode.execution_timeout)
        if error is None:
            return self.transition(
                job,
                JobStatus.completed,
                "Workflow completed",
                values={"output_payload": output, "error": None, "error_message": None},
            )
        values = {"error": error.as_dict(), "error_message": str(error), "output_payload": None}
        if error.retryable and job.retry_count < job.max_retries:
            settings = get_settings()
            delay = min(
                settings.retry_max_seconds, settings.retry_base_seconds * 2**job.retry_count
            )
            values.update(
                retry_count=job.retry_count + 1,
                next_attempt_at=now + timedelta(seconds=delay),
                last_dispatched_at=None,
                deadline_at=None,
            )
            return self.transition(
                job, JobStatus.queued, "Transient failure; retry scheduled", values=values
            )
        status = (
            JobStatus.timed_out if error.code == ErrorCode.execution_timeout else JobStatus.failed
        )
        return self.transition(job, status, "Workflow failed", values=values)

    def is_active(self, job: Job) -> bool:
        status = self.db.scalar(
            select(Job.status).where(Job.id == job.id, Job.attempt_count == job.attempt_count)
        )
        self.db.rollback()
        return status == JobStatus.running

    def cancel(self, job_id: str) -> Job:
        for _ in range(3):
            job = self.get_job(job_id)
            if job.status in TERMINAL:
                return job
            error = ExecutionError(ErrorCode.cancelled)
            if self.transition(
                job,
                JobStatus.cancelled,
                "Cancellation accepted",
                values={"error": error.as_dict(), "error_message": str(error)},
            ):
                return self.get_job(job_id)
        raise HTTPException(409, "Job state changed; retry cancellation")

    def reset_failed_job_for_retry(self, job_id: str) -> Job:
        job = self.get_job(job_id)
        if (
            job.status != JobStatus.failed
            or not (job.error or {}).get("retryable")
            or job.retry_count >= job.max_retries
        ):
            raise HTTPException(
                409,
                "Job is not eligible for retry; retry budget and permanent failures are preserved",
            )
        if not self.transition(
            job,
            JobStatus.queued,
            "Manual retry queued",
            values={
                "retry_count": job.retry_count + 1,
                "next_attempt_at": utcnow(),
                "last_dispatched_at": None,
                "completed_at": None,
                "latency_ms": None,
                "error": None,
                "error_message": None,
                "output_payload": None,
            },
        ):
            raise HTTPException(409, "Job state changed")
        return self.get_job(job_id)

    def recover_expired(self) -> int:
        jobs = list(
            self.db.scalars(
                select(Job).where(Job.status == JobStatus.running, Job.deadline_at <= utcnow())
            )
        )
        # Preserve the selected attempt snapshots across commits inside finish().
        self.db.expunge_all()
        self.db.rollback()
        count = 0
        for job in jobs:
            count += self.finish(job, error=ExecutionError(ErrorCode.execution_timeout))
        return count
