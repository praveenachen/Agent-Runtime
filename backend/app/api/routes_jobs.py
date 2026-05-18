from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.job import JobCreate, JobListItem, JobRead
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=202)
def create_job(payload: JobCreate, db: Session = Depends(get_db)) -> JobRead:
    job = JobService(db).create_job(payload)
    return JobRead.model_validate(job)


@router.get("", response_model=list[JobListItem])
def list_jobs(db: Session = Depends(get_db)) -> list[JobListItem]:
    jobs = JobService(db).list_jobs()
    return [JobListItem.model_validate(job) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobRead:
    job = JobService(db).get_job(job_id)
    return JobRead.model_validate(job)

