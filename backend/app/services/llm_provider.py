"""LLM provider that turns questions into structured query plans.

The provider is the ONLY component that talks to the language model. It returns
a raw plan dictionary; it never executes code and never trusts the model beyond
producing JSON. All validation and execution happen downstream.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import Settings
from app.core.exceptions import LLMError

SYSTEM_PROMPT = """You are a query-planning assistant for a tabular data \
analytics system. Convert the user's question into a STRICT JSON query plan.

You MUST NOT write code. Output ONLY a single JSON object, with no prose.

The JSON object has these fields:
- "operation": one of ["row_count", "column_count", "sum", "average", "max", \
"min", "groupby_sum", "groupby_count", "top_n", "xy_select"]
- "column": (string or null) the target numeric column for sum/average/max/min/\
groupby_sum/top_n
- "group_by": (string or null) the column to group by for groupby_sum/\
groupby_count/top_n
- "n": (integer or null) the number of groups for top_n
- "x_column": (string or null) numeric x-axis column for xy_select
- "y_column": (string or null) numeric y-axis column for xy_select
- "chart_type": (string or null) a chart recommendation, one of ["bar", \
"line", "pie", "scatter"]

Rules:
- Use only column names from the provided schema, spelled exactly as given.
- "row_count" and "column_count" require no column.
- "sum", "average", "max", "min" require "column".
- "groupby_sum" and "top_n" require both "group_by" and "column".
- "groupby_count" requires "group_by" (it counts rows per group).
- "top_n" also requires "n".
- "xy_select" requires numeric "x_column" and "y_column".
- Set unused fields to null.

Chart guidance for "chart_type":
- trends or values over time -> "line"
- shares, proportions or distributions -> "pie"
- comparisons across categories, "by X", or "top N" -> "bar"
- the relationship between two numeric columns -> "scatter" (use xy_select)
- if no chart makes sense (single-number answers), set "chart_type" to null.
Return ONLY the JSON object."""


@runtime_checkable
class QueryPlanner(Protocol):
    """Abstraction over any component that can produce a query plan."""

    async def generate_plan(
        self, question: str, schema: dict[str, str]
    ) -> dict[str, Any]:
        """Return a raw query-plan dict for ``question`` given a column schema."""
        ...


class OllamaQueryPlanner:
    """Query planner backed by an Ollama-served model (e.g. Llama 3)."""

    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._client: httpx.AsyncClient | None = None

    def set_client(self, client: httpx.AsyncClient) -> None:
        """Attach the shared, lifespan-managed HTTP client."""
        self._client = client

    async def generate_plan(
        self, question: str, schema: dict[str, str]
    ) -> dict[str, Any]:
        """Ask the model for a JSON plan and parse it.

        Raises:
            LLMError: if Ollama is unreachable or returns non-JSON content.
        """
        if self._client is None:
            raise LLMError("The LLM HTTP client has not been initialized.")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": self._build_user_prompt(question, schema)},
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
            raise LLMError(
                f"The model returned invalid JSON: {content!r}"
            ) from exc

        if not isinstance(plan, dict):
            raise LLMError(f"The model returned a non-object plan: {plan!r}")
        return plan

    @staticmethod
    def _build_user_prompt(question: str, schema: dict[str, str]) -> str:
        """Render the dataset schema and question into a prompt."""
        schema_lines = "\n".join(
            f"- {name}: {dtype}" for name, dtype in schema.items()
        )
        return (
            "Dataset columns (name: type):\n"
            f"{schema_lines}\n\n"
            f"Question: {question}\n"
            "JSON plan:"
        )
