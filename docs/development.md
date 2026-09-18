# Development and setup

Run all commands from the repository root unless a command explicitly changes directories. The dashboard is optional; the API can be used with curl or `/docs`.

## Docker Compose

Requirements: Docker Engine/Desktop running, with Compose v2 or newer. No separate Python, Node, or Redis install is needed.

```bash
# Copy only on first setup; never overwrite an existing local configuration.
test -f .env || cp .env.example .env
docker compose up --build
```

The default empty `OPENAI_API_KEY` selects the deterministic mock provider. To force mock mode even if `.env` contains a real key, run `OPENAI_API_KEY= docker compose up --build` in a POSIX shell. For a real provider, set the key only in `.env`, then recreate the services. API keys must never use a `VITE_` prefix.

- API: http://localhost:8000; OpenAPI: http://localhost:8000/docs
- Dashboard: http://localhost:5173
- API-only stack: `docker compose up --build backend worker dispatcher`
- Logs: `docker compose logs -f backend worker dispatcher`
- Stop: Ctrl+C, then `docker compose down`

SQLite lives at `./data/agent_runtime.db` on the host. Redis AOF uses the `redis-data` named volume. Stopping/removing containers with `down` retains both; deleting database files or volumes does not. Stop older processes and back up SQLite before upgrading an existing installation. The API initializes/migrates the database before workers start through Compose health dependencies.

## Native development (Linux/macOS, POSIX shell)

Install Python 3.12, Redis 7, and Node 22.12+ (Node only for the dashboard). RQ's standard worker uses process isolation; on Windows, use Docker Compose or a Linux environment.

Create the environment once:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
test -f .env || cp .env.example .env
```

Start Redis in a terminal:

```bash
redis-server --bind 127.0.0.1 --port 6379
```

In a second terminal, start the API from the repository root. Wait for startup to complete before starting workers:

```bash
PYTHONPATH=backend REDIS_URL=redis://127.0.0.1:6379/0 DATABASE_URL=sqlite:///./agent_runtime.db \
  .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a third terminal, start the worker from the same root:

```bash
PYTHONPATH=backend REDIS_URL=redis://127.0.0.1:6379/0 DATABASE_URL=sqlite:///./agent_runtime.db \
  .venv/bin/rq worker agent-runtime --url redis://127.0.0.1:6379/0
```

In a fourth terminal, start the required dispatcher from the same root:

```bash
PYTHONPATH=backend REDIS_URL=redis://127.0.0.1:6379/0 DATABASE_URL=sqlite:///./agent_runtime.db \
  .venv/bin/python -m app.workers.dispatcher
```

All three application processes read the root `.env`. Prefix each command with `OPENAI_API_KEY=` to force mock mode. Their database URL, working directory, Redis URL, and queue name must agree. Native history is in the root `agent_runtime.db`, separate from the Compose database under `data/`.

Optional dashboard, in another terminal:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1
```

Stop each native process with Ctrl+C. The frontend's `VITE_API_BASE_URL` defaults to `http://localhost:8000`; change it only when the API address changes. The Compose frontend is a local Vite development server, not a production static-site deployment.

## Configuration

`.env.example` contains non-secret defaults; environment variables override `.env`.

| Setting | Default / meaning |
| --- | --- |
| `OPENAI_API_KEY` | Empty selects mock; nonempty selects the OpenAI adapter |
| `OPENAI_MODEL` | `gpt-4o-mini`; used only by the real adapter |
| `PROVIDER_TIMEOUT_SECONDS` | 60; provider HTTP timeout, range greater than 0 through 300 |
| `RETRY_BASE_SECONDS` / `RETRY_MAX_SECONDS` | 5 / 60; exponential delay base and cap |
| `DISPATCH_INTERVAL_SECONDS` / `REDISPATCH_SECONDS` | 2 / 30; dispatcher poll interval and delivery lease |
| `DATABASE_URL` | Native default `sqlite:///./agent_runtime.db`; Compose sets `sqlite:////data/agent_runtime.db` |
| `REDIS_URL` | Default/Compose `redis://redis:6379/0`; native commands override to localhost |
| `QUEUE_NAME` | `agent-runtime`; match the RQ worker command when changing it |
| `LOG_LEVEL` | `INFO`; SDK HTTP/debug loggers are restricted to warning |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` |

Compose forwards the provider/retry/dispatcher settings in `.env.example` and fixes the database/Redis addresses for its internal network. Other overrides require updating the service environment and, for the queue name, the worker command.

## Troubleshooting

- **`docker: command not found`:** start Docker Desktop and open a new terminal. If Docker added its PATH setting to `~/.zprofile`, load it with `source ~/.zprofile`.
- **Cannot connect to Docker:** start the Docker engine/Desktop first.
- **Jobs stay queued:** inspect worker and dispatcher logs and check that all processes use the same database, Redis address, and queue name. `/health` alone does not establish worker readiness.
- **Requests return 409:** a key was reused for different validated input, a retry is ineligible, or a cancellation raced repeated state changes. Reuse a submission key only for the same logical request.
- **Real-provider errors:** inspect the normalized job error and configured credentials. Provider failures do not fall back to fabricated successful mock results.

## Validation

Use the [README testing commands](../README.md#testing). The checked-in tests do not call a real provider or require live Redis. CI also builds the container images; it does not currently automate a live queue smoke test. For a manual smoke check, start the full stack in mock mode, submit the [API example](api.md#submit-and-inspect), and retrieve the ID until it reaches `completed` with `attempt_count: 1` and validated output.
