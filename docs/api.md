# HTTP contract

The public execution resource is named **job**. Interactive OpenAPI documentation is available at `/docs` while the API is running.

| Method | Route | Behavior |
| --- | --- | --- |
| POST | `/jobs` | Validate, persist, and attempt dispatch; 202 with the job record |
| GET | `/jobs` | Latest 100 jobs, newest first; summary fields only |
| GET | `/jobs/{id}` | Full job, payloads, timestamps, error, and persisted logs; 404 if absent |
| POST | `/jobs/{id}/cancel` | Return cancelled queued/running job, or unchanged terminal job |
| POST | `/jobs/{id}/retry` | Retry only an eligible transient failure with remaining budget; otherwise 409 |
| GET | `/metrics-summary` | Dashboard aggregates from persisted state |
| GET | `/metrics` | Prometheus-compatible snapshot gauges |
| GET | `/health` | API liveness; does not check workers or Redis |

## Submit and inspect

```bash
curl -sS http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: example-summary-001' \
  -H 'X-Correlation-ID: example-trace-001' \
  -d '{"workflow_type":"summarize_text","input_payload":{"text":"Queued execution separates request acceptance from provider work."},"max_retries":2,"timeout_seconds":300}'
```

Reuse the same key and body if the response is lost. A successful submission returns `id`; substitute it in:

```bash
curl -sS http://localhost:8000/jobs/JOB_ID
curl -sS -X POST http://localhost:8000/jobs/JOB_ID/cancel
```

Keys/correlation IDs may also be sent as `idempotency_key` and `correlation_id` body fields. They accept 1–128 printable ASCII characters without spaces. Conflicting header/body identifiers return 422. Submit/status responses include `X-Correlation-ID`; submission also includes `Location`. Missing correlation IDs are generated once. Correlation IDs are excluded from the idempotency fingerprint; a duplicate submission retains the original correlation ID.

The fingerprint covers workflow type, validated input, retry budget, execution timeout, and non-normal demo scenario. Omitted and explicit `normal` scenarios are equivalent. Server defaults are normalized before hashing; a changed material field with the same key returns 409. Submission includes `X-Idempotency-Reused: true` when it returns an existing job.

## Registered handlers

These small handlers demonstrate the runtime boundary. They do not implement Relay planning or arbitrary action execution.

| `workflow_type` | Input | Validated output |
| --- | --- | --- |
| `summarize_text` | `{"text":"Text to summarize"}` | Nonempty `summary`; `key_points` string list (defaults to empty) |
| `extract_structured_data` | `{"text":"Acme needs a follow-up by Friday."}` | `title` (string/null), `entities` (name/type/optional value), `dates`, `action_items` |
| `classify_message` | `{"message":"The nightly execution failed."}` | `category`, `priority`, `sentiment` enums; `confidence` from 0 to 1 |

Text/message lengths are 1–100,000 characters. `max_retries` is 0–5 (default 2); `timeout_seconds` is 1–3600 (default 300). Invalid requests return 422 before a job is created. Idempotency covers the validated input plus workflow type, retry budget, and execution timeout.

## Results and failures

States are `queued`, `running`, `completed`, `failed`, `cancelled`, and `timed_out`. A `completed` job has schema-validated `output_payload`; failures expose both the legacy `error_message` and `error: {code, message, retryable}`. Possible codes are `ValidationError`, `ProviderUnavailable`, `ProviderRateLimited`, `ProviderTimeout`, `StructuredOutputInvalid`, `ExecutionTimeout`, `ExecutionCancelled`, and `InternalExecutionError`. Request-validation HTTP errors use FastAPI's `detail` response rather than a persisted job error.

`retryable` describes the error category, not remaining budget or permission to restart the job. Normal automatic retry exhaustion cannot be reset by the manual retry route. Unexpected provider/worker errors do not expose raw exception text. Queued retries retain their last error until the next attempt is claimed.

`attempt_count` counts started attempts; `retry_count` counts scheduled retries. Timestamps use the existing timezone-naive **UTC** representation. `started_at`, `latency_ms`, and `queue_latency_ms` describe the latest attempt; logs preserve earlier transitions. `completed_at` marks a terminal state, including cancellation/failure, not just success. Input and output payloads are stored and retrievable, so callers must avoid submitting secrets unnecessarily.

## Relay adapter expectations

Relay should map an approved operation to a supported handler, submit it over HTTP with stable idempotency/correlation identifiers, keep the returned job ID, and poll or cancel that ID. A client network timeout is not runtime cancellation. Treat all six statuses explicitly and read typed errors rather than interpreting exception messages.

The Relay client implementation is not available here. This is the runtime's actual contract and an integration boundary description, not a claim that Relay's current methods or response types have been verified against it.
