"""Integration tests for the agent graph (planner → verifier → executor → aggregator).

Uses FakePlanner and FakeToolRegistry so no LLM or real service is called.
Tests cover:
  - happy path (multi-step chain completes)
  - explain_only mode
  - all four verifier complexity guards
  - CRUD approval: suspend, approve, reject
  - recovery: single retry succeeds, max retries exhausted
  - orchestrator run/resume/explain/get_session wrappers
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import Settings
from app.schemas.agent import AgentApproveRequest, AgentRunRequest, AgentStatus
from app.services.agent_graph import build_agent_graph
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.agent_tools import AgentTool, ToolRegistry


# ------------------------------------------------------------------ #
# Fakes
# ------------------------------------------------------------------ #

class FakePlanner:
    """Returns a pre-configured plan list; never calls an LLM."""

    def __init__(self, plan: list[dict]) -> None:
        self._plan = plan
        self._replan: list[dict] = []

    def set_replan(self, replan: list[dict]) -> None:
        self._replan = replan

    async def generate_plan(self, goal, tool_schemas, dataset_id, connection_id, conversation_history):
        return list(self._plan)

    async def replan(self, goal, tool_schemas, completed_results, failed_step, error, remaining_steps):
        return list(self._replan)


class FakeTool:
    """Always succeeds and records calls."""

    def __init__(self, name: str, output: dict | None = None, error: Exception | None = None) -> None:
        self.name = name
        self.description = f"Fake {name}"
        self.input_schema: dict = {}
        self.requires_approval = False
        self._output = output or {"answer": f"{name} done"}
        self._error = error
        self.calls: list[dict] = []

    async def execute(self, arguments: dict, state: dict) -> dict:
        self.calls.append({"arguments": arguments, "state_keys": list(state.keys())})
        if self._error:
            raise self._error
        return dict(self._output)


class FakeCrudPreviewTool(FakeTool):
    """Simulates a crud_preview that requires confirmation."""

    def __init__(self, requires_confirmation: bool = True) -> None:
        super().__init__("crud_preview")
        self.requires_approval = True
        self._requires_confirmation = requires_confirmation

    async def execute(self, arguments: dict, state: dict) -> dict:
        self.calls.append(arguments)
        return {
            "answer": "Preview: update orders",
            "requires_confirmation": self._requires_confirmation,
            "confirmation_token": "tok-abc" if self._requires_confirmation else None,
            "connection_id": "conn1",
            "operation": "update",
            "table_name": "orders",
            "affected_row_count": 5,
            "rollback_supported": True,
            "warnings": [],
            "plan": {"operation": "update", "table_name": "orders"},
        }


class FakeCrudExecuteTool(FakeTool):
    def __init__(self) -> None:
        super().__init__("crud_execute")

    async def execute(self, arguments: dict, state: dict) -> dict:
        self.calls.append(arguments)
        return {
            "answer": "Executed update on orders: 5 rows affected.",
            "operation": "update",
            "table_name": "orders",
            "affected_rows": 5,
            "rollback_token": "rb-xyz",
            "audit_id": "aud-001",
        }


def _make_registry(*tools: FakeTool) -> ToolRegistry:
    return ToolRegistry(list(tools))


def _make_settings(**kwargs: Any) -> Settings:
    defaults = dict(
        agent_max_tool_calls=10,
        agent_max_retries=2,
        agent_max_reports_per_run=1,
        agent_max_forecasts_per_run=1,
    )
    defaults.update(kwargs)
    return Settings(**defaults)


def _make_graph(planner: FakePlanner, registry: ToolRegistry, **settings_kwargs: Any):
    settings = _make_settings(**settings_kwargs)
    return build_agent_graph(tools=registry, planner=planner, settings=settings)


def _make_orchestrator(planner: FakePlanner, registry: ToolRegistry, **settings_kwargs: Any):
    graph = _make_graph(planner, registry, **settings_kwargs)
    return AgentOrchestrator(graph=graph, planner=planner, max_retries=2)


def _run_request(question: str = "analyse my data", **kwargs: Any) -> AgentRunRequest:
    return AgentRunRequest(question=question, dataset_id="ds1", **kwargs)


# ------------------------------------------------------------------ #
# Happy path
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_happy_path_two_steps():
    t1 = FakeTool("analytics")
    t2 = FakeTool("visualization")
    planner = FakePlanner([
        {"tool_name": "analytics",     "arguments": {"dataset_id": "ds1", "question": "sum?"}, "step_label": "analyse"},
        {"tool_name": "visualization", "arguments": {"dataset_id": "ds1", "question": "chart?"}, "step_label": "chart"},
    ])
    orch = _make_orchestrator(planner, _make_registry(t1, t2))
    resp = await orch.run(_run_request())

    assert resp.status == AgentStatus.DONE
    assert len(resp.completed_steps) == 2
    assert resp.final_answer is not None
    assert "analyse" in resp.final_answer or "analytics done" in resp.final_answer


@pytest.mark.anyio
async def test_single_step_completes():
    t = FakeTool("dataset_preview", output={"answer": "100 rows, 5 cols", "rows": 100, "columns": 5, "column_names": [], "preview_rows": []})
    planner = FakePlanner([
        {"tool_name": "dataset_preview", "arguments": {"dataset_id": "ds1"}, "step_label": "preview"},
    ])
    orch = _make_orchestrator(planner, _make_registry(t))
    resp = await orch.run(_run_request("preview my data"))
    assert resp.status == AgentStatus.DONE
    assert resp.completed_steps[0].tool_name == "dataset_preview"


# ------------------------------------------------------------------ #
# Explain-only mode
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_explain_returns_plan_without_executing():
    t = FakeTool("analytics")
    planner = FakePlanner([
        {"tool_name": "analytics", "arguments": {}, "step_label": "analyse"},
    ])
    orch = _make_orchestrator(planner, _make_registry(t))
    resp = await orch.explain(_run_request())

    assert resp.plan_valid is True
    assert len(resp.plan) == 1
    assert resp.plan[0].tool_name == "analytics"
    assert t.calls == []   # no tool was executed


@pytest.mark.anyio
async def test_explain_returns_error_for_invalid_plan():
    t = FakeTool("analytics")
    planner = FakePlanner([
        {"tool_name": "analytics", "arguments": {}, "step_label": "a"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "b"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "c"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "d"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "e"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "f"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "g"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "h"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "i"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "j"},
        {"tool_name": "analytics", "arguments": {}, "step_label": "k"},  # 11 steps
    ])
    orch = _make_orchestrator(planner, _make_registry(t), agent_max_tool_calls=10)
    resp = await orch.explain(_run_request())
    assert resp.plan_valid is False
    assert resp.error is not None


# ------------------------------------------------------------------ #
# Verifier guards
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_verifier_rejects_too_many_steps():
    t = FakeTool("analytics")
    steps = [{"tool_name": "analytics", "arguments": {}, "step_label": f"s{i}"} for i in range(11)]
    planner = FakePlanner(steps)
    orch = _make_orchestrator(planner, _make_registry(t), agent_max_tool_calls=10)
    resp = await orch.run(_run_request())
    assert resp.status == AgentStatus.FAILED
    assert resp.final_answer is not None


@pytest.mark.anyio
async def test_verifier_rejects_too_many_reports():
    t = FakeTool("report")
    planner = FakePlanner([
        {"tool_name": "report", "arguments": {}, "step_label": "r1"},
        {"tool_name": "report", "arguments": {}, "step_label": "r2"},
    ])
    orch = _make_orchestrator(planner, _make_registry(t), agent_max_reports_per_run=1)
    resp = await orch.run(_run_request())
    assert resp.status == AgentStatus.FAILED


@pytest.mark.anyio
async def test_verifier_rejects_too_many_forecasts():
    t = FakeTool("forecast")
    planner = FakePlanner([
        {"tool_name": "forecast", "arguments": {}, "step_label": "f1"},
        {"tool_name": "forecast", "arguments": {}, "step_label": "f2"},
    ])
    orch = _make_orchestrator(planner, _make_registry(t), agent_max_forecasts_per_run=1)
    resp = await orch.run(_run_request())
    assert resp.status == AgentStatus.FAILED


@pytest.mark.anyio
async def test_verifier_rejects_unknown_tool():
    planner = FakePlanner([
        {"tool_name": "does_not_exist", "arguments": {}, "step_label": "bad"},
    ])
    orch = _make_orchestrator(planner, _make_registry())
    resp = await orch.run(_run_request())
    assert resp.status == AgentStatus.FAILED


@pytest.mark.anyio
async def test_verifier_rejects_crud_execute_without_preview():
    execute_tool = FakeCrudExecuteTool()
    planner = FakePlanner([
        # crud_execute without a preceding crud_preview
        {"tool_name": "crud_execute", "arguments": {}, "step_label": "execute"},
    ])
    orch = _make_orchestrator(planner, _make_registry(execute_tool))
    resp = await orch.run(_run_request("delete rows"))
    assert resp.status == AgentStatus.FAILED


# ------------------------------------------------------------------ #
# CRUD approval gate
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_crud_approval_suspends_session():
    preview = FakeCrudPreviewTool(requires_confirmation=True)
    execute = FakeCrudExecuteTool()
    planner = FakePlanner([
        {"tool_name": "crud_preview", "arguments": {"question": "delete rows"}, "step_label": "preview"},
        {"tool_name": "crud_execute", "arguments": {}, "step_label": "execute"},
    ])
    orch = _make_orchestrator(planner, _make_registry(preview, execute))
    resp = await orch.run(_run_request("delete some rows"))

    assert resp.status == AgentStatus.SUSPENDED
    assert resp.pending_approval is not None
    assert resp.pending_approval.session_id == resp.session_id
    assert execute.calls == []  # execute not called yet


@pytest.mark.anyio
async def test_crud_approval_approve_completes():
    preview = FakeCrudPreviewTool(requires_confirmation=True)
    execute = FakeCrudExecuteTool()
    planner = FakePlanner([
        {"tool_name": "crud_preview", "arguments": {"question": "delete rows"}, "step_label": "preview"},
        {"tool_name": "crud_execute", "arguments": {}, "step_label": "execute"},
    ])
    orch = _make_orchestrator(planner, _make_registry(preview, execute))

    run_resp = await orch.run(_run_request("delete some rows"))
    assert run_resp.status == AgentStatus.SUSPENDED

    resume_resp = await orch.resume(run_resp.session_id, AgentApproveRequest(approved=True))
    assert resume_resp.status == AgentStatus.DONE
    assert len(execute.calls) == 1
    # confirmation_token should have been auto-injected from crud_preview result
    assert execute.calls[0].get("confirmation_token") == "tok-abc"


@pytest.mark.anyio
async def test_crud_approval_reject_triggers_recovery():
    preview = FakeCrudPreviewTool(requires_confirmation=True)
    execute = FakeCrudExecuteTool()
    analytics = FakeTool("analytics")
    planner = FakePlanner([
        {"tool_name": "crud_preview", "arguments": {"question": "delete rows"}, "step_label": "preview"},
        {"tool_name": "crud_execute", "arguments": {}, "step_label": "execute"},
    ])
    # Recovery replans to analytics only
    planner.set_replan([
        {"tool_name": "analytics", "arguments": {"dataset_id": "ds1", "question": "count?"}, "step_label": "count"},
    ])
    orch = _make_orchestrator(planner, _make_registry(preview, execute, analytics))

    run_resp = await orch.run(_run_request("delete some rows"))
    assert run_resp.status == AgentStatus.SUSPENDED

    resume_resp = await orch.resume(run_resp.session_id, AgentApproveRequest(approved=False))
    assert execute.calls == []   # CRUD execute never ran
    # Recovery ran analytics instead
    assert any(s.tool_name == "analytics" for s in resume_resp.completed_steps)


@pytest.mark.anyio
async def test_crud_no_confirmation_needed_skips_approval_gate():
    """When crud_preview returns requires_confirmation=False, graph skips the gate."""
    preview = FakeCrudPreviewTool(requires_confirmation=False)
    execute = FakeCrudExecuteTool()
    planner = FakePlanner([
        {"tool_name": "crud_preview", "arguments": {"question": "update amount"}, "step_label": "preview"},
        {"tool_name": "crud_execute", "arguments": {}, "step_label": "execute"},
    ])
    orch = _make_orchestrator(planner, _make_registry(preview, execute))
    resp = await orch.run(_run_request("update amount=99 for id=1"))
    assert resp.status == AgentStatus.DONE
    assert len(execute.calls) == 1


# ------------------------------------------------------------------ #
# Recovery
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_recovery_replans_on_tool_error():
    failing = FakeTool("analytics", error=RuntimeError("LLM timeout"))
    fallback = FakeTool("dataset_preview", output={"answer": "100 rows", "rows": 100, "columns": 5, "column_names": [], "preview_rows": []})
    planner = FakePlanner([
        {"tool_name": "analytics", "arguments": {}, "step_label": "analyse"},
    ])
    # After analytics fails, replan to dataset_preview
    planner.set_replan([
        {"tool_name": "dataset_preview", "arguments": {"dataset_id": "ds1"}, "step_label": "fallback preview"},
    ])
    orch = _make_orchestrator(planner, _make_registry(failing, fallback))
    resp = await orch.run(_run_request())

    # Should complete after recovery
    assert resp.status == AgentStatus.DONE
    names = [s.tool_name for s in resp.completed_steps]
    assert "dataset_preview" in names


@pytest.mark.anyio
async def test_max_retries_exhausted_returns_partial():
    failing = FakeTool("analytics", error=RuntimeError("always fails"))
    planner = FakePlanner([
        {"tool_name": "analytics", "arguments": {}, "step_label": "step1"},
    ])
    # replan always returns the same failing step → retries exhaust
    planner.set_replan([
        {"tool_name": "analytics", "arguments": {}, "step_label": "retry1"},
    ])
    orch = _make_orchestrator(planner, _make_registry(failing), agent_max_retries=2)
    resp = await orch.run(AgentRunRequest(question="do analysis", max_retries=2))

    assert resp.status in (AgentStatus.FAILED, AgentStatus.DONE)
    assert resp.final_answer is not None  # partial answer always returned


# ------------------------------------------------------------------ #
# Orchestrator get_session
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_get_session_after_completion():
    t = FakeTool("analytics")
    planner = FakePlanner([
        {"tool_name": "analytics", "arguments": {}, "step_label": "analyse"},
    ])
    orch = _make_orchestrator(planner, _make_registry(t))
    run_resp = await orch.run(_run_request())

    info = await orch.get_session(run_resp.session_id)
    assert info.session_id == run_resp.session_id
    assert info.status == AgentStatus.DONE
    assert info.total_steps == 1


@pytest.mark.anyio
async def test_get_session_unknown_id_raises():
    from app.core.exceptions import ValidationError
    t = FakeTool("analytics")
    planner = FakePlanner([])
    orch = _make_orchestrator(planner, _make_registry(t))
    with pytest.raises(ValidationError):
        await orch.get_session("non-existent-session-id")


# anyio backend — asyncio only
@pytest.fixture(params=["asyncio"])
def anyio_backend():
    return "asyncio"
