from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from rq.timeouts import JobTimeoutException
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import sessionmaker

from app.ai.provider import MockAIProvider
from app.core.errors import ErrorCode, ExecutionError
from app.core.time import utcnow
from app.db.session import Base, get_db
from app.main import app
from app.models.job import Job, JobStatus
from app.schemas.job import JobCreate
from app.services.job_service import JobService
from app.services.queue_service import QueueService
from app.services.workflow_service import WorkflowService
from app.workers import worker
from app.workflows.summarize import summarize_text


@pytest.fixture()
def runtime(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, autoflush=False)
    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    def mock_service():
        service = WorkflowService(MockAIProvider())
        service.register("summarize_text", summarize_text)
        return service

    monkeypatch.setattr(worker, "build_workflow_service", mock_service)
    yield factory
    engine.dispose()


def submit(factory, **overrides):
    with factory() as db:
        job = JobService(db).create_job(
            JobCreate(
                workflow_type="summarize_text", input_payload={"text": "Hello world."}, **overrides
            )
        )
        return job.id


def read(factory, identity):
    with factory() as db:
        return JobService(db).get_job(identity)


def due(factory, identity):
    with factory() as db:
        db.execute(
            update(Job)
            .where(Job.id == identity)
            .values(next_attempt_at=utcnow() - timedelta(seconds=1))
        )
        db.commit()


def fail_provider(monkeypatch, error):
    def execute(*args):
        raise error

    monkeypatch.setattr(
        worker,
        "build_workflow_service",
        lambda: SimpleNamespace(provider=MockAIProvider(), execute=execute),
    )


def test_success_and_duplicate_delivery(runtime):
    identity = submit(runtime)
    worker.execute_job(identity, 0)
    worker.execute_job(identity, 0)
    job = read(runtime, identity)
    assert job.status == JobStatus.completed
    assert job.attempt_count == 1
    assert job.output_payload["summary"] == "Hello world."
    assert job.started_at and job.completed_at and job.queue_latency_ms is not None
    assert [log.message for log in job.logs] == [
        "Job queued",
        "Worker picked up job",
        "Attempt started",
        "Provider request started",
        "Provider response received",
        "Output validated",
        "Workflow completed",
    ]


@pytest.mark.parametrize(
    "code", [ErrorCode.unavailable, ErrorCode.rate_limited, ErrorCode.provider_timeout]
)
def test_retry_then_success(runtime, monkeypatch, code):
    identity = submit(runtime)
    builder = worker.build_workflow_service
    fail_provider(monkeypatch, ExecutionError(code))
    worker.execute_job(identity, 0)
    job = read(runtime, identity)
    assert job.status == JobStatus.queued and job.retry_count == 1
    assert job.error["code"] == code
    assert job.next_attempt_at > utcnow()
    worker.execute_job(identity, 1)  # backoff has not elapsed
    assert read(runtime, identity).attempt_count == 1
    due(runtime, identity)
    worker.execute_job(identity, 0)  # old queue message cannot consume a retry
    assert read(runtime, identity).attempt_count == 1
    monkeypatch.setattr(worker, "build_workflow_service", builder)
    worker.execute_job(identity, 1)
    job = read(runtime, identity)
    assert job.status == JobStatus.completed and job.attempt_count == 2
    assert job.error is None and job.error_message is None


def test_retry_exhaustion(runtime, monkeypatch):
    identity = submit(runtime, max_retries=2)
    fail_provider(monkeypatch, ExecutionError(ErrorCode.rate_limited))
    for attempt in range(3):
        due(runtime, identity)
        worker.execute_job(identity, attempt)
    job = read(runtime, identity)
    assert job.status == JobStatus.failed and job.retry_count == 2 and job.attempt_count == 3
    worker.execute_job(identity, 3)
    with runtime() as db, pytest.raises(HTTPException) as error:
        JobService(db).reset_failed_job_for_retry(identity)
    assert error.value.status_code == 409


