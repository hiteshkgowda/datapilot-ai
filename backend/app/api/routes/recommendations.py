"""POST /api/v1/recommendations — Recommendation Engine endpoint."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies import get_dataset_service, get_memory_service, get_recommendation_service
from app.core.auth import get_current_user
from app.core.exceptions import DatasetNotFoundError, RecommendationError
from app.schemas.auth import CurrentUser
from app.schemas.memory import TurnType
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.dataset_service import DatasetService
from app.services.memory_service import MemoryService
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
logger = logging.getLogger(__name__)


@router.post("", response_model=RecommendationResponse, status_code=status.HTTP_200_OK)
async def generate_recommendations(
    request: RecommendationRequest,
    datasets: DatasetService = Depends(get_dataset_service),
    service: RecommendationService = Depends(get_recommendation_service),
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> RecommendationResponse:
    """Generate prioritised, data-grounded recommendations.

    Accepts any combination of anomalies, insights, forecast, and query_results.
    At least one signal source must be non-null.
    """
    if all(
        v is None
        for v in (request.anomalies, request.insights, request.forecast, request.query_results)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "At least one of 'anomalies', 'insights', 'forecast', or "
                "'query_results' must be provided."
            ),
        )

    try:
        meta = datasets.get_metadata(request.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if meta.owner_sub and meta.owner_sub != current_user.sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    try:
        resp = await service.generate(request)
    except RecommendationError as exc:
        logger.warning("Recommendation error for dataset %s: %s", request.dataset_id, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Unexpected recommendation error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate recommendations.",
        ) from exc

    if x_session_id:
        asyncio.ensure_future(
            memory.record_turn(
                session_id=x_session_id,
                user_sub=current_user.sub,
                turn_type=TurnType.RECOMMENDATION,
                dataset_id=request.dataset_id,
                recommendations={
                    "total_count": resp.total_count,
                    "summary": resp.summary,
                    "llm_enhanced": resp.llm_enhanced,
                    "top": [r.model_dump() for r in resp.recommendations[:5]],
                },
            )
        )

    return resp
