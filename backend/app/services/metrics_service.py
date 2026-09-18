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
        avg_latency = (
            self.db.scalar(select(func.avg(Job.latency_ms)).where(Job.latency_ms.is_not(None))) or 0
        )
        retries = self.db.scalar(select(func.sum(Job.retry_count))) or 0
        success_rate = (completed / total * 100) if total else 0
        return {
            "total_jobs": total,
            "queued_jobs": queued,
            "running_jobs": running,
            "completed_jobs": completed,
            "failed_jobs": failed,
            "cancelled_jobs": self._count_status(JobStatus.cancelled),
            "timed_out_jobs": self._count_status(JobStatus.timed_out),
            "average_queue_latency_ms": round(
                float(self.db.scalar(select(func.avg(Job.queue_latency_ms))) or 0), 2
            ),
            "success_rate": round(success_rate, 2),
            "average_latency_ms": round(float(avg_latency), 2),
            "total_retries": int(retries),
        }

    def _count_status(self, status: JobStatus) -> int:
        return (
            self.db.scalar(select(func.count()).select_from(Job).where(Job.status == status)) or 0
        )

    def prometheus_text(self) -> str:
        summary = self.summary()
        avg_latency_seconds = float(summary["average_latency_ms"]) / 1000
        lines = [
            "# HELP agent_jobs_total Total workflow jobs created.",
            "# TYPE agent_jobs_total gauge",
            f"agent_jobs_total {summary['total_jobs']}",
            "# HELP agent_jobs_completed_total Total workflow jobs completed.",
            "# TYPE agent_jobs_completed_total gauge",
            f"agent_jobs_completed_total {summary['completed_jobs']}",
            "# HELP agent_jobs_failed_total Total workflow jobs failed.",
            "# TYPE agent_jobs_failed_total gauge",
            f"agent_jobs_failed_total {summary['failed_jobs']}",
            "# HELP agent_job_retries_total Total workflow retries scheduled.",
            "# TYPE agent_job_retries_total gauge",
            f"agent_job_retries_total {summary['total_retries']}",
            "# HELP agent_job_latency_seconds Average most recent recorded attempt latency in seconds.",
            "# TYPE agent_job_latency_seconds gauge",
            f"agent_job_latency_seconds {avg_latency_seconds}",
            "# HELP agent_jobs_by_status Current jobs by status.",
            "# TYPE agent_jobs_by_status gauge",
            f'agent_jobs_by_status{{status="queued"}} {summary["queued_jobs"]}',
            f'agent_jobs_by_status{{status="running"}} {summary["running_jobs"]}',
            f'agent_jobs_by_status{{status="completed"}} {summary["completed_jobs"]}',
            f'agent_jobs_by_status{{status="failed"}} {summary["failed_jobs"]}',
        ]
        lines.extend(
            [
                f'agent_jobs_by_status{{status="cancelled"}} {summary["cancelled_jobs"]}',
                f'agent_jobs_by_status{{status="timed_out"}} {summary["timed_out_jobs"]}',
                "# HELP agent_job_queue_latency_seconds Average most recent attempt queue wait.",
                "# TYPE agent_job_queue_latency_seconds gauge",
                f"agent_job_queue_latency_seconds {summary['average_queue_latency_ms'] / 1000}",
            ]
        )
        return "\n".join(lines) + "\n"
