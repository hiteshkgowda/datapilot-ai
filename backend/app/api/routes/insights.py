"""AI Insight Generation Engine route.

POST /api/v1/insights/generate
-------------------------------
Accepts a dataset_id, the original question, and the table_data rows from a
prior query result.  Returns AI-generated insights backed by deterministic
statistical analysis and optional LLM reasoning.

Design constraints
------------------
- Authentication is required; dataset ownership is verified.
- The endpoint never loads the dataset file — it works on caller-supplied
  table_data so it can operate on any query result without a second I/O.
- The service caches responses by SHA-256(dataset_id | question | table_data)
  with a configurable TTL.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.dependencies import get_dataset_service, get_insight_service, get_memory_service
from app.core.auth import get_current_user
from app.core.exceptions import DatasetNotFoundError
from app.core.rate_limit import _dynamic_limit, limiter
from app.schemas.auth import CurrentUser
from app.schemas.insight import InsightRequest, InsightResponse
from app.schemas.memory import TurnType
from app.services.dataset_service import DatasetService
from app.services.insight_service import InsightGenerationService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.post(
    "/generate",
    response_model=InsightResponse,
    summary="Generate AI insights from query result data",
    description=(
        "Runs deterministic statistical analysis on the supplied `table_data` rows "
        "and passes the findings to an LLM to produce natural-language insights. "
        "The LLM is constrained to reference only the computed statistics — it cannot "
        "hallucinate or invent data. Responses are TTL-cached."
    ),
)
@limiter.limit(_dynamic_limit)
async def generate_insights(
    request: Request,
    body: InsightRequest,
    datasets: DatasetService = Depends(get_dataset_service),
    insight_svc: InsightGenerationService = Depends(get_insight_service),
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> InsightResponse:
    """Generate AI insights for a previously executed query result.

    Raises:
        HTTP 404: Dataset not found or not accessible by the current user.
    """
    try:
        meta = datasets.get_metadata(body.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    if meta.owner_sub and meta.owner_sub != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found."
        )

    resp = await insight_svc.generate(
        dataset_id=body.dataset_id,
        question=body.question,
        table_data=body.table_data,
    )

    if x_session_id:
        asyncio.ensure_future(
            memory.record_turn(
                session_id=x_session_id,
                user_sub=current_user.sub,
                turn_type=TurnType.INSIGHT,
                dataset_id=body.dataset_id,
                question=body.question,
                answer=resp.summary,
                insights=resp.model_dump(),
            )
        )

    return resp
