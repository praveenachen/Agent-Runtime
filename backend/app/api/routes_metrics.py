from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.metrics_service import MetricsService

router = APIRouter(tags=["metrics"])


@router.get("/metrics-summary")
def metrics_summary(db: Session = Depends(get_db)) -> dict:
    return MetricsService(db).summary()


@router.get("/metrics")
def prometheus_metrics(db: Session = Depends(get_db)) -> Response:
    return Response(MetricsService(db).prometheus_text(), media_type="text/plain; version=0.0.4")
