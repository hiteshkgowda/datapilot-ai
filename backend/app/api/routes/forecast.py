"""Forecasting route: POST /forecast."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies import get_dataset_service, get_forecast_service, get_memory_service
from app.core.auth import get_current_user
from app.core.exceptions import (
    DatasetNotFoundError,
    ForecastValidationError,
    LLMError,
    ParseError,
)
from app.schemas.auth import CurrentUser
from app.schemas.forecast import ForecastRequest, ForecastResponse
from app.schemas.memory import TurnType
from app.services.dataset_service import DatasetService
from app.services.forecast_service import ForecastService
from app.services.memory_service import MemoryService

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
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> ForecastResponse:
    try:
        meta = datasets.get_metadata(request.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if meta.owner_sub and meta.owner_sub != current_user.sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    try:
        resp = await service.create_forecast(request.dataset_id, request.question)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ForecastValidationError, ParseError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except LLMError as exc:
        logger.error("Forecast planning failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if x_session_id:
        asyncio.ensure_future(
            memory.record_turn(
                session_id=x_session_id,
                user_sub=current_user.sub,
                turn_type=TurnType.FORECAST,
                dataset_id=request.dataset_id,
                question=request.question,
                answer=resp.answer,
                table_data=resp.table_data,
                chart_spec=resp.chart_spec,
                forecast={
                    "operation": resp.operation,
                    "horizon": resp.horizon,
                    "frequency": resp.frequency,
                    "method_used": resp.method_used,
                },
            )
        )

    return resp