def test_invalid_output_is_permanent_and_redacted(runtime, monkeypatch):
    class BadProvider(MockAIProvider):
        def generate_json(self, *args):
            return {"summary": {"secret": "sensitive prompt"}}

    service = WorkflowService(BadProvider())
    service.register("summarize_text", summarize_text)
    monkeypatch.setattr(worker, "build_workflow_service", lambda: service)
    identity = submit(runtime)
    worker.execute_job(identity)
    job = read(runtime, identity)
    assert job.status == JobStatus.failed and job.retry_count == 0
    assert job.error["code"] == "StructuredOutputInvalid"
    assert "sensitive" not in str(job.error) + str([log.context for log in job.logs])


def test_provider_initialization_failure_is_persisted(runtime, monkeypatch):
    def broken():
        raise RuntimeError("secret credential")

    monkeypatch.setattr(worker, "build_workflow_service", broken)
    identity = submit(runtime)
    worker.execute_job(identity)
    job = read(runtime, identity)
    assert job.status == JobStatus.failed and job.error["code"] == "InternalExecutionError"
    assert "secret" not in job.error_message


def test_concurrent_idempotency(runtime):
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(
            pool.map(
                lambda _: submit(runtime, idempotency_key="stable", correlation_id="trace"),
                range(8),
            )
        )
    assert len(set(ids)) == 1
    with runtime() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 1
        with pytest.raises(HTTPException) as error:
            JobService(db).create_job(
                JobCreate(
                    workflow_type="summarize_text",
                    input_payload={"text": "different"},
                    idempotency_key="stable",
                )
            )
        assert error.value.status_code == 409


def test_two_workers_only_one_claim(runtime):
    identity = submit(runtime)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: worker.execute_job(identity, 0), range(2)))
    assert read(runtime, identity).attempt_count == 1
    assert read(runtime, identity).status == JobStatus.completed


def test_cancel_queued_and_completed(runtime):
    identity = submit(runtime)
    with runtime() as db:
        assert JobService(db).cancel(identity).status == JobStatus.cancelled
        assert JobService(db).cancel(identity).status == JobStatus.cancelled
    worker.execute_job(identity)
    assert read(runtime, identity).attempt_count == 0
    completed = submit(runtime)
    worker.execute_job(completed)
    with runtime() as db:
        assert JobService(db).cancel(completed).status == JobStatus.completed


@pytest.mark.parametrize("failure", [False, True])
def test_cancel_running_wins_over_result_and_retry(runtime, monkeypatch, failure):
    identity = submit(runtime)

    def execute(*args):
        with runtime() as db:
            JobService(db).cancel(identity)
        if failure:
            raise ExecutionError(ErrorCode.unavailable)
        return {"summary": "late", "key_points": []}

    monkeypatch.setattr(
        worker,
        "build_workflow_service",
        lambda: SimpleNamespace(provider=MockAIProvider(), execute=execute),
    )
    worker.execute_job(identity)
    job = read(runtime, identity)
    assert job.status == JobStatus.cancelled and job.output_payload is None and job.retry_count == 0


def test_hard_timeout(runtime, monkeypatch):
    identity = submit(runtime)
    fail_provider(monkeypatch, JobTimeoutException("timeout"))
    worker.execute_job(identity)
    job = read(runtime, identity)
    assert job.status == JobStatus.timed_out and job.error["code"] == "ExecutionTimeout"
    assert job.retry_count == 0


def test_abandoned_worker_recovery_and_late_result(runtime):
    identity = submit(runtime)
    with runtime() as db:
        stale = JobService(db).claim(identity, 0)
        db.refresh(stale)
        db.expunge(stale)
    with runtime() as db:
        db.execute(
            update(Job)
            .where(Job.id == identity)
            .values(deadline_at=utcnow() - timedelta(seconds=1))
        )
        db.commit()
        assert JobService(db).recover_expired() == 1
        assert not JobService(db).finish(stale, output={"summary": "late"})
    assert read(runtime, identity).status == JobStatus.timed_out


