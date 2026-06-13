"""Natural-language analytics route: POST /query."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies import (
    get_analytics_service,
    get_dataset_service,
    get_insight_service,
    get_memory_service,
)
from app.core.auth import get_current_user
from app.core.exceptions import (
    DatasetNotFoundError,
    LLMError,
    ParseError,
    PlanValidationError,
)
from app.schemas.auth import CurrentUser
from app.schemas.memory import TurnType
from app.schemas.query import QueryRequest, QueryResponse
from app.services.analytics_service import AnalyticsService
from app.services.dataset_service import DatasetService
from app.services.insight_service import InsightGenerationService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])


@router.post(
    "",
    response_model=QueryResponse,
    summary="Ask a natural-language question about a dataset",
)
async def run_query(
    request: QueryRequest,
    service: AnalyticsService = Depends(get_analytics_service),
    datasets: DatasetService = Depends(get_dataset_service),
    insight_svc: InsightGenerationService = Depends(get_insight_service),
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> QueryResponse:
    try:
        meta = datasets.get_metadata(request.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if meta.owner_sub and meta.owner_sub != current_user.sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    try:
        analysis = await service.analyze(request.dataset_id, request.question)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlanValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except LLMError as exc:
        logger.error("LLM planning failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    response = QueryResponse(
        answer=analysis.result.answer,
        query_plan=analysis.plan,
        execution_time_ms=analysis.execution_time_ms,
        total_time_ms=analysis.total_time_ms,
    )

    if request.include_insights and analysis.result.table:
        try:
            insights = await insight_svc.generate(
                dataset_id=request.dataset_id,
                question=request.question,
                table_data=analysis.result.table,
            )
            response = response.model_copy(update={"insights": insights})
        except Exception as exc:
            logger.warning("Insight generation failed (non-fatal): %s", exc)

    if x_session_id:
        table = analysis.result.table or []
        asyncio.ensure_future(
            memory.record_turn(
                session_id=x_session_id,
                user_sub=current_user.sub,
                turn_type=TurnType.QUERY,
                dataset_id=request.dataset_id,
                question=request.question,
                answer=analysis.result.answer,
                table_data=table,
            )
        )

    return response
