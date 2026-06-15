"""Data Quality route.

GET /api/v1/datasets/{dataset_id}/quality
-----------------------------------------
Returns a comprehensive data quality report for a stored dataset.
All analysis is deterministic (no LLM) and backed by an in-memory TTL cache.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_data_quality_service, get_dataset_service
from app.core.auth import get_current_user
from app.core.exceptions import DatasetNotFoundError, ParseError
from app.core.rate_limit import _dynamic_limit, limiter
from app.schemas.auth import CurrentUser
from app.schemas.data_quality import DataQualityResponse
from app.services.data_quality_service import DataQualityService
from app.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["data-quality"])


@router.get(
    "/{dataset_id}/quality",
    response_model=DataQualityResponse,
    summary="Data quality profile for a dataset",
)
@limiter.limit(_dynamic_limit)
async def get_data_quality(
    request: Request,
    dataset_id: str,
    datasets: DatasetService = Depends(get_dataset_service),
    quality_svc: DataQualityService = Depends(get_data_quality_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> DataQualityResponse:
    """Profile data quality: completeness, uniqueness, validity, and outliers.

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

    return await run_in_threadpool(quality_svc.analyse, df, dataset_id)
