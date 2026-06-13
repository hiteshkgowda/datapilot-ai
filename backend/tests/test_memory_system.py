"""Tests for the conversational memory system.

Coverage:
  - SessionMemory (L1 in-process cache)
  - ConversationStore (SQLite persistence)
  - ContextBuilder (turn → prompt formatting)
  - MemoryService (facade integration)
  - Memory API routes (GET /memory/context, DELETE /memory/clear)
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from memory.session_memory import SessionMemory
from memory.conversation_store import ConversationStore
from memory.context_builder import ContextBuilder
from app.schemas.memory import TurnType, ConversationTurn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turn(
    session_id: str = "sess1",
    user_sub: str = "user1",
    turn_type: str = "query",
    question: str = "show top customers",
    answer: str = "Here are the top 5 customers.",
    dataset_id: str = "ds1",
) -> dict:
    return {
        "turn_id": uuid.uuid4().hex,
        "session_id": session_id,
        "user_sub": user_sub,
        "created_at": "2024-01-01T00:00:00+00:00",
        "turn_type": turn_type,
        "dataset_id": dataset_id,
        "question": question,
        "answer": answer,
        "table_data": [{"name": "Alice", "revenue": 5000}],
        "chart_spec": None,
        "insights": None,
        "anomalies": None,
        "forecast": None,
        "recommendations": None,
        "metadata": None,
    }


# ---------------------------------------------------------------------------
# SessionMemory tests
# ---------------------------------------------------------------------------

class TestSessionMemory:
    def test_get_returns_empty_for_unknown_session(self):
        mem = SessionMemory(ttl_seconds=60, max_sessions=10)
        assert mem.get("nosess", "nouser") == []

    def test_put_and_get(self):
        mem = SessionMemory(ttl_seconds=60, max_sessions=10)
        turns = [_turn()]
        mem.put("s1", "u1", turns)
        result = mem.get("s1", "u1")
        assert len(result) == 1
        assert result[0]["question"] == "show top customers"

    def test_different_users_isolated(self):
        mem = SessionMemory(ttl_seconds=60, max_sessions=10)
        mem.put("same_session", "user_a", [_turn(user_sub="user_a")])
        mem.put("same_session", "user_b", [_turn(user_sub="user_b", question="other")])
        assert mem.get("same_session", "user_a")[0]["question"] == "show top customers"
        assert mem.get("same_session", "user_b")[0]["question"] == "other"

    def test_delete_clears_turns(self):
        mem = SessionMemory(ttl_seconds=60, max_sessions=10)
        mem.put("s1", "u1", [_turn()])
        count = mem.delete("s1", "u1")
        assert count == 1
        assert mem.get("s1", "u1") == []

    def test_delete_nonexistent_returns_zero(self):
        mem = SessionMemory(ttl_seconds=60, max_sessions=10)
        count = mem.delete("nosess", "nouser")
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_async_returns_empty_for_unknown(self):
        mem = SessionMemory(ttl_seconds=60, max_sessions=10)
        result = await mem.get_async("nosess", "nouser")
        assert result == []

    @pytest.mark.asyncio
    async def test_put_async_then_get_async(self):
        mem = SessionMemory(ttl_seconds=60, max_sessions=10)
        turns = [_turn()]
        await mem.put_async("s1", "u1", turns)
        result = await mem.get_async("s1", "u1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_delete_async_clears(self):
        mem = SessionMemory(ttl_seconds=60, max_sessions=10)
        await mem.put_async("s1", "u1", [_turn()])
        await mem.delete_async("s1", "u1")
        result = await mem.get_async("s1", "u1")
        assert result == []

    def test_no_redis_when_package_missing(self):
        with patch.dict("sys.modules", {"redis": None, "redis.asyncio": None}):
            mem = SessionMemory(redis_url="redis://localhost:6379")
        assert mem._redis is None


# ---------------------------------------------------------------------------
# ConversationStore tests
# ---------------------------------------------------------------------------

class TestConversationStore:
    @pytest.fixture
    def db_path(self, tmp_path: Path) -> Path:
        return tmp_path / "test_conversations.db"

    @pytest.mark.asyncio
    async def test_initialize_creates_table(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        assert db_path.exists()

    @pytest.mark.asyncio
    async def test_save_and_load_turn(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        t = _turn()
        await store.save_turn(t)
        turns = await store.load_turns("sess1", "user1")
        assert len(turns) == 1
        assert turns[0]["question"] == "show top customers"
        assert turns[0]["turn_type"] == "query"

    @pytest.mark.asyncio
    async def test_load_respects_limit(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        for i in range(5):
            t = _turn(question=f"question {i}")
            t["created_at"] = f"2024-01-0{i+1}T00:00:00+00:00"
            await store.save_turn(t)
        turns = await store.load_turns("sess1", "user1", limit=3)
        assert len(turns) == 3

    @pytest.mark.asyncio
    async def test_load_ordered_ascending(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        for i in range(3):
            t = _turn(question=f"q{i}")
            t["turn_id"] = uuid.uuid4().hex
            t["created_at"] = f"2024-01-0{i+1}T00:00:00+00:00"
            await store.save_turn(t)
        turns = await store.load_turns("sess1", "user1")
        questions = [t["question"] for t in turns]
        assert questions == ["q0", "q1", "q2"]

    @pytest.mark.asyncio
    async def test_user_isolation(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        t1 = _turn(user_sub="alice")
        t2 = _turn(user_sub="bob", question="bob question")
        t2["turn_id"] = uuid.uuid4().hex
        await store.save_turn(t1)
        await store.save_turn(t2)
        alice_turns = await store.load_turns("sess1", "alice")
        bob_turns = await store.load_turns("sess1", "bob")
        assert len(alice_turns) == 1
        assert len(bob_turns) == 1
        assert bob_turns[0]["question"] == "bob question"

    @pytest.mark.asyncio
    async def test_clear_session(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        await store.save_turn(_turn())
        await store.save_turn({**_turn(), "turn_id": uuid.uuid4().hex})
        count = await store.clear_session("sess1", "user1")
        assert count == 2
        remaining = await store.load_turns("sess1", "user1")
        assert remaining == []

    @pytest.mark.asyncio
    async def test_clear_only_targets_user(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        t_alice = _turn(user_sub="alice")
        t_bob = {**_turn(user_sub="bob"), "turn_id": uuid.uuid4().hex}
        await store.save_turn(t_alice)
        await store.save_turn(t_bob)
        await store.clear_session("sess1", "alice")
        bob_turns = await store.load_turns("sess1", "bob")
        assert len(bob_turns) == 1

    @pytest.mark.asyncio
    async def test_count_turns(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        for _ in range(3):
            await store.save_turn({**_turn(), "turn_id": uuid.uuid4().hex})
        count = await store.count_turns("sess1", "user1")
        assert count == 3

    @pytest.mark.asyncio
    async def test_expire_removes_old_turns(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        old = {**_turn(), "created_at": "2020-01-01T00:00:00+00:00"}
        new = {**_turn(), "turn_id": uuid.uuid4().hex, "created_at": "2099-01-01T00:00:00+00:00"}
        await store.save_turn(old)
        await store.save_turn(new)
        expired = await store.expire_old_turns("2024-01-01T00:00:00+00:00")
        assert expired == 1
        remaining = await store.load_turns("sess1", "user1")
        assert len(remaining) == 1
        assert remaining[0]["created_at"] == "2099-01-01T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_json_fields_round_trip(self, db_path: Path):
        store = ConversationStore(db_path)
        await store.initialize()
        t = _turn()
        t["chart_spec"] = {"type": "bar", "data": [1, 2, 3]}
        t["insights"] = {"key": "value", "count": 5}
        await store.save_turn(t)
        turns = await store.load_turns("sess1", "user1")
        assert turns[0]["chart_spec"] == {"type": "bar", "data": [1, 2, 3]}
        assert turns[0]["insights"] == {"key": "value", "count": 5}


# ---------------------------------------------------------------------------
# ContextBuilder tests
# ---------------------------------------------------------------------------

class TestContextBuilder:
    def test_build_agent_context_empty(self):
        items = ContextBuilder.build_agent_context([])
        assert items == []

    def test_build_agent_context_uses_question_as_goal(self):
        t = _turn(question="what is the top revenue?", answer="Customer A: $5k")
        items = ContextBuilder.build_agent_context([t])
        assert len(items) == 1
        assert items[0]["goal"] == "what is the top revenue?"
        assert "5 row" in items[0]["summary"] or "Customer A" in items[0]["summary"]

    def test_build_agent_context_fallback_goal_when_no_question(self):
        t = _turn(question=None)
        items = ContextBuilder.build_agent_context([t])
        assert "dataset" in items[0]["goal"] or "action" in items[0]["goal"]

    def test_build_summary_empty(self):
        summary = ContextBuilder.build_summary([])
        assert "No prior" in summary

    def test_build_summary_includes_question(self):
        t = _turn(question="show revenue by region")
        summary = ContextBuilder.build_summary([t])
        assert "show revenue by region" in summary

    def test_build_summary_capped_at_max_chars(self):
        turns = [_turn(answer="x" * 500) for _ in range(20)]
        summary = ContextBuilder.build_summary(turns, max_chars=200)
        assert len(summary) <= 200

    def test_extract_dataset_ids_returns_most_recent_first(self):
        t1 = _turn(dataset_id="ds_old")
        t1["created_at"] = "2024-01-01T00:00:00"
        t2 = {**_turn(), "dataset_id": "ds_new", "turn_id": uuid.uuid4().hex}
        t2["created_at"] = "2024-01-02T00:00:00"
        ids = ContextBuilder.extract_dataset_ids([t1, t2])
        assert ids[0] == "ds_new"
        assert ids[1] == "ds_old"

    def test_extract_dataset_ids_deduplicates(self):
        turns = [_turn(dataset_id="ds1"), {**_turn(), "turn_id": uuid.uuid4().hex}]
        ids = ContextBuilder.extract_dataset_ids(turns)
        assert ids.count("ds1") == 1

    def test_summarize_forecast_turn(self):
        t = _turn(turn_type="forecast")
        t["forecast"] = {"horizon": 12, "frequency": "M"}
        items = ContextBuilder.build_agent_context([t])
        assert "12" in items[0]["summary"]

    def test_summarize_anomaly_turn(self):
        t = _turn(turn_type="anomaly")
        t["anomalies"] = {"total_anomaly_count": 7, "severity": "high"}
        items = ContextBuilder.build_agent_context([t])
        assert "7" in items[0]["summary"]

    def test_summarize_insight_turn(self):
        t = _turn(turn_type="insight")
        t["insights"] = {"insights": ["a", "b", "c"]}
        items = ContextBuilder.build_agent_context([t])
        assert "3" in items[0]["summary"]

    def test_summarize_recommendation_turn(self):
        t = _turn(turn_type="recommendation")
        t["recommendations"] = {"total_count": 5}
        items = ContextBuilder.build_agent_context([t])
        assert "5" in items[0]["summary"]


# ---------------------------------------------------------------------------
# MemoryService integration tests
# ---------------------------------------------------------------------------

class TestMemoryService:
    @pytest.fixture
    def db_path(self, tmp_path: Path) -> Path:
        return tmp_path / "mem_svc.db"

    @pytest_asyncio.fixture
    async def memory_service(self, db_path: Path):
        from app.services.memory_service import MemoryService

        store = ConversationStore(db_path)
        await store.initialize()
        session_mem = SessionMemory(ttl_seconds=60, max_sessions=10)
        builder = ContextBuilder()
        return MemoryService(
            store=store,
            session_memory=session_mem,
            context_builder=builder,
            max_turns_per_session=10,
            max_table_rows=5,
            session_ttl_seconds=3600,
        )

    @pytest.mark.asyncio
    async def test_record_turn_returns_conversation_turn(self, memory_service):
        turn = await memory_service.record_turn(
            session_id="sess1",
            user_sub="user1",
            turn_type=TurnType.QUERY,
            question="show top customers",
            answer="Here are the top 5.",
            dataset_id="ds1",
        )
        assert isinstance(turn, ConversationTurn)
        assert turn.question == "show top customers"
        assert turn.turn_type == TurnType.QUERY

    @pytest.mark.asyncio
    async def test_get_context_after_recording(self, memory_service):
        await memory_service.record_turn(
            "sess1", "u1", TurnType.QUERY, question="Q1", answer="A1", dataset_id="ds1"
        )
        ctx = await memory_service.get_context("sess1", "u1")
        assert ctx.session_id == "sess1"
        assert ctx.turn_count == 1
        assert ctx.turns[0].question == "Q1"
        assert "ds1" in ctx.datasets_referenced
        assert ctx.last_dataset_id == "ds1"

    @pytest.mark.asyncio
    async def test_table_data_capped(self, memory_service):
        big_table = [{"row": i} for i in range(100)]
        await memory_service.record_turn(
            "sess1", "u1", TurnType.QUERY, table_data=big_table
        )
        ctx = await memory_service.get_context("sess1", "u1")
        assert len(ctx.turns[0].table_data) == 5  # max_table_rows=5

    @pytest.mark.asyncio
    async def test_clear_session(self, memory_service):
        await memory_service.record_turn("sess1", "u1", TurnType.QUERY, question="Q1")
        # Allow fire-and-forget SQLite write to complete
        await asyncio.sleep(0.05)
        resp = await memory_service.clear_session("sess1", "u1")
        assert resp.turns_cleared >= 1
        ctx = await memory_service.get_context("sess1", "u1")
        assert ctx.turn_count == 0

    @pytest.mark.asyncio
    async def test_build_agent_context(self, memory_service):
        await memory_service.record_turn(
            "sess1", "u1", TurnType.QUERY, question="show revenue", answer="$1M"
        )
        history = await memory_service.build_agent_context("sess1", "u1")
        assert len(history) == 1
        assert history[0]["goal"] == "show revenue"

    @pytest.mark.asyncio
    async def test_max_turns_per_session_enforced(self, memory_service):
        for i in range(15):  # max is 10
            await memory_service.record_turn("s1", "u1", TurnType.QUERY, question=f"q{i}")
        ctx = await memory_service.get_context("s1", "u1")
        assert ctx.turn_count <= 10

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self, memory_service):
        await memory_service.record_turn("s1", "u1", TurnType.QUERY, question="show top customers", answer="Alice, Bob, Carol")
        await memory_service.record_turn("s1", "u1", TurnType.FORECAST, question="forecast them", answer="Growth expected")
        await memory_service.record_turn("s1", "u1", TurnType.REPORT, question="generate report", answer="report.pdf")

        history = await memory_service.build_agent_context("s1", "u1")
        assert len(history) == 3
        assert history[0]["goal"] == "show top customers"
        assert history[1]["goal"] == "forecast them"
        assert history[2]["goal"] == "generate report"


# ---------------------------------------------------------------------------
# Memory API route tests
# ---------------------------------------------------------------------------

class TestMemoryRoutes:
    @pytest.fixture
    def mock_memory_service(self):
        from app.schemas.memory import ConversationContext, MemoryClearResponse
        svc = AsyncMock()
        svc.get_context.return_value = ConversationContext(
            session_id="sess1",
            turn_count=2,
            turns=[],
            summary="Two prior turns.",
            datasets_referenced=["ds1"],
            last_dataset_id="ds1",
        )
        svc.clear_session.return_value = MemoryClearResponse(
            session_id="sess1",
            turns_cleared=2,
            message="Cleared 2 turn(s) from session.",
        )
        return svc

    def _make_client(self, mock_svc):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from app.api.routes.memory import router
        from app.api.dependencies import get_memory_service
        from app.core.auth import get_current_user
        from app.schemas.auth import CurrentUser

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_memory_service] = lambda: mock_svc
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            sub="user1", email="test@test.com", name="Test"
        )
        return TestClient(app)

    def test_get_context_returns_200(self, mock_memory_service):
        client = self._make_client(mock_memory_service)
        resp = client.get("/api/v1/memory/context?session_id=sess1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "sess1"
        assert data["turn_count"] == 2
        assert data["last_dataset_id"] == "ds1"

    def test_get_context_requires_session_id(self, mock_memory_service):
        client = self._make_client(mock_memory_service)
        resp = client.get("/api/v1/memory/context")
        assert resp.status_code == 422

    def test_clear_returns_200(self, mock_memory_service):
        client = self._make_client(mock_memory_service)
        resp = client.delete("/api/v1/memory/clear?session_id=sess1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["turns_cleared"] == 2

    def test_clear_calls_with_user_sub(self, mock_memory_service):
        client = self._make_client(mock_memory_service)
        client.delete("/api/v1/memory/clear?session_id=sess1")
        mock_memory_service.clear_session.assert_called_once_with(
            session_id="sess1", user_sub="user1"
        )

    def test_get_context_calls_with_user_sub(self, mock_memory_service):
        client = self._make_client(mock_memory_service)
        client.get("/api/v1/memory/context?session_id=sess1")
        mock_memory_service.get_context.assert_called_once_with(
            session_id="sess1", user_sub="user1"
        )
