from app.models.job import Job, JobStatus
from app.services.metrics_service import MetricsService


def test_metrics_summary_counts_jobs(db_session) -> None:
    db_session.add_all(
        [
            Job(workflow_type="summarize_text", input_payload={"text": "a"}, status=JobStatus.completed, latency_ms=100),
            Job(workflow_type="classify_message", input_payload={"message": "b"}, status=JobStatus.failed, retry_count=1),
        ]
    )
    db_session.commit()

    summary = MetricsService(db_session).summary()

    assert summary["total_jobs"] == 2
    assert summary["completed_jobs"] == 1
    assert summary["failed_jobs"] == 1
    assert summary["total_retries"] == 1

