from app.core.logging import configure_logging, get_logger
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.job import JobStatus
from app.services.job_service import JobService
from app.services.queue_service import QueueService
from app.workflows import build_workflow_service

configure_logging()
logger = get_logger(__name__)


def execute_job(job_id: str) -> None:
    init_db()
    with SessionLocal() as db:
        service = JobService(db)
        job = service.get_job(job_id)
        service.transition(job, JobStatus.running, "Worker picked up job")
        db.commit()
        workflow_service = build_workflow_service()
        try:
            job.output_payload = workflow_service.execute(job.workflow_type, job.input_payload)
            job.error_message = None
            service.transition(job, JobStatus.completed, "Workflow completed")
            db.commit()
        except Exception as exc:
            if job.retry_count < job.max_retries:
                service.mark_for_retry(job, exc)
                db.commit()
                QueueService().enqueue_job(job.id)
                return
            job.error_message = str(exc)
            service.transition(job, JobStatus.failed, "Workflow failed after retries")
            service.add_log(job.id, "error", str(exc), {"error_type": exc.__class__.__name__})
            db.commit()
        logger.info(
            "Worker execution finished",
            extra={"job_id": job_id, "workflow_type": job.workflow_type, "status": job.status.value},
        )
