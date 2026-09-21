from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.job import JobCreate, JobListItem, JobRead
from app.services.job_service import JobService
from app.services.queue_service import QueueService

router = APIRouter(prefix="/jobs", tags=["jobs"])
Identifier = Annotated[str | None, Header(min_length=1, max_length=128, pattern=r"^[!-~]+$")]


@router.post("", response_model=JobRead, status_code=202)
def create_job(
    payload: JobCreate,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: Identifier = None,
    x_correlation_id: Identifier = None,
) -> JobRead:
    for field, header in (
        ("idempotency_key", idempotency_key),
        ("correlation_id", x_correlation_id),
    ):
        if header is not None:
            if getattr(payload, field) not in (None, header):
                raise HTTPException(422, f"Conflicting {field} in header and body")
            setattr(payload, field, header)
    service = JobService(db)
    job = service.create_job(payload)
    identity = job.id
    QueueService().dispatch_pending(db, identity)
    job = service.get_job(identity)
    response.headers["X-Correlation-ID"] = job.correlation_id
    response.headers["Location"] = f"/jobs/{identity}"
    response.headers["X-Idempotency-Reused"] = str(service.reused).lower()
    return JobRead.model_validate(job)


@router.get("", response_model=list[JobListItem])
def list_jobs(db: Session = Depends(get_db)) -> list[JobListItem]:
    return [JobListItem.model_validate(job) for job in JobService(db).list_jobs()]


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, response: Response, db: Session = Depends(get_db)) -> JobRead:
    job = JobService(db).get_job(job_id)
    response.headers["X-Correlation-ID"] = job.correlation_id
    return JobRead.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: str, db: Session = Depends(get_db)) -> JobRead:
    return JobRead.model_validate(JobService(db).cancel(job_id))


@router.post("/{job_id}/retry", response_model=JobRead, status_code=202)
def retry_job(job_id: str, db: Session = Depends(get_db)) -> JobRead:
    service = JobService(db)
    job = service.reset_failed_job_for_retry(job_id)
    QueueService().dispatch_pending(db, job.id)
    return JobRead.model_validate(service.get_job(job_id))
