"""LangGraph StateGraph for the agent orchestration layer (Phase 9).

Graph topology
--------------
START → planner → verifier → executor ──► approval_gate ──► executor
                       │          │                │ (rejected)
                       │          └── recovery ◄───┘
                       │ (explain)      │
                       └──► aggregator ◄┘ (done / max-retries)
                                │
                               END

Node responsibilities
---------------------
planner       — calls the LLM to produce an ordered plan array
verifier      — enforces complexity guards; routes explain-only requests
executor      — executes one tool at a time; auto-injects CRUD tokens
approval_gate — pauses via interrupt() for human CRUD approval
recovery      — asks the LLM to replan remaining steps; bounded retries
aggregator    — synthesises the final answer from all tool results

No business logic lives in this file.  Every tool call is delegated to
the ToolRegistry; every LLM call is delegated to the AgentPlanner.
"""

from __future__ import annotations

import logging
import time
from functools import partial
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.core.config import Settings
from app.schemas.agent import AgentState, AgentStatus
from app.services.agent_planner import AgentPlanner
from app.services.agent_tools import ToolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_confirmation_token(results: list[dict[str, Any]]) -> str | None:
    """Return the confirmation_token from the most recent crud_preview result."""
    for result in reversed(results):
        if result.get("tool_name") == "crud_preview":
            return result.get("output", {}).get("confirmation_token")
    return None


