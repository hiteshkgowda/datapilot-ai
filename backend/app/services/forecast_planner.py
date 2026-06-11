"""LLM provider that turns questions into structured forecast plans.

Mirrors the analytics planner: the model emits only a JSON ForecastPlan; it
never produces code. Uses the shared, lifespan-managed HTTP client.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import Settings
from app.core.exceptions import LLMError

SYSTEM_PROMPT = """You are a forecasting-plan assistant for a tabular data \
system. Convert the user's question into a STRICT JSON forecast plan.

You MUST NOT write code. Output ONLY a single JSON object, with no prose.

Fields:
- "operation": one of ["forecast", "anomaly_detection", "timeseries_aggregate"]
- "date_column": (string) a column containing dates/timestamps
- "value_column": (string) the numeric column to analyze
- "frequency": one of ["D", "W", "M", "Q", "Y"] (day/week/month/quarter/year) — NEVER null
- "aggregation": one of ["sum", "mean"] — ALWAYS required, NEVER null or omitted
- "horizon": (integer or null) number of future periods to forecast

Rules:
- Use only column names from the provided schema, spelled exactly as given.
- "forecast" projects future values; set a reasonable "horizon".
- "anomaly_detection" flags unusual points; "horizon" may be null.
- "timeseries_aggregate" just resamples the series; "horizon" may be null.
- "aggregation" must always be "sum" or "mean" regardless of the operation.
- "frequency" must always be one of ["D", "W", "M", "Q", "Y"], never null.
Return ONLY the JSON object."""


@runtime_checkable
class ForecastPlanner(Protocol):
    async def generate_forecast_plan(
        self, question: str, schema: dict[str, str]
    ) -> dict[str, Any]:
        ...


class OllamaForecastPlanner:
    """Forecast planner backed by an Ollama-served model (e.g. Llama 3)."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._client: httpx.AsyncClient | None = None

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def generate_forecast_plan(
        self, question: str, schema: dict[str, str]
    ) -> dict[str, Any]:
        if self._client is None:
            raise LLMError("The LLM HTTP client has not been initialized.")

        schema_lines = "\n".join(f"- {n}: {t}" for n, t in schema.items())
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Dataset columns (name: type):\n{schema_lines}\n\n"
                        f"Question: {question}\nJSON plan:"
                    ),
                },
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/api/chat", json=payload
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Could not reach the Ollama model '{self._model}' at "
                f"{self._base_url}: {exc}"
            ) from exc

        content = response.json().get("message", {}).get("content", "")
        try:
            plan = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMError(f"The model returned invalid JSON: {content!r}") from exc
        if not isinstance(plan, dict):
            raise LLMError(f"The model returned a non-object plan: {plan!r}")
        return plan
