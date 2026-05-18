from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.job import JobCreate, JobListItem, JobRead
from app.services.job_service import JobService
from app.services.queue_service import QueueService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=202)
def create_job(payload: JobCreate, db: Session = Depends(get_db)) -> JobRead:
    service = JobService(db)
    job = service.create_job(payload)
    rq_job_id = QueueService().enqueue_job(job.id)
    service.add_log(job.id, "info", "Job dispatched to Redis queue", {"rq_job_id": rq_job_id})
    db.commit()
    db.refresh(job)
    return JobRead.model_validate(job)


@router.get("", response_model=list[JobListItem])
def list_jobs(db: Session = Depends(get_db)) -> list[JobListItem]:
    jobs = JobService(db).list_jobs()
    return [JobListItem.model_validate(job) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobRead:
    job = JobService(db).get_job(job_id)
    return JobRead.model_validate(job)