def test_queue_failure_recovers_and_lost_message_redispatches(runtime, monkeypatch):
    identity = submit(runtime)
    calls = []

    def unavailable(*args):
        raise ConnectionError("redis://secret")

    monkeypatch.setattr(QueueService, "enqueue_job", unavailable)
    queue = QueueService()
    with runtime() as db:
        assert queue.dispatch_pending(db) == 0
    assert read(runtime, identity).status == JobStatus.queued
    monkeypatch.setattr(
        QueueService, "enqueue_job", lambda self, *args: calls.append(args) or "rq-id"
    )
    for _ in range(2):
        with runtime() as db:
            db.execute(update(Job).where(Job.id == identity).values(last_dispatched_at=None))
            db.commit()
            assert queue.dispatch_pending(db) == 1
    assert len(calls) == 2
    for job_id, attempt, _ in calls:
        worker.execute_job(job_id, attempt)
    assert read(runtime, identity).attempt_count == 1


@pytest.fixture()
def client(runtime, monkeypatch):
    def override_db():
        with runtime() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(QueueService, "enqueue_job", lambda *args: "fake-rq-id")
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_contract(client):
    body = {"workflow_type": "summarize_text", "input_payload": {"text": "hello"}}
    headers = {"Idempotency-Key": "request-1", "X-Correlation-ID": "trace-1"}
    first = client.post("/jobs", json=body, headers=headers)
    assert first.status_code == 202
    assert first.headers["x-correlation-id"] == "trace-1"
    identity = first.json()["id"]
    assert client.post("/jobs", json=body, headers=headers).json()["id"] == identity
    assert client.get(f"/jobs/{identity}").json()["status"] == "queued"
    assert client.post(f"/jobs/{identity}/cancel").json()["error"]["code"] == "ExecutionCancelled"
    assert client.get("/jobs/missing").status_code == 404
    assert client.get("/health").status_code == 200
    assert client.get("/jobs").json()[0]["id"] == identity
    body["input_payload"] = {"text": "changed"}
    assert client.post("/jobs", json=body, headers=headers).status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"workflow_type": "shell", "input_payload": {}},
        {"workflow_type": "summarize_text", "input_payload": {}},
        {"workflow_type": "summarize_text", "input_payload": {"text": ""}},
        {"workflow_type": "summarize_text", "input_payload": {"text": "a"}, "max_retries": 6},
        {"workflow_type": "summarize_text", "input_payload": {"text": "a"}, "timeout_seconds": 0},
    ],
)
def test_malformed_requests_never_queue(client, runtime, body):
    assert client.post("/jobs", json=body).status_code == 422
    with runtime() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 0


def test_cancellation_during_provider_initialization_stops_call(runtime, monkeypatch):
    identity = submit(runtime)

    def build():
        with runtime() as db:
            JobService(db).cancel(identity)

        def execute(*args):
            pytest.fail("Cancelled execution must not start provider work")

        return SimpleNamespace(provider=MockAIProvider(), execute=execute)

    monkeypatch.setattr(worker, "build_workflow_service", build)
    worker.execute_job(identity)
    assert read(runtime, identity).status == JobStatus.cancelled


def test_old_attempt_cannot_finish_new_running_attempt(runtime):
    identity = submit(runtime)
    with runtime() as db:
        service = JobService(db)
        first = service.claim(identity, 0)
        db.refresh(first)
        db.expunge(first)
        assert service.finish(first, error=ExecutionError(ErrorCode.unavailable))
    due(runtime, identity)
    with runtime() as db:
        service = JobService(db)
        assert service.claim(identity, 1)
        assert not service.finish(first, output={"summary": "stale"})
    assert read(runtime, identity).status == JobStatus.running
    assert read(runtime, identity).attempt_count == 2


def test_backoff_increases_and_is_capped(runtime, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "retry_base_seconds", 5)
    monkeypatch.setattr(settings, "retry_max_seconds", 8)
    identity = submit(runtime)
    fail_provider(monkeypatch, ExecutionError(ErrorCode.unavailable))
    for attempt, expected_delay in [(0, 5), (1, 8)]:
        due(runtime, identity)
        before = utcnow()
        worker.execute_job(identity, attempt)
        job = read(runtime, identity)
        assert (
            before + timedelta(seconds=expected_delay)
            <= job.next_attempt_at
            <= utcnow() + timedelta(seconds=expected_delay)
        )
        assert job.latency_ms is not None


