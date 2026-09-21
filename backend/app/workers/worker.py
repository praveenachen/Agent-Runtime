import time

from pydantic import ValidationError
from rq.timeouts import JobTimeoutException
from sqlalchemy import update

from app.ai.provider import AIProvider
from app.core.config import get_settings
from app.core.errors import ErrorCode, ExecutionError
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.models.job import Job, JobStatus
from app.services.job_service import JobService
from app.workflows import build_workflow_service

logger = get_logger(__name__)


class ObservedProvider(AIProvider):
    def __init__(self, provider: AIProvider, service: JobService, job: Job):
        self.provider = provider
        self.service = service
        self.job = job

    def generate_json(self, system_prompt: str, user_payload: dict) -> dict:
        self.service.event(self.job, "Provider request started")
        started = time.monotonic()
        if get_settings().demo_enabled and self.job.demo_scenario == "slow_execution":
            time.sleep(10)
        if get_settings().demo_enabled and self.job.demo_scenario == "malformed_output":
            result = {}
        else:
            result = self.provider.generate_json(system_prompt, user_payload)
        self.service.event(
            self.job,
            "Provider response received",
            {"provider_latency_ms": round((time.monotonic() - started) * 1000)},
        )
        return result


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
            provider = workflow_service.provider
            provider_name = type(provider).__name__
            model_name = getattr(provider, "model", None)
            if (
                get_settings().demo_enabled
                and job.demo_scenario == "transient_failure"
                and job.attempt_count == 1
            ):
                raise ExecutionError(ErrorCode.rate_limited)
            if get_settings().demo_enabled and job.demo_scenario == "permanent_failure":
                raise ExecutionError(ErrorCode.validation)
            if get_settings().demo_enabled and job.demo_scenario == "malformed_output":
                provider_name, model_name = "DemoMalformedOutput", None
            db.execute(
                update(Job)
                .where(
                    Job.id == job.id,
                    Job.status == JobStatus.running,
                    Job.attempt_count == job.attempt_count,
                )
                .values(provider_name=provider_name, model_name=model_name)
            )
            db.commit()
            workflow_service.provider = ObservedProvider(provider, service, job)
            logger.info(
                "Provider execution started",
                extra={
                    **service.context(job),
                    "provider": provider_name,
                },
            )
            output = workflow_service.execute(job.workflow_type, job.input_payload)
            service.event(job, "Output validated")
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
