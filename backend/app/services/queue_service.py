from datetime import timedelta

from redis import Redis
from rq import Queue
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.job import Job, JobStatus

logger = get_logger(__name__)


class QueueService:
    def __init__(self) -> None:
        settings = get_settings()
        self.redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        self.queue = Queue(settings.queue_name, connection=self.redis)

    def enqueue_job(self, job_id: str, attempt: int, timeout: int) -> str:
        job = self.queue.enqueue(
            "app.workers.worker.execute_job",
            job_id,
            attempt,
            job_timeout=timeout,
            result_ttl=0,
            failure_ttl=86400,
        )
        return job.id

    def dispatch_pending(self, db: Session, job_id: str | None = None) -> int:
        """The DB is a durable outbox. Re-dispatch lost messages; worker claims are atomic."""
        settings = get_settings()
        now = utcnow()
        eligible = (
            Job.status == JobStatus.queued,
            Job.next_attempt_at <= now,
            or_(
                Job.last_dispatched_at.is_(None),
                Job.last_dispatched_at <= now - timedelta(seconds=settings.redispatch_seconds),
            ),
        )
        query = select(Job).where(*eligible).order_by(Job.next_attempt_at).limit(100)
        if job_id:
            query = query.where(Job.id == job_id)
        jobs = list(db.scalars(query))
        sent = 0
        for job in jobs:
            identity, attempt, timeout = job.id, job.attempt_count, job.timeout_seconds
            # Reserve briefly before network I/O. A crash at either side of enqueue recovers.
            result = db.execute(
                update(Job)
                .where(Job.id == identity, Job.attempt_count == attempt, *eligible)
                .values(last_dispatched_at=now)
            )
            db.commit()
            if result.rowcount != 1:
                continue
            try:
                self.enqueue_job(identity, attempt, timeout)
                sent += 1
            except Exception:
                # No raw Redis URL/credentials in logs. The DB record remains dispatchable.
                logger.warning(
                    "Queue unavailable; durable dispatch pending", extra={"execution_id": identity}
                )
        return sent
