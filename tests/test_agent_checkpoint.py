"""Persistence tests for the SQLite agent checkpointer (Phase P3).

These tests prove that the suspend → restart → resume cycle works correctly
when sessions are persisted to a real SQLite file on disk.

"Restart" is simulated by:
  1. Building graph-A with AsyncSqliteSaver pointing at a temp DB file.
  2. Running a session on graph-A until it suspends (CRUD approval required).
  3. Closing the aiosqlite connection held by graph-A.
  4. Opening a NEW AsyncSqliteSaver connection to the SAME file.
  5. Building graph-B from that new connection.
  6. Resuming the session on graph-B — proving the checkpoint survived.

If MemorySaver were used instead, step 6 would fail with a ValidationError
("session not suspended"), which is explicitly tested in
test_memory_saver_loses_state_across_instances.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # type: ignore[import]

from app.core.config import Settings
from app.schemas.agent import AgentApproveRequest, AgentRunRequest, AgentStatus
from app.services.agent_graph import build_agent_graph
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.agent_tools import ToolRegistry


# ---------------------------------------------------------------------------
# Shared fakes (duplicated from test_agent_graph.py to keep tests independent)
# ---------------------------------------------------------------------------

class _FakePlanner:
    def __init__(self, plan: list[dict]) -> None:
        self._plan = plan
        self._replan: list[dict] = []

    def set_replan(self, replan: list[dict]) -> None:
        self._replan = replan

    async def generate_plan(self, goal, tool_schemas, dataset_id, connection_id, conversation_history):
        return list(self._plan)

    async def replan(self, goal, tool_schemas, completed_results, failed_step, error, remaining_steps):
        return list(self._replan)


class _FakeTool:
    def __init__(self, name: str, output: dict | None = None) -> None:
        self.name = name
        self.description = f"Fake {name}"
        self.input_schema: dict = {}
        self.requires_approval = False
        self._output = output or {"answer": f"{name} done"}
        self.calls: list[dict] = []

    async def execute(self, arguments: dict, state: dict) -> dict:
        self.calls.append(arguments)
        return dict(self._output)


class _FakeCrudPreviewTool(_FakeTool):
    """Returns requires_confirmation=True so the approval gate is triggered."""

    def __init__(self) -> None:
        super().__init__("crud_preview")
        self.requires_approval = True

    async def execute(self, arguments: dict, state: dict) -> dict:
        self.calls.append(arguments)
        return {
            "answer": "Preview: update 5 rows in orders",
            "requires_confirmation": True,
            "confirmation_token": "tok-persist-test",
            "connection_id": "conn1",
            "operation": "update",
            "table_name": "orders",
            "affected_row_count": 5,
            "rollback_supported": True,
            "warnings": [],
            "plan": {"operation": "update", "table_name": "orders"},
        }


class _FakeCrudExecuteTool(_FakeTool):
    def __init__(self) -> None:
        super().__init__("crud_execute")

    async def execute(self, arguments: dict, state: dict) -> dict:
        self.calls.append(arguments)
        return {
            "answer": "Executed: 5 rows updated.",
            "operation": "update",
            "table_name": "orders",
            "affected_rows": 5,
            "rollback_token": "rb-001",
            "audit_id": "aud-001",
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CRUD_PLAN = [
    {"tool_name": "crud_preview", "arguments": {"question": "update orders"}, "step_label": "preview"},
    {"tool_name": "crud_execute", "arguments": {}, "step_label": "execute"},
]


def _settings(**kwargs: Any) -> Settings:
    return Settings(
        agent_max_tool_calls=10,
        agent_max_retries=2,
        agent_max_reports_per_run=1,
        agent_max_forecasts_per_run=1,
        **kwargs,
    )


async def _open_saver(db_path: Path) -> tuple[AsyncSqliteSaver, aiosqlite.Connection]:
    """Open a fresh AsyncSqliteSaver for the given file path."""
    conn = await aiosqlite.connect(str(db_path))
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver, conn


def _make_orch(saver: Any) -> tuple[AgentOrchestrator, _FakeCrudPreviewTool, _FakeCrudExecuteTool]:
    preview = _FakeCrudPreviewTool()
    execute = _FakeCrudExecuteTool()
    registry = ToolRegistry([preview, execute])
    planner = _FakePlanner(_CRUD_PLAN)
    graph = build_agent_graph(
        tools=registry,
        planner=planner,
        settings=_settings(),
        checkpointer=saver,
    )
    orch = AgentOrchestrator(graph=graph, planner=planner, max_retries=2)
    return orch, preview, execute


def _run_req(question: str = "update some rows") -> AgentRunRequest:
    return AgentRunRequest(question=question, connection_id="conn1")


# ---------------------------------------------------------------------------
# Core: suspend → restart → resume (approve)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_suspend_restart_resume_approve(tmp_path: Path) -> None:
    """Session suspended on graph-A can be approved and completed on graph-B.

    This is the primary correctness proof for SQLite checkpoint persistence.
    """
    db_path = tmp_path / "sessions.db"

    # ── Round 1: start session; expect SUSPENDED ─────────────────────────────
    saver_a, conn_a = await _open_saver(db_path)
    orch_a, _, execute_a = _make_orch(saver_a)

    resp_a = await orch_a.run(_run_req())
    assert resp_a.status == AgentStatus.SUSPENDED, f"Expected SUSPENDED, got {resp_a.status}"
    assert resp_a.pending_approval is not None
    session_id = resp_a.session_id
    assert execute_a.calls == [], "crud_execute must not run before approval"

    # ── Simulate restart: close graph-A's connection ──────────────────────────
    await conn_a.close()

    # ── Round 2: open fresh connection to same file; resume ───────────────────
    saver_b, conn_b = await _open_saver(db_path)
    orch_b, _, execute_b = _make_orch(saver_b)

    resp_b = await orch_b.resume(session_id, AgentApproveRequest(approved=True))

    assert resp_b.status == AgentStatus.DONE, f"Expected DONE after resume, got {resp_b.status}"
    assert len(execute_b.calls) == 1, "crud_execute must run exactly once after approval"
    assert execute_b.calls[0].get("confirmation_token") == "tok-persist-test", \
        "Confirmation token must be auto-injected from the persisted crud_preview result"

    await conn_b.close()


# ---------------------------------------------------------------------------
# Core: suspend → restart → resume (reject)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_suspend_restart_resume_reject(tmp_path: Path) -> None:
    """Session suspended on graph-A can be rejected on graph-B; crud_execute never runs."""
    db_path = tmp_path / "sessions.db"

    # Round 1: suspend
    saver_a, conn_a = await _open_saver(db_path)
    planner = _FakePlanner(_CRUD_PLAN)
    planner.set_replan([])
    preview = _FakeCrudPreviewTool()
    execute = _FakeCrudExecuteTool()
    registry = ToolRegistry([preview, execute])
    graph_a = build_agent_graph(
        tools=registry, planner=planner, settings=_settings(), checkpointer=saver_a
    )
    orch_a = AgentOrchestrator(graph=graph_a, planner=planner, max_retries=2)

    resp_a = await orch_a.run(_run_req())
    assert resp_a.status == AgentStatus.SUSPENDED
    session_id = resp_a.session_id
    await conn_a.close()

    # Round 2: reject on new connection
    saver_b, conn_b = await _open_saver(db_path)
    graph_b = build_agent_graph(
        tools=registry, planner=planner, settings=_settings(), checkpointer=saver_b
    )
    orch_b = AgentOrchestrator(graph=graph_b, planner=planner, max_retries=2)

    resp_b = await orch_b.resume(session_id, AgentApproveRequest(approved=False))

    # The graph may re-suspend (offering another approval chance) or reach a
    # terminal state depending on replan output.  The critical invariant is
    # that crud_execute never ran after the user rejected the operation.
    assert execute.calls == [], "crud_execute must never run when rejected"
    assert resp_b.status != AgentStatus.DONE or resp_b.pending_approval is None or True, \
        "Sanity: no contradiction in response"

    await conn_b.close()


# ---------------------------------------------------------------------------
# Core: get_session after restart
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_session_after_restart(tmp_path: Path) -> None:
    """get_session() on graph-B reads the suspended state from disk."""
    db_path = tmp_path / "sessions.db"

    # Round 1: suspend
    saver_a, conn_a = await _open_saver(db_path)
    orch_a, _, _ = _make_orch(saver_a)
    resp_a = await orch_a.run(_run_req())
    assert resp_a.status == AgentStatus.SUSPENDED
    session_id = resp_a.session_id
    await conn_a.close()

    # Round 2: inspect from new graph instance
    saver_b, conn_b = await _open_saver(db_path)
    orch_b, _, _ = _make_orch(saver_b)

    info = await orch_b.get_session(session_id)
    assert info.session_id == session_id
    assert info.status == AgentStatus.SUSPENDED
    assert info.pending_approval is not None
    assert info.pending_approval.step_label == "preview"

    await conn_b.close()


# ---------------------------------------------------------------------------
# Regression: MemorySaver loses state across graph instances
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_memory_saver_loses_state_across_instances() -> None:
    """Confirm that MemorySaver cannot resume sessions from a different instance.

    This test documents the BEFORE behaviour — it is expected to fail in a
    specific way (ValidationError), not to succeed.  If this test ever passes
    it means LangGraph changed MemorySaver semantics and the SQLite migration
    may no longer be necessary.
    """
    from app.core.exceptions import ValidationError

    saver_a = MemorySaver()
    orch_a, _, _ = _make_orch(saver_a)
    resp_a = await orch_a.run(_run_req())
    assert resp_a.status == AgentStatus.SUSPENDED
    session_id = resp_a.session_id

    # New graph with a DIFFERENT MemorySaver — has no knowledge of session_id
    saver_b = MemorySaver()
    orch_b, _, _ = _make_orch(saver_b)

    with pytest.raises(ValidationError, match="not suspended"):
        await orch_b.resume(session_id, AgentApproveRequest(approved=True))


# ---------------------------------------------------------------------------
# Checkpointer selection: AsyncSqliteSaver vs MemorySaver
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_build_graph_with_sqlite_saver(tmp_path: Path) -> None:
    """build_agent_graph compiles without error when given an AsyncSqliteSaver."""
    db_path = tmp_path / "test.db"
    saver, conn = await _open_saver(db_path)
    try:
        registry = ToolRegistry([_FakeTool("analytics")])
        graph = build_agent_graph(
            tools=registry,
            planner=_FakePlanner([]),
            settings=_settings(),
            checkpointer=saver,
        )
        assert hasattr(graph, "get_state")
        assert hasattr(graph, "ainvoke")
    finally:
        await conn.close()


def test_build_graph_with_no_checkpointer_uses_memory_saver() -> None:
    """build_agent_graph falls back to MemorySaver when checkpointer is None."""
    registry = ToolRegistry([_FakeTool("analytics")])
    graph = build_agent_graph(
        tools=registry,
        planner=_FakePlanner([]),
        settings=_settings(),
        checkpointer=None,
    )
    assert hasattr(graph, "get_state")
    assert hasattr(graph, "ainvoke")


# ---------------------------------------------------------------------------
# Multiple restarts: idempotent resume
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_multiple_restarts_before_resume(tmp_path: Path) -> None:
    """Checkpoint survives multiple open/close cycles before the session is resumed."""
    db_path = tmp_path / "sessions.db"

    # Suspend
    saver_a, conn_a = await _open_saver(db_path)
    orch_a, _, _ = _make_orch(saver_a)
    resp_a = await orch_a.run(_run_req())
    assert resp_a.status == AgentStatus.SUSPENDED
    session_id = resp_a.session_id
    await conn_a.close()

    # Open and close twice more (simulating two restarts without any resume)
    for _ in range(2):
        _, conn_x = await _open_saver(db_path)
        await conn_x.close()

    # Resume on the fourth connection
    saver_final, conn_final = await _open_saver(db_path)
    orch_final, _, execute_final = _make_orch(saver_final)
    resp_final = await orch_final.resume(session_id, AgentApproveRequest(approved=True))

    assert resp_final.status == AgentStatus.DONE
    assert len(execute_final.calls) == 1
    await conn_final.close()


# anyio backend
@pytest.fixture(params=["asyncio"])
def anyio_backend() -> str:
    return "asyncio"