def test_header_conflicts_and_body_identifiers(client):
    body = {
        "workflow_type": "summarize_text",
        "input_payload": {"text": "hello"},
        "idempotency_key": "body-key",
        "correlation_id": "body-trace",
    }
    assert client.post("/jobs", json=body, headers={"Idempotency-Key": "other"}).status_code == 422
    response = client.post("/jobs", json=body)
    assert response.status_code == 202
    assert response.json()["idempotency_key"] == "body-key"
    assert response.headers["x-correlation-id"] == "body-trace"


def test_api_accepts_durable_work_during_redis_outage(client, runtime, monkeypatch):
    def unavailable(*args):
        raise ConnectionError("secret")

    monkeypatch.setattr(QueueService, "enqueue_job", unavailable)
    body = {"workflow_type": "summarize_text", "input_payload": {"text": "hello"}}
    response = client.post("/jobs", json=body, headers={"Idempotency-Key": "outage"})
    assert response.status_code == 202
    assert read(runtime, response.json()["id"]).status == JobStatus.queued
    assert (
        client.post("/jobs", json=body, headers={"Idempotency-Key": "outage"}).json()["id"]
        == response.json()["id"]
    )


@pytest.mark.parametrize(
    "scenario,final_status,code",
    [
        ("normal", JobStatus.completed, None),
        ("permanent_failure", JobStatus.failed, "ValidationError"),
        ("malformed_output", JobStatus.failed, "StructuredOutputInvalid"),
    ],
)
def test_demo_scenarios(runtime, monkeypatch, scenario, final_status, code):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    identity = submit(runtime, demo_scenario=scenario)
    worker.execute_job(identity)
    job = read(runtime, identity)
    assert job.status == final_status
    assert (job.error or {}).get("code") == code
    assert job.provider_name == (
        "DemoMalformedOutput"
        if scenario == "malformed_output"
        else None
        if scenario == "permanent_failure"
        else "MockAIProvider"
    )
    if scenario == "malformed_output":
        assert "Provider response received" in [log.message for log in job.logs]
    monkeypatch.setattr(get_settings(), "demo_mode", False)


