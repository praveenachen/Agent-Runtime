from datetime import UTC, datetime


def utcnow() -> datetime:
    """UTC stored without timezone, matching the existing SQLite timestamp contract."""
    return datetime.now(UTC).replace(tzinfo=None)
