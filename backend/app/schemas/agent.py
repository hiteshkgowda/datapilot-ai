"""Pydantic schemas and LangGraph TypedDict state for the agent layer (Phase 9).

API schemas (Pydantic BaseModel) are used only at the HTTP boundary.
AgentState (TypedDict) is used exclusively inside the LangGraph graph so that
LangGraph's MemorySaver can checkpoint it without custom serialisation.

Stored lists (``results``) use ``Annotated[list, operator.add]`` so that
each executor node appends its result rather than replacing the full list.
"""

from __future__ import annotations

import operator
from enum import Enum
from typing import Annotated, Any, Optional, TypedDict

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    RUNNING = "running"
    SUSPENDED = "suspended"   # waiting for human CRUD approval
    DONE = "done"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Plan and result types (stored as plain dicts inside AgentState)
# ---------------------------------------------------------------------------

class PlannedToolCall(BaseModel):
    """One step in the agent execution plan, emitted by the LLM planner."""

    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    step_label: str = Field(..., min_length=1)
    requires_approval: bool = False


class ToolResult(BaseModel):
    """The output produced by one executed tool call."""

    tool_name: str
    step_label: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0


class PendingApproval(BaseModel):
    """Surfaced to the caller when a CRUD operation is waiting for approval."""

    session_id: str
    step_index: int
    step_label: str
    preview: dict[str, Any]     # CrudPreviewResponse serialised as dict


# ---------------------------------------------------------------------------
# LangGraph graph state (TypedDict — must remain JSON-serialisable)
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """Mutable state threaded through every node in the agent graph.

    All values must be JSON-serialisable so MemorySaver can checkpoint them.
    Pydantic models are converted to dicts before storing here.
    """

    # ── Inputs ──────────────────────────────────────────────────────────────
    session_id: str
    user_goal: str
    dataset_id: Optional[str]
    connection_id: Optional[str]
    explain_only: bool              # when True, planner+verifier run but no tools execute

    # ── Plan ────────────────────────────────────────────────────────────────
    plan: list[dict]                # list of PlannedToolCall dicts
    current_step: int               # index of next step to execute

    # ── Execution (append-only via operator.add reducer) ────────────────────
    results: Annotated[list[dict], operator.add]   # list of ToolResult dicts

    # ── Control flow ────────────────────────────────────────────────────────
    retry_count: int
    max_retries: int
    status: str                     # AgentStatus value

    # ── Output ──────────────────────────────────────────────────────────────
    final_answer: Optional[str]
    error: Optional[str]

    # ── Memory ──────────────────────────────────────────────────────────────
    conversation_history: list[dict]   # prior turns injected into the planner prompt


# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------

class AgentRunRequest(BaseModel):
    """Client request to start a new agent session."""

    question: str = Field(..., min_length=1)
    dataset_id: Optional[str] = Field(default=None, min_length=1)
    connection_id: Optional[str] = Field(default=None, min_length=1)
    context: list[str] = Field(
        default_factory=list,
        description="Prior conversation lines for session memory (optional).",
    )
    max_retries: int = Field(default=2, ge=0, le=5)


class AgentRunResponse(BaseModel):
    """Response for /agent/run and /agent/resume."""

    session_id: str
    status: AgentStatus
    final_answer: Optional[str] = None
    completed_steps: list[ToolResult] = Field(default_factory=list)
    pending_approval: Optional[PendingApproval] = None
    error: Optional[str] = None


class AgentApproveRequest(BaseModel):
    """Client request to approve or reject a suspended CRUD operation."""

    approved: bool


class AgentExplainResponse(BaseModel):
    """Response for /agent/explain — returns the plan without executing tools."""

    session_id: str
    plan: list[PlannedToolCall]
    plan_valid: bool
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class AgentSessionInfo(BaseModel):
    """Snapshot of an active or completed session, returned by GET /agent/session/{id}."""

    session_id: str
    status: AgentStatus
    user_goal: str
    current_step: int
    total_steps: int
    completed_results: list[ToolResult] = Field(default_factory=list)
    pending_approval: Optional[PendingApproval] = None
    final_answer: Optional[str] = None
    error: Optional[str] = None
