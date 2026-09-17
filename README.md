# Agent Runtime

Agent Runtime is reliable execution infrastructure for AI workflows. It queues, executes, validates, retries, and inspects domain-agnostic work behind a typed API.

The app lets a user submit structured AI workflow jobs through an API or dashboard. Jobs are persisted, pushed to a Redis-backed queue, executed asynchronously by a worker, validated with Pydantic, retried on failure, and surfaced through operational metrics and execution logs.

## Why This Matters

Modern AI products need more than a prompt box. Production teams need infrastructure that can run AI work reliably: structured inputs, schema-validated outputs, retries, latency tracking, execution history, failure visibility, and provider boundaries. Agent Runtime is a focused MVP of that infrastructure.

## Architecture

```text
React dashboard / API client
          |
          v
FastAPI service ---- SQLite database
          |              ^
          v              |
      Redis queue ---- RQ worker
                         |
                         v
              Workflow service
                         |
                         v
       AI provider interface -> OpenAI or mock provider
                         |
                         v
              Pydantic output validation
```

## System Flow

1. `POST /jobs` creates a job record with `queued` status.
2. The API dispatches the job ID to Redis through RQ.
3. A worker picks up the job and marks it `running`.
4. The workflow service routes execution by `workflow_type`.
5. The AI provider returns JSON output.
6. Pydantic validates the workflow-specific response schema.
7. The worker stores output, logs status transitions, records latency, and marks the job `completed`.
8. Transient provider failures schedule bounded exponential retries in SQLite. Permanent validation failures fail immediately. A dispatcher delivers due work and expires abandoned runs.
9. The dashboard polls for job status, metrics, logs, output, and retry controls.

## Tech Stack

- Backend: FastAPI, SQLAlchemy, Pydantic
- Queue: Redis + RQ
- Database: SQLite for local MVP
- AI: OpenAI API behind a modular provider interface, with mock fallback
- Observability: structured JSON logs, persisted job logs, Prometheus-compatible metrics
- Frontend: React, Vite, TypeScript
- Deployment: Docker and Docker Compose

## Features

- Submit asynchronous AI workflow jobs
- List and inspect workflow executions
- Track status transitions: `queued`, `running`, `completed`, `failed`, `cancelled`, `timed_out`
- Validate structured LLM outputs with Pydantic
- Retry failed workflow executions automatically and manually
- Persist input, output, errors, timestamps, latency, retry counts, and logs
- View metrics summary cards in the dashboard
- Expose Prometheus-compatible metrics at `/metrics`
- Run locally with or without an OpenAI API key

## Workflow Types

### `summarize_text`

Input:

```json
{ "text": "Long text to summarize..." }
```

Output:

```json
{
  "summary": "Concise summary",
  "key_points": ["Point one", "Point two"]
}
```

### `extract_structured_data`

Input:

```json
{ "text": "Customer Acme needs follow-up by Friday..." }
```

Output:

```json
{
  "title": "Customer follow-up",
  "entities": [{ "name": "Acme", "type": "company", "value": null }],
  "dates": ["Friday"],
  "action_items": ["Follow up with customer"]
}
```

### `classify_message`

Input:

```json
{ "message": "The production job failed again and needs attention." }
```

Output:

```json
{
  "category": "incident",
  "priority": "high",
  "sentiment": "negative",
  "confidence": 0.91
}
```

## API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/jobs` | Submit a workflow job |
| `GET` | `/jobs` | List recent jobs |
| `GET` | `/jobs/{job_id}` | Retrieve job status, payloads, logs, errors, and timestamps |
| `POST` | `/jobs/{job_id}/retry` | Retry an eligible transient failure within its remaining budget |
| `POST` | `/jobs/{job_id}/cancel` | Cancel queued/running work; terminal jobs are returned unchanged |
| `GET` | `/metrics-summary` | Return workflow analytics for the dashboard |
| `GET` | `/metrics` | Return Prometheus-compatible metrics |
| `GET` | `/health` | Health check |

Example request:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_type": "summarize_text",
    "input_payload": {
      "text": "Agent Runtime queues and executes AI workflows asynchronously."
    },
    "max_retries": 2
  }'
```

## Run Locally

Copy the environment template:

```bash
cp .env.example .env
```

The app works without `OPENAI_API_KEY`; it uses a deterministic mock provider for demo mode. Add an OpenAI key to `.env` to call the real provider.

Start the full stack:

```bash
docker compose up --build
```

Open:

- Dashboard: http://localhost:5173
- API docs: http://localhost:8000/docs
- Metrics: http://localhost:8000/metrics

## Local Development Without Docker

Backend:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
REDIS_URL=redis://localhost:6379/0 uvicorn app.main:app --reload
```

Worker:

```bash
cd backend
rq worker agent-runtime --url redis://localhost:6379/0
```

Dispatcher (required for retries, queue recovery, and abandoned-worker recovery):

```bash
cd backend
REDIS_URL=redis://localhost:6379/0 python -m app.workers.dispatcher
```

Run the API once before starting workers to initialize/upgrade the SQLite schema. All three processes must use the same database path and Redis URL.

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Observability

Agent Runtime records observability signals at the workflow level:

- Job status transitions
- Structured per-job logs
- Error messages and validation failures
- Retry counts and retry log entries
- Start/completion timestamps
- Latency in milliseconds
- Dashboard summary analytics
- Prometheus-compatible metrics:
  - `agent_jobs_total`
  - `agent_jobs_completed_total`
  - `agent_jobs_failed_total`
  - `agent_job_latency_seconds`
  - `agent_job_retries_total`

## Execution guarantees and limits

