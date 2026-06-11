"""Tests for LLM provider selection and fallback behaviour."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.core.exceptions import LLMError
from app.api.dependencies import _make_query_planner, _make_forecast_planner
from app.services.groq_provider import (
    FallbackForecastPlanner,
    FallbackQueryPlanner,
    GroqForecastPlanner,
    GroqQueryPlanner,
)
from app.services.llm_provider import OllamaQueryPlanner
from app.services.forecast_planner import OllamaForecastPlanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(**overrides) -> Settings:
    """Build a Settings object with test-safe defaults."""
    base = dict(
        llm_provider="ollama",
        groq_api_key=None,
        groq_model="llama3-8b-8192",
        groq_base_url="https://api.groq.com/openai/v1",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3",
        ollama_timeout_seconds=60.0,
    )
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# Provider selection — query planner
# ---------------------------------------------------------------------------

def test_ollama_provider_returns_ollama_query_planner():
    planner = _make_query_planner(_settings(llm_provider="ollama"))
    assert isinstance(planner, OllamaQueryPlanner)


def test_groq_provider_returns_fallback_query_planner():
    planner = _make_query_planner(_settings(llm_provider="groq", groq_api_key="sk-test"))
    assert isinstance(planner, FallbackQueryPlanner)


def test_groq_fallback_query_planner_wraps_groq_primary():
    planner = _make_query_planner(_settings(llm_provider="groq", groq_api_key="sk-test"))
    assert isinstance(planner._primary, GroqQueryPlanner)


def test_groq_fallback_query_planner_wraps_ollama_secondary():
    planner = _make_query_planner(_settings(llm_provider="groq", groq_api_key="sk-test"))
    assert isinstance(planner._secondary, OllamaQueryPlanner)


# ---------------------------------------------------------------------------
# Provider selection — forecast planner
# ---------------------------------------------------------------------------

def test_ollama_provider_returns_ollama_forecast_planner():
    planner = _make_forecast_planner(_settings(llm_provider="ollama"))
    assert isinstance(planner, OllamaForecastPlanner)


def test_groq_provider_returns_fallback_forecast_planner():
    planner = _make_forecast_planner(_settings(llm_provider="groq", groq_api_key="sk-test"))
    assert isinstance(planner, FallbackForecastPlanner)


def test_groq_fallback_forecast_planner_wraps_groq_primary():
    planner = _make_forecast_planner(_settings(llm_provider="groq", groq_api_key="sk-test"))
    assert isinstance(planner._primary, GroqForecastPlanner)


def test_groq_fallback_forecast_planner_wraps_ollama_secondary():
    planner = _make_forecast_planner(_settings(llm_provider="groq", groq_api_key="sk-test"))
    assert isinstance(planner._secondary, OllamaForecastPlanner)


# ---------------------------------------------------------------------------
# FallbackQueryPlanner — fallback behaviour
# ---------------------------------------------------------------------------

def test_fallback_query_planner_uses_primary_when_it_succeeds():
    expected = {"operation": "row_count", "column": None}
    primary = MagicMock()
    primary.generate_plan = AsyncMock(return_value=expected)
    secondary = MagicMock()
    secondary.generate_plan = AsyncMock(return_value={"operation": "column_count"})

    planner = FallbackQueryPlanner(primary, secondary)
    result = asyncio.run(planner.generate_plan("How many rows?", {}))

    assert result == expected
    primary.generate_plan.assert_awaited_once()
    secondary.generate_plan.assert_not_awaited()


def test_fallback_query_planner_falls_back_on_llm_error():
    fallback_plan = {"operation": "row_count", "column": None}
    primary = MagicMock()
    primary.generate_plan = AsyncMock(side_effect=LLMError("Groq unavailable"))
    secondary = MagicMock()
    secondary.generate_plan = AsyncMock(return_value=fallback_plan)

    planner = FallbackQueryPlanner(primary, secondary)
    result = asyncio.run(planner.generate_plan("How many rows?", {}))

    assert result == fallback_plan
    primary.generate_plan.assert_awaited_once()
    secondary.generate_plan.assert_awaited_once()


def test_fallback_query_planner_propagates_secondary_error():
    primary = MagicMock()
    primary.generate_plan = AsyncMock(side_effect=LLMError("Groq down"))
    secondary = MagicMock()
    secondary.generate_plan = AsyncMock(side_effect=LLMError("Ollama also down"))

    planner = FallbackQueryPlanner(primary, secondary)
    with pytest.raises(LLMError, match="Ollama also down"):
        asyncio.run(planner.generate_plan("How many rows?", {}))


# ---------------------------------------------------------------------------
# FallbackForecastPlanner — fallback behaviour
# ---------------------------------------------------------------------------

def test_fallback_forecast_planner_uses_primary_when_it_succeeds():
    expected = {"operation": "forecast", "date_column": "date", "value_column": "sales",
                "frequency": "M", "aggregation": "sum", "horizon": 6}
    primary = MagicMock()
    primary.generate_forecast_plan = AsyncMock(return_value=expected)
    secondary = MagicMock()
    secondary.generate_forecast_plan = AsyncMock(return_value={})

    planner = FallbackForecastPlanner(primary, secondary)
    result = asyncio.run(planner.generate_forecast_plan("Forecast sales", {}))

    assert result == expected
    secondary.generate_forecast_plan.assert_not_awaited()


def test_fallback_forecast_planner_falls_back_on_llm_error():
    fallback_plan = {"operation": "forecast", "date_column": "date",
                     "value_column": "sales", "frequency": "M",
                     "aggregation": "sum", "horizon": 6}
    primary = MagicMock()
    primary.generate_forecast_plan = AsyncMock(side_effect=LLMError("Groq rate limit"))
    secondary = MagicMock()
    secondary.generate_forecast_plan = AsyncMock(return_value=fallback_plan)

    planner = FallbackForecastPlanner(primary, secondary)
    result = asyncio.run(planner.generate_forecast_plan("Forecast sales", {}))

    assert result == fallback_plan
    secondary.generate_forecast_plan.assert_awaited_once()


# ---------------------------------------------------------------------------
# set_client delegation
# ---------------------------------------------------------------------------

def test_fallback_query_planner_delegates_set_client_to_both():
    import httpx
    client = MagicMock(spec=httpx.AsyncClient)
    primary = MagicMock(spec=["set_client", "generate_plan"])
    secondary = MagicMock(spec=["set_client", "generate_plan"])

    FallbackQueryPlanner(primary, secondary).set_client(client)

    primary.set_client.assert_called_once_with(client)
    secondary.set_client.assert_called_once_with(client)


def test_fallback_forecast_planner_delegates_set_client_to_both():
    import httpx
    client = MagicMock(spec=httpx.AsyncClient)
    primary = MagicMock(spec=["set_client", "generate_forecast_plan"])
    secondary = MagicMock(spec=["set_client", "generate_forecast_plan"])

    FallbackForecastPlanner(primary, secondary).set_client(client)

    primary.set_client.assert_called_once_with(client)
    secondary.set_client.assert_called_once_with(client)


def test_fallback_set_client_skips_planners_without_set_client():
    """Planners that have no set_client attribute must not raise."""
    import httpx
    client = MagicMock(spec=httpx.AsyncClient)
    primary = MagicMock(spec=["generate_plan"])   # no set_client
    secondary = MagicMock(spec=["set_client", "generate_plan"])

    FallbackQueryPlanner(primary, secondary).set_client(client)  # must not raise
    secondary.set_client.assert_called_once_with(client)