def _find_crud_preview_output(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the output dict from the most recent crud_preview result."""
    for result in reversed(results):
        if result.get("tool_name") == "crud_preview":
            return result.get("output", {})
    return None


def _summarise_results(results: list[dict[str, Any]]) -> str:
    parts = []
    for r in results:
        answer = r.get("output", {}).get("answer", "")
        err = r.get("error", "")
        label = r.get("step_label", r.get("tool_name", "?"))
        if err:
            parts.append(f"[{label}] ERROR: {err}")
        elif answer:
            parts.append(f"[{label}] {answer}")
    return "\n".join(parts) or "No results."


# ---------------------------------------------------------------------------
# Node: planner
# ---------------------------------------------------------------------------

async def _planner_node(
    state: AgentState,
    *,
    planner: AgentPlanner,
    tools: ToolRegistry,
) -> dict[str, Any]:
    """Ask the LLM to plan tool calls or produce a direct conversational reply."""
    try:
        result = await planner.generate_plan(
            goal=state["user_goal"],
            tool_schemas=tools.schemas(),
            dataset_id=state.get("dataset_id"),
            connection_id=state.get("connection_id"),
            conversation_history=state.get("conversation_history", []),
        )
    except Exception as exc:
        logger.error("Planner failed: %s", exc)
        return {
            "plan": [],
            "current_step": 0,
            "status": AgentStatus.FAILED.value,
            "error": f"Planning failed: {exc}",
        }

    # Conversational reply — skip all tool execution.
    if result.get("type") == "chat":
        return {
            "plan": [],
            "current_step": 0,
            "status": AgentStatus.DONE.value,
            "final_answer": result["message"],
            "error": None,
        }

    # Tool plan — proceed to verifier → executor.
    return {
        "plan": result.get("steps", []),
        "current_step": 0,
        "status": AgentStatus.RUNNING.value,
        "error": None,
    }


def _planner_router(state: AgentState) -> str:
    status = state.get("status")
    if status == AgentStatus.FAILED.value:
        return "aggregator"
    if status == AgentStatus.DONE.value:
        # Planner produced a direct chat reply — skip tool execution entirely.
        return "aggregator"
    return "verifier"


# ---------------------------------------------------------------------------
# Node: verifier
# ---------------------------------------------------------------------------

def _verifier_node(
    state: AgentState,
    *,
    tools: ToolRegistry,
    settings: Settings,
) -> dict[str, Any]:
    """Enforce complexity guards and validate tool names."""
    plan = state.get("plan", [])
    errors: list[str] = []
    warnings: list[str] = []

    # Guard 1 — max tool calls
    if len(plan) > settings.agent_max_tool_calls:
        errors.append(
            f"Plan has {len(plan)} steps; maximum is {settings.agent_max_tool_calls}."
        )

    # Guard 2 — max reports per run
    report_count = sum(1 for s in plan if s.get("tool_name") == "report")
    if report_count > settings.agent_max_reports_per_run:
        errors.append(
            f"Plan contains {report_count} 'report' steps; "
            f"maximum is {settings.agent_max_reports_per_run}."
        )

    # Guard 3 — max forecasts per run
    forecast_count = sum(1 for s in plan if s.get("tool_name") == "forecast")
    if forecast_count > settings.agent_max_forecasts_per_run:
        errors.append(
            f"Plan contains {forecast_count} 'forecast' steps; "
            f"maximum is {settings.agent_max_forecasts_per_run}."
        )

    # Guard 4 — all tool names must exist in registry
    valid_names = set(tools.names())
    for i, step in enumerate(plan):
        name = step.get("tool_name", "")
        if name not in valid_names:
            errors.append(f"Step {i}: unknown tool '{name}'.")

    # Guard 5 — crud_execute must be preceded immediately by crud_preview
    for i, step in enumerate(plan):
        if step.get("tool_name") == "crud_execute":
            if i == 0 or plan[i - 1].get("tool_name") != "crud_preview":
                errors.append(
                    f"Step {i}: 'crud_execute' must be immediately preceded by 'crud_preview'."
                )

    # Safety: CRUD write without mutation intent in goal
    goal_lower = state["user_goal"].lower()
    _MUTATION_WORDS = {
        "create", "insert", "add", "update", "change", "edit", "set",
        "delete", "remove", "drop", "soft delete", "modify", "upsert",
    }
    has_crud_write = any(s.get("tool_name") == "crud_execute" for s in plan)
    has_mutation_intent = any(w in goal_lower for w in _MUTATION_WORDS)
    if has_crud_write and not has_mutation_intent:
        warnings.append(
            "Plan includes a CRUD write but the goal does not contain clear mutation intent. "
            "Proceeding, but please verify the plan."
        )

    if errors:
        logger.warning("Plan verification failed: %s", errors)
        return {
            "error": "; ".join(errors),
            "status": AgentStatus.FAILED.value,
        }

    for w in warnings:
        logger.warning("Plan verification warning: %s", w)
    return {}


def _verifier_router(state: AgentState) -> str:
    if state.get("status") == AgentStatus.FAILED.value:
        return "aggregator"
    if state.get("explain_only"):
        return "aggregator"
    return "executor"


# ---------------------------------------------------------------------------
# Node: executor
# ---------------------------------------------------------------------------

async def _executor_node(
    state: AgentState,
    *,
    tools: ToolRegistry,
) -> dict[str, Any]:
    """Execute one tool step and return the result."""
    plan = state["plan"]
    step_index = state["current_step"]

    if step_index >= len(plan):
        return {"status": AgentStatus.DONE.value}

    raw_step = plan[step_index]
    tool_name = raw_step.get("tool_name", "")
    step_label = raw_step.get("step_label", tool_name)
    arguments = dict(raw_step.get("arguments") or {})

    # Auto-inject confirmation_token for crud_execute from the prior crud_preview result
    if tool_name == "crud_execute":
        token = _find_confirmation_token(state["results"])
        if token:
            arguments["confirmation_token"] = token
        # Also auto-inject connection_id and plan from the crud_preview output if not present
        preview_out = _find_crud_preview_output(state["results"])
        if preview_out:
            if "connection_id" not in arguments or not arguments["connection_id"]:
                arguments["connection_id"] = preview_out.get("connection_id")
            if "plan" not in arguments or not arguments["plan"]:
                arguments["plan"] = preview_out.get("plan")

    t0 = time.monotonic()
    try:
        tool = tools.get(tool_name)
        output = await tool.execute(arguments, dict(state))
        duration_ms = round((time.monotonic() - t0) * 1000, 2)
        result = {
            "tool_name": tool_name,
            "step_label": step_label,
            "output": output,
            "error": None,
            "duration_ms": duration_ms,
        }
        return {
            "results": [result],
            "current_step": step_index + 1,
            "error": None,
        }
    except Exception as exc:
        duration_ms = round((time.monotonic() - t0) * 1000, 2)
        logger.warning("Tool '%s' failed at step %d: %s", tool_name, step_index, exc)
        result = {
            "tool_name": tool_name,
            "step_label": step_label,
            "output": {},
            "error": str(exc),
            "duration_ms": duration_ms,
        }
        return {
            "results": [result],
            "current_step": step_index + 1,
            "error": str(exc),
        }


def _executor_router(state: AgentState) -> str:
    if state.get("error"):
        return "recovery"

    # Check if we just ran a crud_preview that needs human approval
    results = state.get("results", [])
    if results:
        last = results[-1]
        if (
            last.get("tool_name") == "crud_preview"
            and last.get("output", {}).get("requires_confirmation")
        ):
            return "approval_gate"

    # All steps done?
    if state["current_step"] >= len(state.get("plan", [])):
        return "aggregator"

    return "executor"


# ---------------------------------------------------------------------------
# Node: approval_gate
# ---------------------------------------------------------------------------

def _approval_gate_node(state: AgentState) -> dict[str, Any]:
    """Pause graph execution until the user approves or rejects the CRUD operation."""
    preview_output = _find_crud_preview_output(state["results"]) or {}
    step_index = state["current_step"] - 1  # preview was the previous step
    step_label = ""
    if 0 <= step_index < len(state.get("plan", [])):
        step_label = state["plan"][step_index].get("step_label", "")

    # interrupt() saves graph state and surfaces the value to the caller.
    # On resume, the return value is what the caller passed to Command(resume=...).
    approved: bool = interrupt(
        {
            "type": "crud_approval",
            "session_id": state["session_id"],
            "step_index": step_index,
            "step_label": step_label,
            "preview": preview_output,
        }
    )

    if approved:
        return {"error": None, "status": AgentStatus.RUNNING.value}
    return {
        "error": "User rejected the CRUD operation.",
        "retry_count": state.get("retry_count", 0) + 1,
    }


def _approval_gate_router(state: AgentState) -> str:
    if state.get("error"):
        return "recovery"
    return "executor"


# ---------------------------------------------------------------------------
# Node: recovery
# ---------------------------------------------------------------------------

async def _recovery_node(
    state: AgentState,
    *,
    planner: AgentPlanner,
    tools: ToolRegistry,
) -> dict[str, Any]:
    """Attempt to replan the remaining steps; give up after max_retries."""
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    if retry_count >= max_retries:
        logger.warning(
            "Session %s exhausted %d retries. Giving up.", state["session_id"], max_retries
        )
        completed_summary = _summarise_results(state["results"])
        return {
            "status": AgentStatus.FAILED.value,
            "final_answer": (
                f"I completed {len(state['results'])} step(s) before encountering "
                f"an unrecoverable error: {state.get('error', 'unknown')}.\n\n"
                f"Partial results:\n{completed_summary}"
            ),
        }

    plan = state.get("plan", [])
    current_step = state.get("current_step", 0)
    failed_step_index = max(current_step - 1, 0)
    failed_step = plan[failed_step_index] if failed_step_index < len(plan) else {}
    remaining_steps = plan[current_step:]

    try:
        new_remaining = await planner.replan(
            goal=state["user_goal"],
            tool_schemas=tools.schemas(),
            completed_results=state.get("results", []),
            failed_step=failed_step,
            error=state.get("error", ""),
            remaining_steps=remaining_steps,
        )
    except Exception as exc:
        logger.error("Replanning failed: %s", exc)
        return {
            "status": AgentStatus.FAILED.value,
            "error": f"Replanning failed: {exc}",
            "retry_count": retry_count + 1,
        }

    revised_plan = plan[:current_step] + new_remaining
    return {
        "plan": revised_plan,
        "error": None,
        "retry_count": retry_count + 1,
    }


def _recovery_router(state: AgentState) -> str:
    if state.get("status") in (AgentStatus.FAILED.value, AgentStatus.DONE.value):
        return "aggregator"
    if state.get("error"):
        return "aggregator"
    return "executor"


# ---------------------------------------------------------------------------
# Node: aggregator
# ---------------------------------------------------------------------------

def _aggregator_node(state: AgentState) -> dict[str, Any]:
    """Synthesise a final natural-language answer from all tool results."""
    results = state.get("results", [])
    explain_only = state.get("explain_only", False)
    current_status = state.get("status", AgentStatus.RUNNING.value)

    # Use `or` fallback instead of dict default so an explicit None in state
    # doesn't bypass the fallback string.
    def _error_msg(default: str) -> str:
        return state.get("error") or default

    # Preserve FAILED status set by planner/verifier/recovery — do not overwrite with DONE.
    # When already FAILED with a final_answer (e.g. recovery exhausted retries), pass through.
    if current_status == AgentStatus.FAILED.value:
        existing_answer = state.get("final_answer")
        return {
            "final_answer": existing_answer or f"I couldn't complete that request: {_error_msg('an unexpected error occurred')}",
            "status": AgentStatus.FAILED.value,
        }

    if explain_only:
        # Return the verified plan as the final answer
        plan = state.get("plan", [])
        plan_text = "\n".join(
            f"  {i + 1}. [{s.get('tool_name')}] {s.get('step_label', '')}"
            for i, s in enumerate(plan)
        )
        return {
            "final_answer": f"Execution plan ({len(plan)} steps):\n{plan_text}",
            "status": AgentStatus.DONE.value,
        }

    if not results:
        # No tools ran. Two cases:
        # 1. Error during planning/verification — surface it.
        # 2. Empty plan (e.g. greeting or non-task input) — return a helpful prompt.
        error = state.get("error")
        if error:
            return {
                "final_answer": f"I couldn't complete that request: {error}",
                "status": AgentStatus.FAILED.value,
            }
        return {
            "final_answer": (
                "Hi! I'm your data assistant. I can help you explore datasets, "
                "run queries, generate charts, forecast time series, or create PDF reports. "
                "Try uploading a dataset and asking me a question about it!"
            ),
            "status": AgentStatus.DONE.value,
        }

    # Build a structured summary; each result contributes its "answer" field
    summary_parts: list[str] = []
    for r in results:
        label = r.get("step_label", r.get("tool_name", "?"))
        if r.get("error"):
            summary_parts.append(f"**{label}**: ⚠ {r['error']}")
        else:
            answer = r.get("output", {}).get("answer", "")
            if answer:
                summary_parts.append(f"**{label}**: {answer}")

    goal = state.get("user_goal", "")
    combined = "\n".join(summary_parts) or "No results."

    final_answer = f"Here is what I found for: *{goal}*\n\n{combined}"
    return {
        "final_answer": final_answer,
        "status": AgentStatus.DONE.value,
    }


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def build_agent_graph(
    *,
    tools: ToolRegistry,
    planner: AgentPlanner,
    settings: Settings,
    checkpointer: Any = None,
) -> Any:  # returns a compiled LangGraph
    """Build and compile the agent StateGraph.

    ``checkpointer`` must be a ready-to-use LangGraph checkpointer instance
    (e.g. ``SqliteSaver`` or ``MemorySaver``).  Connection lifecycle is the
    caller's responsibility.  When ``None`` a fresh ``MemorySaver`` is used
    (sessions are lost on restart — suitable for tests and local dev).
    """
    graph = StateGraph(AgentState)

    # ── Node registration ────────────────────────────────────────────────────
    graph.add_node("planner",       partial(_planner_node,  planner=planner, tools=tools))
    graph.add_node("verifier",      partial(_verifier_node, tools=tools, settings=settings))
    graph.add_node("executor",      partial(_executor_node, tools=tools))
    graph.add_node("approval_gate", _approval_gate_node)
    graph.add_node("recovery",      partial(_recovery_node, planner=planner, tools=tools))
    graph.add_node("aggregator",    _aggregator_node)

    # ── Edges ────────────────────────────────────────────────────────────────
    graph.add_edge(START, "planner")
    graph.add_conditional_edges("planner",       _planner_router,       {"aggregator": "aggregator", "verifier": "verifier"})
    graph.add_conditional_edges("verifier",      _verifier_router,      {"aggregator": "aggregator", "executor": "executor"})
    graph.add_conditional_edges("executor",      _executor_router,      {"executor": "executor", "approval_gate": "approval_gate", "aggregator": "aggregator", "recovery": "recovery"})
    graph.add_conditional_edges("approval_gate", _approval_gate_router, {"executor": "executor", "recovery": "recovery"})
    graph.add_conditional_edges("recovery",      _recovery_router,      {"executor": "executor", "aggregator": "aggregator"})
    graph.add_edge("aggregator", END)

    # ── Checkpointer ─────────────────────────────────────────────────────────
    return graph.compile(checkpointer=checkpointer or MemorySaver())
