"""Agent orchestrator — public entry point for Phase 9 (Phase 9).

Wraps the compiled LangGraph and exposes four operations:

run(request)        — start a new session; returns immediately whether done or suspended
resume(id, approved)— resume a suspended (CRUD approval) session
explain(request)    — run planner+verifier only; return the plan without executing tools
get_session(id)     — inspect current state of any live session
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from langgraph.types import Command

from app.core.exceptions import AgentExecutionError, ValidationError
from app.schemas.agent import (
    AgentApproveRequest,
    AgentExplainResponse,
    AgentRunRequest,
    AgentRunResponse,
    AgentSessionInfo,
    AgentStatus,
    PendingApproval,
    PlannedToolCall,
    ToolResult,
)

logger = logging.getLogger(__name__)

# LangGraph checkpoint config key
_THREAD_KEY = "thread_id"


def _thread_config(session_id: str) -> dict[str, Any]:
    return {"configurable": {_THREAD_KEY: session_id}}


def _extract_pending_approval(result: dict[str, Any]) -> PendingApproval | None:
    """Pull the interrupt payload out of a LangGraph result dict."""
    interrupts = result.get("__interrupt__", [])
    if not interrupts:
        return None
    value = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
    if not isinstance(value, dict):
        return None
    return PendingApproval(
        session_id=value.get("session_id", ""),
        step_index=value.get("step_index", 0),
        step_label=value.get("step_label", ""),
        preview=value.get("preview", {}),
    )


def _build_run_response(
    session_id: str,
    result: dict[str, Any],
) -> AgentRunResponse:
    """Convert a raw LangGraph result dict into an AgentRunResponse."""
    pending = _extract_pending_approval(result)
    status = AgentStatus.SUSPENDED if pending else AgentStatus(
        result.get("status", AgentStatus.DONE.value)
    )

    raw_results = result.get("results", [])
    completed_steps = [ToolResult(**r) for r in raw_results if isinstance(r, dict)]

    return AgentRunResponse(
        session_id=session_id,
        status=status,
        final_answer=result.get("final_answer"),
        completed_steps=completed_steps,
        pending_approval=pending,
        error=result.get("error") if status == AgentStatus.FAILED else None,
    )


class AgentOrchestrator:
    """Facade over the compiled LangGraph agent graph."""

    def __init__(self, graph: Any, planner: Any, max_retries: int = 2) -> None:
        self._graph = graph
        self._planner = planner   # exposed for set_client() wiring in lifespan
        self._default_max_retries = max_retries

    # ------------------------------------------------------------------ #
    # Run
    # ------------------------------------------------------------------ #

    async def run(self, request: AgentRunRequest, owner_sub: str = "") -> AgentRunResponse:
        """Start a new agent session.

        Returns immediately — the session may be ``done``, ``suspended``
        (waiting for CRUD approval), or ``failed``.
        """
        session_id = uuid.uuid4().hex
        config = _thread_config(session_id)

        history: list[dict[str, Any]] = [{"goal": c} for c in request.context]

        initial_state: dict[str, Any] = {
            "session_id": session_id,
            "user_goal": request.question,
            "dataset_id": request.dataset_id,
            "connection_id": request.connection_id,
            "explain_only": False,
            "plan": [],
            "current_step": 0,
            "results": [],
            "retry_count": 0,
            "max_retries": request.max_retries,
            "status": AgentStatus.RUNNING.value,
            "final_answer": None,
            "error": None,
            "conversation_history": history,
            "owner_sub": owner_sub,
        }

        try:
            result = await self._graph.ainvoke(initial_state, config=config)
        except Exception as exc:
            logger.error("Agent session %s failed: %s", session_id, exc)
            raise AgentExecutionError(f"Agent execution failed: {exc}") from exc

        return _build_run_response(session_id, result)

    # ------------------------------------------------------------------ #
    # Resume
    # ------------------------------------------------------------------ #

    async def resume(
        self, session_id: str, request: AgentApproveRequest, owner_sub: str = ""
    ) -> AgentRunResponse:
        """Resume a suspended session after the user approves or rejects a CRUD operation."""
        config = _thread_config(session_id)

        # Verify the session exists and is suspended; enforce ownership
        try:
            state = await self._graph.aget_state(config)
        except Exception as exc:
            raise ValidationError(f"Session '{session_id}' not found: {exc}") from exc

        if not state.next:
            raise ValidationError(
                f"Session '{session_id}' is not suspended and cannot be resumed."
            )

        # Ownership check — return 404 (not 403) to avoid leaking session existence
        stored_owner = state.values.get("owner_sub", "")
        if owner_sub and stored_owner and stored_owner != owner_sub:
            raise ValidationError(f"Session '{session_id}' not found.")

        try:
            result = await self._graph.ainvoke(
                Command(resume=request.approved), config=config
            )
        except Exception as exc:
            logger.error("Resume of session %s failed: %s", session_id, exc)
            raise AgentExecutionError(f"Resume failed: {exc}") from exc

        return _build_run_response(session_id, result)

    # ------------------------------------------------------------------ #
    # Explain
    # ------------------------------------------------------------------ #

    async def explain(self, request: AgentRunRequest) -> AgentExplainResponse:
        """Run planner + verifier only; return the plan without executing any tools."""
        session_id = uuid.uuid4().hex
        config = _thread_config(session_id)

        initial_state: dict[str, Any] = {
            "session_id": session_id,
            "user_goal": request.question,
            "dataset_id": request.dataset_id,
            "connection_id": request.connection_id,
            "explain_only": True,
            "plan": [],
            "current_step": 0,
            "results": [],
            "retry_count": 0,
            "max_retries": request.max_retries,
            "status": AgentStatus.RUNNING.value,
            "final_answer": None,
            "error": None,
            "conversation_history": [{"goal": c} for c in request.context],
        }

        try:
            result = await self._graph.ainvoke(initial_state, config=config)
        except Exception as exc:
            logger.error("Explain session %s failed: %s", session_id, exc)
            return AgentExplainResponse(
                session_id=session_id,
                plan=[],
                plan_valid=False,
                error=str(exc),
            )

        error = result.get("error")
        plan_dicts = result.get("plan", [])
        plan_valid = not bool(error)

        plan = []
        for raw in plan_dicts:
            try:
                plan.append(PlannedToolCall(**raw))
            except Exception:
                pass  # best-effort; schema mismatch won't crash explain

        return AgentExplainResponse(
            session_id=session_id,
            plan=plan,
            plan_valid=plan_valid,
            error=error,
        )

    # ------------------------------------------------------------------ #
    # Get session
    # ------------------------------------------------------------------ #

    async def get_session(self, session_id: str, owner_sub: str = "") -> AgentSessionInfo:
        """Return a snapshot of the current session state."""
        config = _thread_config(session_id)
        try:
            snapshot = await self._graph.aget_state(config)
        except Exception as exc:
            raise ValidationError(f"Session '{session_id}' not found: {exc}") from exc

        # LangGraph returns an empty snapshot (not an exception) for unknown thread IDs
        if not snapshot.values:
            raise ValidationError(f"Session '{session_id}' not found.")

        # Ownership check — 404 to avoid leaking session existence
        stored_owner = snapshot.values.get("owner_sub", "")
        if owner_sub and stored_owner and stored_owner != owner_sub:
            raise ValidationError(f"Session '{session_id}' not found.")

        state: dict[str, Any] = snapshot.values or {}
        plan = state.get("plan", [])
        results = state.get("results", [])
        current_step = state.get("current_step", 0)

        # Determine status
        is_suspended = bool(snapshot.next)
        raw_status = state.get("status", AgentStatus.RUNNING.value)
        if is_suspended:
            status = AgentStatus.SUSPENDED
        else:
            try:
                status = AgentStatus(raw_status)
            except ValueError:
                status = AgentStatus.RUNNING

        # Build pending approval if suspended
        pending: PendingApproval | None = None
        if is_suspended:
            for task in snapshot.tasks:
                for intr in task.interrupts:
                    iv = intr.value if hasattr(intr, "value") else intr
                    if isinstance(iv, dict) and iv.get("type") == "crud_approval":
                        pending = PendingApproval(
                            session_id=session_id,
                            step_index=iv.get("step_index", 0),
                            step_label=iv.get("step_label", ""),
                            preview=iv.get("preview", {}),
                        )
                        break

        completed = [ToolResult(**r) for r in results if isinstance(r, dict)]

        return AgentSessionInfo(
            session_id=session_id,
            status=status,
            user_goal=state.get("user_goal", ""),
            current_step=current_step,
            total_steps=len(plan),
            completed_results=completed,
            pending_approval=pending,
            final_answer=state.get("final_answer"),
            error=state.get("error"),
        )
