# Execution and failure paths

The [README system diagram](../README.md#architecture) shows process boundaries. The sequences below explain ordering and recovery without introducing additional components.

## Successful execution

```mermaid
sequenceDiagram
    participant Client as Client / Relay
    participant API as Runtime API
    participant DB as SQLite
    participant Queue as Redis / RQ
    participant Worker as Worker / handler
    participant Provider as AIProvider
    Client->>API: POST /jobs with stable key and correlation ID
    API->>API: Validate request
    API->>DB: Commit job and unique key
    API->>Queue: Enqueue ID and expected attempt
    API-->>Client: 202 with job ID
    Queue->>Worker: Deliver job
    Worker->>DB: Atomically claim queued attempt
    Worker->>Provider: Request JSON
    Provider-->>Worker: JSON response
    Worker->>Worker: Validate output with Pydantic
    Worker->>DB: Conditionally commit completed result
    Client->>API: GET /jobs/{id}
    API->>DB: Read job and logs
    API-->>Client: Status, typed result or error
```

Enqueue is outside the database transaction. The dispatcher scans due queued records and resends after the dispatch lease expires, covering a crash on either side of enqueue. A duplicate queue message does not bypass the atomic claim. An idempotent resubmission returns the existing job, which may already be running or terminal.

## Failure and retry

```mermaid
flowchart TD
    Attempt[Running attempt] --> Failure[Failure]
    Failure --> Current{Still the current running attempt?}
    Current -->|No| Discard[Discard late result or failure]
    Current -->|Yes| Deadline{Execution deadline or RQ timeout?}
    Deadline -->|Yes| Timeout[timed_out]
    Deadline -->|No| Retryable{Transient provider error?}
    Retryable -->|No| Failed[failed]
    Retryable -->|Yes| Budget{Retry budget remaining?}
    Budget -->|No| Failed
    Budget -->|Yes| Persist[Persist queued state and exponential backoff]
    Persist --> Dispatcher[Dispatcher delivers when due]
    Dispatcher --> Claim[Atomically claim next attempt]
    Claim --> Attempt
```

`JobService` owns transitions. Failure decisions and status writes are fenced by status and attempt number, so cancellation or a newer attempt can win a race. `retry_count` increments when scheduling a retry; `attempt_count` increments when a worker claims it. Provider SDK retries are disabled to avoid an invisible second retry budget.

If a worker dies without recording failure, the dispatcher marks the abandoned run `timed_out` after its persisted deadline. It does not automatically replay that unknown external outcome. A Redis outage delays dispatch, not the persisted acceptance of a job. Neither queue recovery nor cancellation can reverse external effects.
