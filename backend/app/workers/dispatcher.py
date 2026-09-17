"""Recover durable pending work and expire abandoned executions independently of the API."""

import time

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.job_service import JobService
from app.services.queue_service import QueueService

logger = get_logger(__name__)


def run_once() -> None:
    with SessionLocal() as db:
        JobService(db).recover_expired()
        QueueService().dispatch_pending(db)


def main() -> None:
    configure_logging()
    init_db()
    while True:
        try:
            run_once()
        except Exception:
            logger.error("Dispatch/recovery pass failed; will retry")
        time.sleep(get_settings().dispatch_interval_seconds)


if __name__ == "__main__":
    main()
