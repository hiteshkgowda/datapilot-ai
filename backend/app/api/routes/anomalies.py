"""Anomaly Detection route.

POST /api/v1/anomalies
----------------------
Accepts a dataset_id and optional configuration (columns to analyse, methods,
thresholds).  Returns a structured anomaly report backed by deterministic
statistical analysis — no LLM involvement.

Design constraints
------------------
- Authentication required; dataset ownership is verified.
- Dataset is loaded once; the engine operates purely on the in-memory DataFrame.
- The service caches responses by SHA-256(dataset_id | params).
- Plotly chart JSON highlighting anomalies by severity is returned inline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_anomaly_service, get_dataset_service, get_memory_service
from app.core.auth import get_current_user
from app.core.exceptions import DatasetNotFoundError, ParseError
from app.schemas.anomaly import AnomalyRequest, AnomalyResponse
from app.schemas.auth import CurrentUser
from app.schemas.memory import TurnType
from app.services.anomaly_service import AnomalyDetectionService
from app.services.dataset_service import DatasetService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.post(
    "",
    response_model=AnomalyResponse,
    summary="Detect anomalies in a dataset",
    description=(
        "Runs up to four statistical methods (z-score, IQR, Isolation Forest, "
        "seasonal decomposition) over the requested numeric columns and returns "
        "a ranked anomaly report with a Plotly chart highlighting anomalous points."
    ),
)
async def detect_anomalies(
    request: AnomalyRequest,
    datasets: DatasetService = Depends(get_dataset_service),
    anomaly_svc: AnomalyDetectionService = Depends(get_anomaly_service),
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> AnomalyResponse:
    """Detect anomalies in a stored dataset.

    Raises:
        HTTP 404: Dataset not found or not accessible by the current user.
        HTTP 422: Dataset file is unreadable.
    """
    try:
        meta = datasets.get_metadata(request.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    if meta.owner_sub and meta.owner_sub != current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found."
        )

    try:
        df, _ = await run_in_threadpool(datasets.load_dataframe, request.dataset_id)
    except DatasetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    resp = await anomaly_svc.detect(df=df, request_dict=request.model_dump())

    if x_session_id:
        asyncio.ensure_future(
            memory.record_turn(
                session_id=x_session_id,
                user_sub=current_user.sub,
                turn_type=TurnType.ANOMALY,
                dataset_id=request.dataset_id,
                anomalies={
                    "total_anomaly_count": resp.total_anomaly_count,
                    "severity": resp.severity,
                    "affected_metrics": resp.affected_metrics,
                    "possible_reasons": resp.possible_reasons,
                },
            )
        )

    return resp
