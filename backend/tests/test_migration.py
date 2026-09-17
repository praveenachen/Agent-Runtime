from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, inspect, text

from app.db import init_db as migration


def test_existing_sqlite_database_is_upgraded_without_losing_history(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("""CREATE TABLE jobs (
            id VARCHAR(36) PRIMARY KEY, workflow_type VARCHAR(64), input_payload JSON,
            output_payload JSON, status VARCHAR(9), error_message TEXT,
            retry_count INTEGER, max_retries INTEGER, created_at DATETIME,
            started_at DATETIME, completed_at DATETIME, latency_ms INTEGER
        )""")
        conn.exec_driver_sql(
            "INSERT INTO jobs (id, workflow_type, input_payload, status, retry_count, max_retries, created_at) VALUES ('legacy', 'summarize_text', '{}', 'running', 0, 2, CURRENT_TIMESTAMP)"
        )
    monkeypatch.setattr(migration, "engine", engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: migration.init_db(), range(2)))
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM jobs")).mappings().one()
        assert row["id"] == row["correlation_id"] == "legacy"
        assert row["deadline_at"] and row["next_attempt_at"]
        assert row["max_retries"] == 2
        assert row["attempt_count"] == 1
        assert set(migration.COLUMNS) <= {col["name"] for col in inspect(conn).get_columns("jobs")}
    engine.dispose()
