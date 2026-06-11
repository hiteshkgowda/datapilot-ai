"""Forecasting route: POST /forecast."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_dataset_service, get_forecast_service
from app.core.auth import get_current_user
from app.core.exceptions import (
    DatasetNotFoundError,
    ForecastValidationError,
    LLMError,
    ParseError,
)
from app.schemas.auth import CurrentUser
from app.schemas.forecast import ForecastRequest, ForecastResponse
from app.services.dataset_service import DatasetService
from app.services.forecast_service import ForecastService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecast", tags=["forecast"])

_LLM_UNAVAILABLE_MESSAGE = (
    "The forecasting model is currently unavailable. Please try again later."
)


@router.post(
    "",
    response_model=ForecastResponse,
    summary="Forecast or detect anomalies in a dataset's time series",
)
async def create_forecast(
    request: ForecastRequest,
    service: ForecastService = Depends(get_forecast_service),
    datasets: DatasetService = Depends(get_dataset_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> ForecastResponse:
    try:
        meta = datasets.get_metadata(request.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if meta.owner_sub and meta.owner_sub != current_user.sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    try:
        return await service.create_forecast(request.dataset_id, request.question)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ForecastValidationError, ParseError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except LLMError as exc:
        logger.error("Forecast planning failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_LLM_UNAVAILABLE_MESSAGE) from exc
