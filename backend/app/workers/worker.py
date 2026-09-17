from pydantic import ValidationError
from rq.timeouts import JobTimeoutException

from app.core.errors import ErrorCode, ExecutionError
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.models.job import JobStatus
from app.services.job_service import JobService
from app.workflows import build_workflow_service

logger = get_logger(__name__)


def execute_job(job_id: str, expected_attempt: int = 0) -> None:
    configure_logging()
    with SessionLocal() as db:
        service = JobService(db)
        job = service.claim(job_id, expected_attempt)
        if job is None:
            return
        # Retain an immutable claim snapshot without a DB transaction during network I/O.
        db.refresh(job)
        if job.status != JobStatus.running or job.attempt_count != expected_attempt + 1:
            return
        db.expunge(job)
        db.rollback()
        try:
            workflow_service = build_workflow_service()
            if not service.is_active(job):
                return
            logger.info(
                "Provider execution started",
                extra={
                    **service.context(job),
                    "provider": type(workflow_service.provider).__name__,
                },
            )
            output = workflow_service.execute(job.workflow_type, job.input_payload)
        except JobTimeoutException:
            service.finish(job, error=ExecutionError(ErrorCode.execution_timeout))
        except ExecutionError as error:
            service.finish(job, error=error)
        except ValidationError:
            service.finish(job, error=ExecutionError(ErrorCode.structured_output))
        except Exception as exc:
            logger.error(
                "Unexpected execution failure",
                extra={**service.context(job), "exception_type": type(exc).__name__},
            )
            service.finish(job, error=ExecutionError(ErrorCode.internal))
        else:
            service.finish(job, output=output)
