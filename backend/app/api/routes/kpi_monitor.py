"""KPI Monitor route.

GET /api/v1/datasets/{dataset_id}/monitor
------------------------------------------
Returns a KPI monitoring report: trend stats, alerts, health indicators,
and recommendations for all numeric columns. Deterministic, no LLM.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_dataset_service, get_kpi_monitor_service
from app.core.auth import get_current_user
from app.core.exceptions import DatasetNotFoundError, ParseError
from app.core.rate_limit import _dynamic_limit, limiter
from app.schemas.auth import CurrentUser
from app.schemas.kpi_monitor import KPIMonitorResponse
from app.services.dataset_service import DatasetService
from app.services.kpi_monitor_service import KPIMonitorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["kpi-monitor"])


@router.get(
    "/{dataset_id}/monitor",
    response_model=KPIMonitorResponse,
    summary="KPI monitoring report for a dataset",
)
@limiter.limit(_dynamic_limit)
async def get_kpi_monitor(
    request: Request,
    dataset_id: str,
    max_kpis: int = 12,
    datasets: DatasetService = Depends(get_dataset_service),
    monitor_svc: KPIMonitorService = Depends(get_kpi_monitor_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> KPIMonitorResponse:
    """Monitor KPIs: trends, alerts, health, and recommendations.

    Raises:
        HTTP 404: Dataset not found or not owned by the current user.
        HTTP 422: Dataset file is unreadable.
    """
    try:
        meta = datasets.get_metadata(dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if meta.owner_sub and meta.owner_sub != current_user.sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    try:
        df, _ = await run_in_threadpool(datasets.load_dataframe, dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return await run_in_threadpool(monitor_svc.monitor, df, dataset_id, max_kpis)
