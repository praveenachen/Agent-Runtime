from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.job import Job, JobStatus


class MetricsService:
    def __init__(self, db: Session):
        self.db = db

    def summary(self) -> dict:
        total = self.db.scalar(select(func.count()).select_from(Job)) or 0
        completed = self._count_status(JobStatus.completed)
        failed = self._count_status(JobStatus.failed)
        queued = self._count_status(JobStatus.queued)
        running = self._count_status(JobStatus.running)
        avg_latency = self.db.scalar(select(func.avg(Job.latency_ms)).where(Job.latency_ms.is_not(None))) or 0
        retries = self.db.scalar(select(func.sum(Job.retry_count))) or 0
        success_rate = (completed / total * 100) if total else 0
        return {
            "total_jobs": total,
            "queued_jobs": queued,
            "running_jobs": running,
            "completed_jobs": completed,
            "failed_jobs": failed,
            "success_rate": round(success_rate, 2),
            "average_latency_ms": round(float(avg_latency), 2),
            "total_retries": int(retries),
        }

    def _count_status(self, status: JobStatus) -> int:
        return self.db.scalar(select(func.count()).select_from(Job).where(Job.status == status)) or 0