def test_demo_transient_retry(runtime, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    identity = submit(runtime, demo_scenario="transient_failure")
    worker.execute_job(identity, 0)
    first = read(runtime, identity)
    assert first.status == JobStatus.queued and first.retry_count == 1
    assert first.logs[-1].context["retry_delay_seconds"] > 0
    due(runtime, identity)
    worker.execute_job(identity, 1)
    job = read(runtime, identity)
    assert job.status == JobStatus.completed and job.attempt_count == 2
    assert job.retry_count == 1
    assert [log.message for log in job.logs] == [
        "Job queued",
        "Worker picked up job",
        "Attempt started",
        "Retryable transient failure",
        "Retry scheduled",
        "Worker picked up job",
        "Attempt started",
        "Provider request started",
        "Provider response received",
        "Output validated",
        "Workflow completed",
    ]
    assert job.logs[3].context["attempt"] == 1
    assert job.logs[3].context["error"]["code"] == "ProviderRateLimited"
    assert job.logs[4].context["retry_delay_seconds"] > 0
    assert job.logs[6].context["attempt"] == 2
    monkeypatch.setattr(get_settings(), "demo_mode", False)


def test_demo_slow_running_observable(runtime, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    identity = submit(runtime, demo_scenario="slow_execution")

    def observe(_seconds):
        assert read(runtime, identity).status == JobStatus.running

    monkeypatch.setattr(worker.time, "sleep", observe)
    worker.execute_job(identity)
    assert read(runtime, identity).status == JobStatus.completed
    monkeypatch.setattr(get_settings(), "demo_mode", False)


def test_demo_guard_and_reuse_event(client, runtime, monkeypatch):
    from app.core.config import get_settings

    body = {
        "workflow_type": "summarize_text",
        "input_payload": {"text": "hello"},
        "demo_scenario": "transient_failure",
    }
    assert client.post("/jobs", json=body).status_code == 422
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    first = client.post("/jobs", json=body, headers={"Idempotency-Key": "demo-key"})
    second = client.post("/jobs", json=body, headers={"Idempotency-Key": "demo-key"})
    assert first.json()["id"] == second.json()["id"]
    assert second.headers["x-idempotency-reused"] == "true"
    assert "Existing execution reused" in [
        log.message for log in read(runtime, first.json()["id"]).logs
    ]
    monkeypatch.setattr(get_settings(), "demo_mode", False)


def test_latency_breakdown_uses_first_queue_wait_and_latest_execution(runtime):
    identity = submit(runtime)
    worker.execute_job(identity)
    job = read(runtime, identity)
    queue_ms = (job.started_at - job.created_at).total_seconds() * 1000
    execution_ms = (job.completed_at - job.started_at).total_seconds() * 1000
    total_ms = (job.completed_at - job.created_at).total_seconds() * 1000
    assert abs(job.queue_latency_ms - queue_ms) < 2
    assert abs(job.latency_ms - execution_ms) < 2
    assert abs(total_ms - queue_ms - execution_ms) < 0.01


def test_demo_disabled_in_production_even_if_flag_set(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    monkeypatch.setattr(get_settings(), "environment", "production")
    body = {
        "workflow_type": "summarize_text",
        "input_payload": {"text": "hello"},
        "demo_scenario": "normal",
    }
    assert client.get("/runtime-config").json() == {"demo_mode": False}
    assert client.post("/jobs", json=body).status_code == 422


def test_idempotency_normalizes_defaults_and_scenario(client, runtime, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    body = {"workflow_type": "summarize_text", "input_payload": {"text": "same"}}
    headers = {"Idempotency-Key": "normalized-key"}
    first = client.post("/jobs", json=body, headers=headers)
    equivalent = {
        **body,
        "max_retries": 2,
        "timeout_seconds": 300,
        "demo_scenario": "normal",
        "correlation_id": "another-trace",
    }
    second = client.post("/jobs", json=equivalent, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert second.headers["x-idempotency-reused"] == "true"
    with runtime() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"input_payload": {"text": "different"}},
        {"workflow_type": "extract_structured_data"},
        {"demo_scenario": "transient_failure"},
        {"max_retries": 3},
        {"timeout_seconds": 301},
    ],
)
def test_idempotency_rejects_changed_logical_request(client, runtime, monkeypatch, change):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    body = {"workflow_type": "summarize_text", "input_payload": {"text": "same"}}
    headers = {"Idempotency-Key": "conflict-key"}
    first = client.post("/jobs", json=body, headers=headers)
    assert first.status_code == 202
    assert client.post("/jobs", json={**body, **change}, headers=headers).status_code == 409
    with runtime() as db:
        assert db.scalar(select(func.count()).select_from(Job)) == 1


def test_duplicate_request_never_enqueues_second_execution(client, runtime, monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        QueueService, "enqueue_job", lambda self, *args: dispatched.append(args) or "rq-id"
    )
    body = {"workflow_type": "summarize_text", "input_payload": {"text": "same"}}
    headers = {"Idempotency-Key": "one-delivery"}
    first = client.post("/jobs", json=body, headers=headers)
    second = client.post("/jobs", json=body, headers=headers)
    assert first.json()["id"] == second.json()["id"]
    assert len(dispatched) == 1
    worker.execute_job(first.json()["id"])
    assert read(runtime, first.json()["id"]).attempt_count == 1


def test_transient_demo_without_manual_key(client, runtime, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    body = {
        "workflow_type": "summarize_text",
        "input_payload": {"text": "retry"},
        "demo_scenario": "transient_failure",
    }
    response = client.post("/jobs", json=body)
    assert response.status_code == 202
    identity = response.json()["id"]
    assert response.json()["idempotency_key"] is None
    worker.execute_job(identity, 0)
    assert read(runtime, identity).status == JobStatus.queued
    due(runtime, identity)
    worker.execute_job(identity, 1)
    assert read(runtime, identity).status == JobStatus.completed
