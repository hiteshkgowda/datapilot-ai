"""Root Cause Analysis route.

POST /api/v1/root-cause
-----------------------
Accepts a dataset_id and a natural-language question (e.g. "Why did revenue
drop?").  Returns a structured root-cause analysis backed by deterministic
statistical decomposition and optional LLM reasoning.

Design constraints
------------------
- Authentication required; dataset ownership is verified.
- Dataset is loaded once; the engine operates purely on the in-memory DataFrame.
- The service caches responses by SHA-256(dataset_id | normalised question | params).
- The service never raises — errors are surfaced as a descriptive problem string.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_dataset_service, get_memory_service, get_root_cause_service
from app.core.auth import get_current_user
from app.core.exceptions import DatasetNotFoundError, ParseError
from app.core.rate_limit import _dynamic_limit, limiter
from app.schemas.auth import CurrentUser
from app.schemas.memory import TurnType
from app.schemas.root_cause import RootCauseRequest, RootCauseResponse
from app.services.dataset_service import DatasetService
from app.services.memory_service import MemoryService
from app.services.root_cause_service import RootCauseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/root-cause", tags=["root-cause"])


@router.post(
    "",
    response_model=RootCauseResponse,
    summary="Root cause analysis: why did a metric change?",
    description=(
        "Decomposes a period-over-period metric change into contributing "
        "dimensions (region, product, segment, channel, category) and "
        "ranks the primary drivers by impact. "
        "Uses deterministic statistics grounded by optional LLM reasoning."
    ),
)
@limiter.limit(_dynamic_limit)
async def root_cause_analysis(
    request: Request,
    body: RootCauseRequest,
    datasets: DatasetService = Depends(get_dataset_service),
    rca_svc: RootCauseService = Depends(get_root_cause_service),
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> RootCauseResponse:
    """Perform root cause analysis on a stored dataset.

    Raises:
        HTTP 404: Dataset not found or not accessible by the current user.
        HTTP 422: Dataset file is unreadable.
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

    try:
        df, _ = await run_in_threadpool(datasets.load_dataframe, body.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    result = await rca_svc.analyze(
        df=df,
        request_dict=body.model_dump(),
    )

    if x_session_id:
        asyncio.ensure_future(
            memory.record_turn(
                session_id=x_session_id,
                user_sub=current_user.sub,
                turn_type=TurnType.AGENT,
                dataset_id=body.dataset_id,
                question=body.question,
                answer=result.problem,
            )
        )

    return result
