from app.models.job import Job, JobStatus
from app.services.metrics_service import MetricsService


def test_metrics_summary_counts_jobs(db_session) -> None:
    db_session.add_all(
        [
            Job(
                workflow_type="summarize_text",
                input_payload={"text": "a"},
                status=JobStatus.completed,
                latency_ms=100,
            ),
            Job(
                workflow_type="classify_message",
                input_payload={"message": "b"},
                status=JobStatus.failed,
                retry_count=1,
            ),
        ]
    )
    db_session.commit()

    summary = MetricsService(db_session).summary()

    assert summary["total_jobs"] == 2
    assert summary["completed_jobs"] == 1
    assert summary["failed_jobs"] == 1
    assert summary["total_retries"] == 1


def test_metrics_include_terminal_states_and_queue_latency(db_session):
    db_session.add_all(
        [
            Job(workflow_type="summarize_text", input_payload={}, status=JobStatus.cancelled),
            Job(
                workflow_type="summarize_text",
                input_payload={},
                status=JobStatus.timed_out,
                queue_latency_ms=100,
            ),
        ]
    )
    db_session.commit()
    service = MetricsService(db_session)
    assert service.summary()["cancelled_jobs"] == 1
    assert service.summary()["timed_out_jobs"] == 1
    assert 'agent_jobs_by_status{status="cancelled"} 1' in service.prometheus_text()
    assert 'agent_jobs_by_status{status="timed_out"} 1' in service.prometheus_text()
    assert "agent_job_queue_latency_seconds 0.1" in service.prometheus_text()
