"""Natural-language analytics route: POST /query."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_analytics_service, get_dataset_service
from app.core.auth import get_current_user
from app.core.exceptions import (
    DatasetNotFoundError,
    LLMError,
    ParseError,
    PlanValidationError,
)
from app.schemas.auth import CurrentUser
from app.schemas.query import QueryRequest, QueryResponse
from app.services.analytics_service import AnalyticsService
from app.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])

_LLM_UNAVAILABLE_MESSAGE = (
    "The analytics model is currently unavailable. Please try again later."
)


@router.post(
    "",
    response_model=QueryResponse,
    summary="Ask a natural-language question about a dataset",
)
async def run_query(
    request: QueryRequest,
    service: AnalyticsService = Depends(get_analytics_service),
    datasets: DatasetService = Depends(get_dataset_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> QueryResponse:
    try:
        meta = datasets.get_metadata(request.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if meta.owner_sub and meta.owner_sub != current_user.sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    try:
        return await service.answer_question(request.dataset_id, request.question)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlanValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except LLMError as exc:
        logger.error("LLM planning failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=_LLM_UNAVAILABLE_MESSAGE) from exc
