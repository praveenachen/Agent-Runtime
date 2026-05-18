from redis import Redis
from rq import Queue

from app.core.config import get_settings


class QueueService:
    def __init__(self) -> None:
        settings = get_settings()
        self.redis = Redis.from_url(settings.redis_url)
        self.queue = Queue(settings.queue_name, connection=self.redis)

    def enqueue_job(self, job_id: str) -> str:
        rq_job = self.queue.enqueue("app.workers.worker.execute_job", job_id, job_timeout=300)
        return rq_job.id

