# Agent Runtime

Agent Runtime is a production-style AI workflow orchestration platform. It demonstrates how backend systems can queue, execute, validate, retry, observe, and inspect LLM-powered work without turning the product into a generic chatbot.

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
8. If execution or validation fails, the worker retries until `max_retries` is reached, then marks the job `failed`.
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
- Track status transitions: `queued`, `running`, `completed`, `failed`
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
| `POST` | `/jobs/{job_id}/retry` | Retry a failed job |
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
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Worker:

```bash
cd backend
rq worker agent-runtime --url redis://localhost:6379/0
```

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

## Reliability Tradeoffs

This project intentionally uses SQLite for a simple local MVP. SQLite is easy to run and demo, but PostgreSQL would be a better production database for concurrent writes, migrations, and operational tooling.

Prometheus metrics are generated from persisted job state, which keeps the API and worker consistent in a multi-process local setup. A larger production system could emit native counters from each process and aggregate them through Prometheus.

RQ and Redis keep async execution understandable for a portfolio project. For heavier workloads, scheduled workflows, or complex routing, Celery, Temporal, or a managed queue could be introduced later.

## Future Improvements

- PostgreSQL and Alembic migrations
- Authentication for dashboard/API access
- Workflow versioning
- Dead-letter queue view
- Streaming worker logs
- OpenTelemetry traces
- More workflow types with multi-step orchestration
- Provider selection per workflow
- CI pipeline with linting, tests, and Docker build checks

