from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.metrics_service import MetricsService

router = APIRouter(tags=["metrics"])


@router.get("/metrics-summary")
def metrics_summary(db: Session = Depends(get_db)) -> dict:
    return MetricsService(db).summary()

