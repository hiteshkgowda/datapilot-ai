"""Agent orchestration routes (Phase 9).

Routes:
    POST /agent/run                     — start a new agent session
    POST /agent/resume/{session_id}     — resume a suspended (CRUD approval) session
    POST /agent/explain                 — return the execution plan without running tools
    GET  /agent/session/{session_id}    — inspect a session's current state
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_agent_orchestrator,
    get_connection_service,
    get_dataset_service,
)
from app.api.params import HexId
from app.core.auth import get_current_user
from app.core.exceptions import (
    AgentExecutionError,
    AgentPlanError,
    ConnectionNotFoundError,
    DatasetNotFoundError,
    ValidationError,
)
from app.schemas.agent import (
    AgentApproveRequest,
    AgentExplainResponse,
    AgentRunRequest,
    AgentRunResponse,
    AgentSessionInfo,
)
from app.schemas.auth import CurrentUser
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.connection_service import ConnectionService
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/agent", tags=["agent"])


def _check_resource_ownership(
    request: AgentRunRequest,
    datasets: DatasetService,
    connections: ConnectionService,
    owner_sub: str,
) -> None:
    """Raise 404 if the caller doesn't own the dataset or connection in the request."""
    if request.dataset_id:
        try:
            meta = datasets.get_metadata(request.dataset_id)
        except DatasetNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if meta.owner_sub and meta.owner_sub != owner_sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    if request.connection_id:
        try:
            record = connections._read_record(request.connection_id)
        except ConnectionNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if record.owner_sub and record.owner_sub != owner_sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found.")


@router.post(
    "/run",
    response_model=AgentRunResponse,
    summary="Start a new agent session",
    status_code=status.HTTP_200_OK,
)
async def run_agent(
    request: AgentRunRequest,
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
    datasets: DatasetService = Depends(get_dataset_service),
    connections: ConnectionService = Depends(get_connection_service),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentRunResponse:
    """Start a new multi-step agent session."""
    _check_resource_ownership(request, datasets, connections, current_user.sub)
    try:
        return await orchestrator.run(request, owner_sub=current_user.sub)
    except AgentPlanError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except AgentExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/resume/{session_id}",
    response_model=AgentRunResponse,
    summary="Resume a suspended agent session after CRUD approval",
)
async def resume_agent(
    session_id: HexId,
    request: AgentApproveRequest,
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentRunResponse:
    """Resume a session that was paused for CRUD approval."""
    try:
        return await orchestrator.resume(session_id, request, owner_sub=current_user.sub)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AgentExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post(
    "/explain",
    response_model=AgentExplainResponse,
    summary="Return the execution plan without running any tools",
    dependencies=[Depends(get_current_user)],
)
async def explain_agent(
    request: AgentRunRequest,
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
) -> AgentExplainResponse:
    """Run the planner and verifier only; no state is persisted."""
    try:
        return await orchestrator.explain(request)
    except AgentExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/session/{session_id}",
    response_model=AgentSessionInfo,
    summary="Inspect the current state of an agent session",
)
async def get_agent_session(
    session_id: HexId,
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentSessionInfo:
    """Return a snapshot of the session's state."""
    try:
        return await orchestrator.get_session(session_id, owner_sub=current_user.sub)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
