"""AI Executive Dashboard Generator routes.

POST /api/v1/dashboards/generate  — generate a dashboard config from a dataset
GET  /api/v1/dashboards/{id}      — retrieve a saved dashboard
POST /api/v1/dashboards/save      — persist a generated dashboard
GET  /api/v1/dashboards           — list all saved dashboards for the current user

Design constraints
------------------
- Authentication required on all endpoints; ownership verified on all reads.
- No raw LLM output reaches chart specs — all Plotly figures are built server-side.
- Dataset ownership is checked before generation (same pattern as query, insights, etc.).
- Dashboard ownership is stamped from JWT sub at save time — never from request body.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies import (
    get_dashboard_service,
    get_dataset_service,
    get_memory_service,
)
from app.core.auth import get_current_user
from app.core.exceptions import DatasetNotFoundError
from app.schemas.auth import CurrentUser
from app.schemas.dashboard import (
    DashboardConfig,
    DashboardListResponse,
    GenerateDashboardRequest,
    GenerateDashboardResponse,
    SaveDashboardRequest,
    SaveDashboardResponse,
)
from app.schemas.memory import TurnType
from app.services.dashboard_generator import DashboardGeneratorService
from app.services.dashboard_store import DashboardNotFoundError, DashboardStore
from app.services.dataset_service import DatasetService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.post(
    "/generate",
    response_model=GenerateDashboardResponse,
    summary="Generate an AI executive dashboard config",
    description=(
        "Analyses a dataset through four deterministic engines (KPI selection, "
        "chart recommendation, layout, scoring) and optionally uses an LLM for "
        "dashboard naming and insight recommendations. "
        "All chart specs are built server-side — no LLM output reaches Plotly. "
        "Responses are TTL-cached."
    ),
)
async def generate_dashboard(
    request: GenerateDashboardRequest,
    datasets: DatasetService = Depends(get_dataset_service),
    dashboard_svc: DashboardGeneratorService = Depends(get_dashboard_service),
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> GenerateDashboardResponse:
    """Generate a dashboard configuration from a dataset.

    Raises:
        HTTP 404: Dataset not found or not accessible by the current user.
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

    config = await dashboard_svc.generate(request=request, owner_sub=current_user.sub)

    if x_session_id:
        asyncio.ensure_future(
            memory.record_turn(
                session_id=x_session_id,
                user_sub=current_user.sub,
                turn_type=TurnType.AGENT,
                dataset_id=request.dataset_id,
                question=request.prompt,
                answer=config.dashboard_name,
                metadata={
                    "score": config.score,
                    "kpi_count": len(config.kpis),
                    "chart_count": len(config.charts),
                },
            )
        )

    return GenerateDashboardResponse(
        dashboard_name=config.dashboard_name,
        dataset_id=config.dataset_id,
        kpis=config.kpis,
        charts=config.charts,
        layout=config.layout,
        recommendations=config.recommendations,
        score=config.score,
        generation_time_ms=config.generation_time_ms,
        cache_hit=config.cache_hit,
    )


@router.get(
    "",
    response_model=DashboardListResponse,
    summary="List all saved dashboards for the current user",
)
async def list_dashboards(
    dashboard_svc: DashboardGeneratorService = Depends(get_dashboard_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> DashboardListResponse:
    """Return all dashboards saved by the current user, newest first."""
    dashboards = dashboard_svc._store.list_for_user(current_user.sub)
    return DashboardListResponse(count=len(dashboards), dashboards=dashboards)


@router.get(
    "/{dashboard_id}",
    response_model=DashboardConfig,
    summary="Retrieve a saved dashboard by ID",
)
async def get_dashboard(
    dashboard_id: str,
    dashboard_svc: DashboardGeneratorService = Depends(get_dashboard_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> DashboardConfig:
    """Return a saved dashboard.

    Raises:
        HTTP 404: Dashboard not found or not owned by the current user.
    """
    try:
        return dashboard_svc._store.get(dashboard_id, current_user.sub)
    except DashboardNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/save",
    response_model=SaveDashboardResponse,
    summary="Persist a generated dashboard to disk",
    status_code=status.HTTP_201_CREATED,
)
async def save_dashboard(
    request: SaveDashboardRequest,
    dashboard_svc: DashboardGeneratorService = Depends(get_dashboard_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> SaveDashboardResponse:
    """Save a generated dashboard config to persistent storage.

    ``owner_sub`` is always stamped from the JWT — it cannot be supplied in
    the request body, preventing cross-user saves.
    """
    config = request.dashboard_config
    if request.dashboard_name:
        config = config.model_copy(update={"dashboard_name": request.dashboard_name})

    meta = dashboard_svc._store.save(config, owner_sub=current_user.sub)

    return SaveDashboardResponse(
        dashboard_id=meta.dashboard_id,
        dashboard_name=meta.dashboard_name,
        created_at=meta.created_at,
        message="Dashboard saved successfully.",
    )
