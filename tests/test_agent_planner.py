"""Unit tests for agent_planner: JSON parsing, validation, fallback logic."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import LLMError
from app.services.agent_planner import (
    FallbackAgentPlanner,
    OllamaAgentPlanner,
    _parse_plan_json,
)


# ------------------------------------------------------------------ #
# _parse_plan_json
# ------------------------------------------------------------------ #

def test_parse_valid_plan():
    raw = json.dumps([
        {"tool_name": "analytics", "arguments": {"dataset_id": "d1", "question": "sum?"}, "step_label": "sum"},
        {"tool_name": "report",    "arguments": {"dataset_id": "d1"}, "step_label": "report"},
    ])
    plan = _parse_plan_json(raw, "test")
    assert len(plan) == 2
    assert plan[0]["tool_name"] == "analytics"


def test_parse_strips_markdown_fences():
    raw = "```json\n[{\"tool_name\": \"analytics\", \"arguments\": {}, \"step_label\": \"s\"}]\n```"
    plan = _parse_plan_json(raw, "test")
    assert plan[0]["tool_name"] == "analytics"


def test_parse_invalid_json_raises():
    with pytest.raises(LLMError, match="invalid JSON"):
        _parse_plan_json("not json at all", "test")


def test_parse_non_array_raises():
    with pytest.raises(LLMError, match="non-array"):
        _parse_plan_json('{"tool_name": "analytics"}', "test")


def test_parse_step_missing_tool_name_raises():
    with pytest.raises(LLMError, match="missing 'tool_name'"):
        _parse_plan_json('[{"arguments": {}, "step_label": "x"}]', "test")


def test_parse_non_dict_step_raises():
    with pytest.raises(LLMError, match="not an object"):
        _parse_plan_json('["just_a_string"]', "test")


def test_parse_empty_plan_is_valid():
    plan = _parse_plan_json("[]", "test")
    assert plan == []


# ------------------------------------------------------------------ #
# OllamaAgentPlanner — mocked HTTP
# ------------------------------------------------------------------ #

def _make_ollama_planner() -> OllamaAgentPlanner:
    from app.core.config import Settings
    settings = Settings(ollama_model="llama3", ollama_base_url="http://localhost:11434")
    return OllamaAgentPlanner(settings)


@pytest.mark.anyio
async def test_ollama_generate_plan_parses_response():
    planner = _make_ollama_planner()
    plan_json = json.dumps([
        {"tool_name": "dataset_preview", "arguments": {"dataset_id": "d1"}, "step_label": "preview"},
    ])
    # Use MagicMock for the response so that json() is a synchronous call (not a coroutine)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": {"content": plan_json}}
    client = AsyncMock()
    client.post.return_value = mock_response
    planner.set_client(client)

    result = await planner.generate_plan(
        goal="preview my dataset",
        tool_schemas=[],
        dataset_id="d1",
        connection_id=None,
        conversation_history=[],
    )
    assert result[0]["tool_name"] == "dataset_preview"


@pytest.mark.anyio
async def test_ollama_unreachable_raises_llm_error():
    import httpx
    planner = _make_ollama_planner()
    client = AsyncMock()
    client.post.side_effect = httpx.ConnectError("refused")
    planner.set_client(client)

    with pytest.raises(LLMError, match="unreachable"):
        await planner.generate_plan("goal", [], None, None, [])


@pytest.mark.anyio
async def test_ollama_no_client_raises():
    planner = _make_ollama_planner()
    with pytest.raises(LLMError, match="not initialised"):
        await planner.generate_plan("goal", [], None, None, [])


@pytest.mark.anyio
async def test_ollama_replan_calls_replan_prompt():
    planner = _make_ollama_planner()
    plan_json = json.dumps([
        {"tool_name": "analytics", "arguments": {"dataset_id": "d1", "question": "?"}, "step_label": "retry"},
    ])
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": {"content": plan_json}}
    client = AsyncMock()
    client.post.return_value = mock_response
    planner.set_client(client)

    result = await planner.replan(
        goal="do analysis",
        tool_schemas=[],
        completed_results=[{"tool_name": "dataset_preview", "output": {"answer": "100 rows"}, "step_label": "p"}],
        failed_step={"tool_name": "analytics", "step_label": "analysis"},
        error="LLM timeout",
        remaining_steps=[],
    )
    assert result[0]["tool_name"] == "analytics"
    # Verify the re-plan system prompt was used
    call_payload = client.post.call_args[1]["json"]
    assert "re-planner" in call_payload["messages"][0]["content"].lower()


# ------------------------------------------------------------------ #
# FallbackAgentPlanner
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_fallback_uses_primary():
    primary = AsyncMock()
    primary.generate_plan.return_value = [{"tool_name": "analytics", "arguments": {}, "step_label": "a"}]
    secondary = AsyncMock()
    fallback = FallbackAgentPlanner(primary, secondary)

    result = await fallback.generate_plan("goal", [], None, None, [])
    primary.generate_plan.assert_awaited_once()
    secondary.generate_plan.assert_not_called()
    assert result[0]["tool_name"] == "analytics"


@pytest.mark.anyio
async def test_fallback_switches_on_llm_error():
    primary = AsyncMock()
    primary.generate_plan.side_effect = LLMError("primary down")
    secondary = AsyncMock()
    secondary.generate_plan.return_value = [{"tool_name": "forecast", "arguments": {}, "step_label": "f"}]
    fallback = FallbackAgentPlanner(primary, secondary)

    result = await fallback.generate_plan("goal", [], None, None, [])
    secondary.generate_plan.assert_awaited_once()
    assert result[0]["tool_name"] == "forecast"


@pytest.mark.anyio
async def test_fallback_propagates_if_both_fail():
    primary = AsyncMock()
    primary.generate_plan.side_effect = LLMError("primary down")
    secondary = AsyncMock()
    secondary.generate_plan.side_effect = LLMError("secondary down")
    fallback = FallbackAgentPlanner(primary, secondary)

    with pytest.raises(LLMError):
        await fallback.generate_plan("goal", [], None, None, [])


def test_fallback_set_client_wires_both():
    primary = MagicMock()
    secondary = MagicMock()
    fallback = FallbackAgentPlanner(primary, secondary)
    client = MagicMock()
    fallback.set_client(client)
    primary.set_client.assert_called_once_with(client)
    secondary.set_client.assert_called_once_with(client)


# anyio backend fixture
@pytest.fixture(params=["asyncio"])
def anyio_backend():
    return "asyncio"