- **State:** `queued → running → completed` (`completed` is the existing success spelling). Cancellation, permanent failure, or timeout are terminal. Conditional updates match both status and attempt number, so duplicate messages and stale workers cannot overwrite newer state. `attempt_count` counts started attempts; `retry_count` counts scheduled retries and is never reset by manual retry.
- **Retry policy:** at most `1 + max_retries` attempts (default 3, maximum 6). Only provider connection/5xx failures, rate limits, and provider timeouts retry. Delay is `min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * 2 ** retry_count)` before incrementing the count; defaults are 60 and 5 seconds. SDK retries are disabled. Invalid requests/output, cancellation, execution timeout, and unexpected internal errors do not auto-retry.
- **Durability:** SQLite is the source of truth on the shared local disk. Queued rows also act as a durable outbox: the dispatcher scans due work every 2 seconds, with a 30-second resend lease. Redis failures or a crash between persistence and enqueue leave recoverable work. Redis AOF is enabled in Compose. Atomic worker claims make duplicate queue deliveries harmless. The API still returns 202 when Redis is unavailable because it has durably accepted the work.
- **Worker failure:** RQ enforces each attempt's execution timeout. The dispatcher marks a running job `timed_out` after its persisted deadline if a worker is killed or disappears. Recovery may lag by the dispatcher interval or its downtime. Unknown external outcomes are not automatically replayed after execution timeout. A live worker's late result is discarded.
- **Timeouts:** HTTP client/network timeout does not cancel accepted work. Queue wait is measured separately and has no expiry in this phase. `timeout_seconds` (1–3600, default 300) applies per execution attempt; `PROVIDER_TIMEOUT_SECONDS` defaults to 60. A client that loses the submission response should resubmit with the same idempotency key.
- **Cancellation:** `POST /jobs/{id}/cancel` atomically cancels queued or running work, preventing future attempts and result publication. In-flight provider calls are not forcibly interrupted and may still incur charges or complete external side effects. Completed/failed/timed-out jobs remain unchanged. Repeated cancellation is safe.
- **Idempotency:** send a caller-owned `Idempotency-Key` header (or `idempotency_key` body field), reused across HTTP retries. Identical validated requests return the same job; changed input, retry budget, or timeout with the same key returns 409. Keys are unique across this single-service database and retained with job history. Omitted keys create independent jobs. The dashboard retains a key across failed submission attempts for unchanged input within the current page session; reloads do not retain it.
- **External effects:** submission deduplication is not an exactly-once guarantee for external systems. A provider timeout may have an unknown external outcome; retries can repeat a provider call. Future side-effecting handlers must propagate a stable operation key to downstream systems that support idempotency, or avoid retrying ambiguous outcomes.

SQLite is appropriate for this single-host deployment with short transactions and a modest worker count. API, workers, and dispatcher share a persisted volume. Startup applies an additive, serialized SQLite migration that preserves existing history; back up the database and stop older processes before upgrading. Do not share this file over a network filesystem. RQ/Redis provides process isolation and hard attempt timeouts without replacing the existing queue stack. Multi-host deployment and high write concurrency are outside this configuration's scope.

Logs include execution/correlation IDs, handler, attempt, status, queue/run latency, and safe error codes. Provider start logs name the adapter. Raw SDK exceptions, prompts, API keys, and validation inputs are not logged. API errors retain the existing `error_message` field and add typed `error: {code, message, retryable}`. Prometheus values are database snapshot **gauges**, including the legacy metric names ending in `_total`; counts can decrease if history is removed or a database is restored. Latency metrics describe each job's most recent attempt, not a cumulative histogram.

## API compatibility and security

Existing `/jobs` routes, workflow names, response fields, and `completed` status remain. Additions include cancellation, `attempt_count`, `timeout_seconds`, `idempotency_key`, `correlation_id`, `queue_latency_ms`, `next_attempt_at`, and typed `error`. `X-Correlation-ID` can be supplied as a header or `correlation_id` in the body; it is returned on submit/status responses. A missing correlation ID is generated once. Conflicting header/body identifiers return 422. Workflow input is now validated before queueing (422), and retry budgets cannot be reset through the manual retry endpoint.

Relay 2.0's `RuntimeClient` / `AgentRuntimeHttpClient` sources are not present in this repository. The existing runtime contract is preserved, but end-to-end Relay compatibility cannot be certified without those client definitions. No Relay code or domain-specific routes were added.

There is no built-in service authentication or tenant isolation. Compose binds API/dashboard ports to localhost and leaves Redis internal. For remote deployment, require authentication and TLS at a trusted gateway; do not expose the unauthenticated API directly. Provider secrets stay in backend/worker environment variables and never enter dashboard configuration. Handlers are selected from the existing explicit registry; request data cannot select arbitrary Python imports or commands. `/health` is a liveness check, not a Redis/worker readiness guarantee.

## Validation

From the repository root, with backend development dependencies installed:

```bash
python -m pytest -q
ruff check backend
ruff format --check backend
cd frontend && npm ci && npm run build
```

Tests use fake providers and queue delivery stubs; no real AI credentials or external AI calls are needed. They cover lifecycle, concurrency, idempotency conflicts, retries/backoff, provider normalization, invalid output, cancellation races, timeout/recovery, migration, and the HTTP contract. Backend type checking is not configured; the frontend build runs TypeScript checking. A real Redis/RQ/Docker smoke test remains a separate deployment check.

## Future Improvements

- Authentication for dashboard/API access
- Workflow versioning
- Dead-letter queue view
- Streaming worker logs
- OpenTelemetry traces
- More workflow types with multi-step orchestration
- Provider selection per workflow

