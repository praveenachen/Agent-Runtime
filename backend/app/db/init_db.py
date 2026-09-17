from sqlalchemy import inspect

from app.db.session import Base, engine

# Small, additive migration for the existing SQLite schema; preserve all job history.
COLUMNS = {
    "correlation_id": "VARCHAR(128)",
    "idempotency_key": "VARCHAR(128)",
    "request_hash": "VARCHAR(64)",
    "error": "JSON",
    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
    "timeout_seconds": "INTEGER NOT NULL DEFAULT 300",
    "deadline_at": "DATETIME",
    "next_attempt_at": "DATETIME",
    "last_dispatched_at": "DATETIME",
    "queue_latency_ms": "INTEGER",
}


def init_db() -> None:
    import app.models.job  # noqa: F401

    # Serialize API/dispatcher startup and migration on the supported SQLite store.
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        Base.metadata.create_all(bind=connection)
        present = {column["name"] for column in inspect(connection).get_columns("jobs")}
        for name, definition in COLUMNS.items():
            if name not in present:
                connection.exec_driver_sql(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
        if "attempt_count" not in present:
            connection.exec_driver_sql(
                "UPDATE jobs SET attempt_count = retry_count + "
                "CASE WHEN status IN ('running', 'completed', 'failed') THEN 1 ELSE 0 END"
            )
        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_jobs_idempotency_key ON jobs (idempotency_key)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_jobs_dispatch ON jobs (status, next_attempt_at)"
        )
        connection.exec_driver_sql(
            "UPDATE jobs SET correlation_id = id WHERE correlation_id IS NULL"
        )
        connection.exec_driver_sql(
            "UPDATE jobs SET next_attempt_at = created_at WHERE next_attempt_at IS NULL"
        )
        # Legacy running records have no deadline. Expire conservatively rather than replay.
        connection.exec_driver_sql(
            "UPDATE jobs SET deadline_at = CURRENT_TIMESTAMP WHERE status = 'running' AND deadline_at IS NULL"
        )
        connection.commit()
