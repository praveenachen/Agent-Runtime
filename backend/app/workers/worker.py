from app.core.logging import configure_logging, get_logger
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.job import JobStatus
from app.services.job_service import JobService

configure_logging()
logger = get_logger(__name__)


def execute_job(job_id: str) -> None:
    init_db()
    with SessionLocal() as db:
        service = JobService(db)
        job = service.get_job(job_id)
        service.transition(job, JobStatus.running, "Worker picked up job")
        db.commit()
        logger.info(
            "Worker execution placeholder completed",
            extra={"job_id": job_id, "workflow_type": job.workflow_type, "status": JobStatus.running.value},
        )

