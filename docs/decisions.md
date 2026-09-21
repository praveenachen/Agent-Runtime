# Engineering decisions

These records describe the implemented single-host runtime, not a future platform roadmap.

## 1. Asynchronous workers with Redis/RQ

- **Problem:** Provider latency and failure should not tie execution lifetime to an HTTP connection.
- **Options:** Execute inside the API request; use RQ/Redis; adopt a larger workflow engine.
- **Decision:** Persist acceptance in FastAPI, execute in RQ workers, and use a dispatcher process for due work and recovery.
- **Why:** RQ fits the existing Python stack and provides worker isolation and hard attempt timeouts. A separate dispatcher can recover work while the API is unavailable.
- **Tradeoff:** Operators run three application processes plus Redis. SQLite and Redis cannot share a transaction, so messages can be delivered more than once.
- **When reconsidered:** Complex multi-step orchestration, scheduling, or throughput requirements justify a workflow engine rather than a queue and explicit state machine.

## 2. SQLite state, durable pending work, and idempotency

- **Problem:** Queue messages alone are insufficient for execution inspection and recovery; HTTP retries must not create duplicate logical jobs.
- **Options:** Redis as the only state store; shared local SQLite; a network database and dedicated outbox table.
- **Decision:** SQLite owns jobs/logs. Queued rows and dispatch leases act as the durable pending-work record. A unique caller-supplied key and canonical validated-request hash enforce submission deduplication; mismatched reuse returns 409. Status/attempt compare-and-swap updates fence workers.
- **Why:** This preserves the working persistence layer and closes the enqueue gap without replacing the database or adding a separate outbox model. Additive startup migration retains existing history.
- **Tradeoff:** One host, serialized SQLite writes, retained keys, and database-wide key scope. A lease can cause duplicate queue deliveries. Provider calls still need downstream idempotency for external effects. Stored inputs/outputs need operational access controls and backups.
- **When reconsidered:** Multi-host workers, greater write concurrency, tenant-scoped keys, retention requirements, or managed recovery justify a network database and versioned migrations.

## 3. Provider interface and schema validation

- **Problem:** Vendor SDK errors and malformed model responses should not leak into runtime state or couple handlers to one SDK.
- **Options:** Direct SDK calls in handlers; a small provider interface; a general orchestration framework.
- **Decision:** Handlers call `AIProvider.generate_structured` with their expected Pydantic output model. The OpenAI adapter maps network/status failures to runtime error categories; a deterministic mock supports local use and tests. Input and output schemas use Pydantic.
- **Why:** The current three handlers need JSON generation and validation, not a framework. SDK calls stay inside the adapter; success requires validated output.
- **Tradeoff:** Only one real provider is implemented. Schema compliance cannot guarantee semantic truth. Invalid output fails immediately rather than entering an implicit repair loop.
- **When reconsidered:** A second provider, streaming, tool calling, or different modalities create concrete requirements that the current interface cannot express.

## 4. Bounded retries, cancellation, and application responsibility

- **Problem:** Transient failure deserves recovery, but unlimited retries, opaque cancellation, or duplicated application policy can make execution unsafe.
- **Options:** Retry every error; delegate retries to SDK defaults; centralize a bounded runtime policy with explicit terminal outcomes.
- **Decision:** Only normalized transient provider failures retry, with capped exponential backoff and at most `1 + max_retries` started attempts. SDK retries are off. Execution timeouts and permanent errors do not auto-retry. Cancellation prevents future attempts and publication of late results. Relay owns planning, approval, workflow meaning, and user-facing state; it calls the runtime over HTTP without a reverse dependency.
- **Why:** A single observable budget and persisted schedule make behavior inspectable. The runtime remains reusable across applications, and cancellation reports a state boundary it can actually enforce.
- **Tradeoff:** There is no retry jitter or provider-specific `Retry-After` scheduling. Cancelling cannot undo or always interrupt an in-flight call. Provider timeouts may be retried despite ambiguous external outcomes. Applications must choose appropriate retry budgets and downstream effect semantics.
- **When reconsidered:** Fleet-wide retry contention, tenant budgets, provider-specific limits, or side-effecting handlers require jitter, explicit downstream operation keys, and stronger cancellation coordination.
