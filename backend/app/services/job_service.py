from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.core.logging import get_logger
from app.models.job import Job, JobLog, JobStatus
from app.schemas.job import JobCreate

logger = get_logger(__name__)


class JobService:
    def __init__(self, db: Session):
        self.db = db

    def create_job(self, payload: JobCreate) -> Job:
        job = Job(
            workflow_type=payload.workflow_type.value,
            input_payload=payload.input_payload,
            max_retries=payload.max_retries,
            status=JobStatus.queued,
        )
        self.db.add(job)
        self.db.flush()
        self.add_log(job.id, "info", "Job queued", {"status": JobStatus.queued.value})
        self.db.commit()
        self.db.refresh(job)
        return job

    def list_jobs(self) -> list[Job]:
        statement = select(Job).order_by(desc(Job.created_at)).limit(100)
        return list(self.db.scalars(statement).all())

    def get_job(self, job_id: str) -> Job:
        statement = select(Job).options(selectinload(Job.logs)).where(Job.id == job_id)
        job = self.db.scalars(statement).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    def add_log(self, job_id: str, level: str, message: str, context: dict | None = None) -> None:
        self.db.add(JobLog(job_id=job_id, level=level, message=message, context=context))

    def transition(self, job: Job, status: JobStatus, message: str) -> None:
        job.status = status
        if status == JobStatus.running:
            job.started_at = datetime.utcnow()
        if status in {JobStatus.completed, JobStatus.failed}:
            job.completed_at = datetime.utcnow()
            if job.started_at:
                job.latency_ms = int((job.completed_at - job.started_at).total_seconds() * 1000)
        self.add_log(job.id, "info", message, {"status": status.value})
        logger.info(
            message,
            extra={"job_id": job.id, "workflow_type": job.workflow_type, "status": status.value},
        )

    def mark_for_retry(self, job: Job, error: Exception) -> None:
        job.retry_count += 1
        job.status = JobStatus.queued
        job.error_message = str(error)
        self.add_log(
            job.id,
            "warning",
            "Workflow failed; retry queued",
            {"retry_count": job.retry_count, "max_retries": job.max_retries, "error": str(error)},
        )

    def reset_failed_job_for_retry(self, job_id: str) -> Job:
        job = self.get_job(job_id)
        if job.status != JobStatus.failed:
            raise HTTPException(status_code=409, detail="Only failed jobs can be retried")
        job.status = JobStatus.queued
        job.retry_count = 0
        job.output_payload = None
        job.error_message = None
        job.started_at = None
        job.completed_at = None
        job.latency_ms = None
        self.add_log(job.id, "info", "Manual retry queued", {"status": JobStatus.queued.value})
        self.db.commit()
        self.db.refresh(job)
        return job
