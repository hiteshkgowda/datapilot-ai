"""Agent orchestration routes (Phase 9).

Routes:
    POST /agent/run                     — start a new agent session
    POST /agent/resume/{session_id}     — resume a suspended (CRUD approval) session
    POST /agent/explain                 — return the execution plan without running tools
    GET  /agent/session/{session_id}    — inspect a session's current state
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.dependencies import (
    get_agent_orchestrator,
    get_connection_service,
    get_dataset_service,
    get_memory_service,
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
from app.core.rate_limit import _dynamic_limit, limiter
from app.schemas.agent import (
    AgentApproveRequest,
    AgentExplainResponse,
    AgentRunRequest,
    AgentRunResponse,
    AgentSessionInfo,
)
from app.schemas.auth import CurrentUser
from app.schemas.memory import TurnType
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.connection_service import ConnectionService
from app.services.dataset_service import DatasetService
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)


def _check_resource_ownership(
    body: AgentRunRequest,
    datasets: DatasetService,
    connections: ConnectionService,
    owner_sub: str,
) -> None:
    """Raise 404 if the caller doesn't own the dataset or connection in the request."""
    if body.dataset_id:
        try:
            meta = datasets.get_metadata(body.dataset_id)
        except DatasetNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        if meta.owner_sub and meta.owner_sub != owner_sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    if body.connection_id:
        try:
            record = connections._read_record(body.connection_id)
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
@limiter.limit(_dynamic_limit)
async def run_agent(
    request: Request,
    body: AgentRunRequest,
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
    datasets: DatasetService = Depends(get_dataset_service),
    connections: ConnectionService = Depends(get_connection_service),
    memory: MemoryService = Depends(get_memory_service),
    current_user: CurrentUser = Depends(get_current_user),
    x_session_id: Optional[str] = Header(None, alias="X-Session-Id"),
) -> AgentRunResponse:
    """Start a new multi-step agent session.

    If X-Session-Id is provided, prior conversation turns are injected into the
    agent's conversation_history so it can resolve references like "forecast them"
    back to results from earlier in the session.
    """
    _check_resource_ownership(body, datasets, connections, current_user.sub)

    # Inject prior session context so the agent understands conversational references.
    if x_session_id:
        prior_context = await memory.build_agent_context(x_session_id, current_user.sub)
        if prior_context:
            # Prepend session history before any caller-supplied context.
            merged_context = [item["goal"] for item in prior_context] + list(body.context)
            body = body.model_copy(update={"context": merged_context})

    try:
        resp = await orchestrator.run(body, owner_sub=current_user.sub)
    except AgentPlanError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except AgentExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Record the completed agent turn (fire-and-forget).
    if x_session_id and resp.final_answer:
        asyncio.ensure_future(
            memory.record_turn(
                session_id=x_session_id,
                user_sub=current_user.sub,
                turn_type=TurnType.AGENT,
                dataset_id=body.dataset_id,
                question=body.question,
                answer=resp.final_answer,
                metadata={"session_id": resp.session_id, "status": resp.status.value},
            )
        )

    return resp


@router.post(
    "/resume/{session_id}",
    response_model=AgentRunResponse,
    summary="Resume a suspended agent session after CRUD approval",
)
@limiter.limit(_dynamic_limit)
async def resume_agent(
    request: Request,
    session_id: HexId,
    body: AgentApproveRequest,
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
    current_user: CurrentUser = Depends(get_current_user),
) -> AgentRunResponse:
    """Resume a session that was paused for CRUD approval."""
    try:
        return await orchestrator.resume(session_id, body, owner_sub=current_user.sub)
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
@limiter.limit(_dynamic_limit)
async def explain_agent(
    request: Request,
    body: AgentRunRequest,
    orchestrator: AgentOrchestrator = Depends(get_agent_orchestrator),
) -> AgentExplainResponse:
    """Run the planner and verifier only; no state is persisted."""
    try:
        return await orchestrator.explain(body)
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
