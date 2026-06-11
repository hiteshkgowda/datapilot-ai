"""LLM provider for CRUD operation planning (Phase 7).

The LLM receives a natural-language mutation request and the target table's
column schema.  It emits a strict JSON CrudPlan — never SQL, never code.

Exports:
    CrudPlanner           — Protocol
    OllamaCrudPlanner     — backed by local Ollama
    GroqCrudPlanner       — backed by Groq cloud API
    FallbackCrudPlanner   — tries primary, falls back to secondary on LLMError
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

import httpx

from app.core.config import Settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a database mutation planning assistant. Convert a \
natural-language instruction into a STRICT JSON CrudPlan object.

Do NOT write SQL, code, or prose. Output ONLY a single JSON object.

Supported operations:
- "create"      requires: row_data
- "update"      requires: filters, set_values
- "delete"      requires: filters
- "bulk_update" requires: filters, set_values
- "soft_delete" requires: filters, soft_delete_column

CrudPlan JSON shape:
{
  "operation": "<operation>",
  "schema_name": "<schema or null>",
  "table_name": "<table — required>",
  "row_data":            { "<col>": <value> } or null,
  "filters":             [ { "column": "<col>", "operator": "<op>", "value": <v> } ] or null,
  "set_values":          { "<col>": <value> } or null,
  "soft_delete_column":  "<col>" or null,
  "soft_delete_value":   <value> or null
}

Filter operators:
  eq, neq, gt, gte, lt, lte      scalar comparisons
  in_                             value must be a JSON array
  is_null, is_not_null            value must be null

Rules (violations cause rejection):
1. Use ONLY column names from the provided schema, spelled exactly as shown.
2. delete / update / bulk_update / soft_delete MUST include at least one filter.
3. soft_delete requires soft_delete_column.
4. in_ value must be a non-empty JSON array.
5. is_null / is_not_null must have value: null.
6. row_data is only used for create.
7. set_values is only used for update / bulk_update.
8. Do not include primary-key columns in set_values.
9. Set all unused fields to null.

Return ONLY the JSON object — no markdown, no commentary."""


def _user_prompt(question: str, schema: dict[str, str], table_name: str) -> str:
    cols = "\n".join(f"  {c}: {t}" for c, t in schema.items())
    return f"Table: {table_name}\nColumns:\n{cols}\n\nInstruction: {question}\nJSON CrudPlan:"


@runtime_checkable
class CrudPlanner(Protocol):
    async def generate_crud_plan(
        self, question: str, schema: dict[str, str], table_name: str
    ) -> dict[str, Any]: ...


class OllamaCrudPlanner:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._client: httpx.AsyncClient | None = None

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def generate_crud_plan(
        self, question: str, schema: dict[str, str], table_name: str
    ) -> dict[str, Any]:
        if self._client is None:
            raise LLMError("LLM HTTP client not initialised.")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(question, schema, table_name)},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        try:
            resp = await self._client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama '{self._model}' unreachable: {exc}") from exc
        content = resp.json().get("message", {}).get("content", "")
        return _parse_json(content, "Ollama")


class GroqCrudPlanner:
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.groq_api_key
        self._model = settings.groq_model
        self._base_url = settings.groq_base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def generate_crud_plan(
        self, question: str, schema: dict[str, str], table_name: str
    ) -> dict[str, Any]:
        if not self._api_key:
            raise LLMError("GROQ_API_KEY is not set.")
        if self._client is None:
            raise LLMError("LLM HTTP client not initialised.")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(question, schema, table_name)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Groq '{self._model}' unreachable: {exc}") from exc
        content = (
            resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        return _parse_json(content, "Groq")


class FallbackCrudPlanner:
    """Tries the primary planner; on LLMError falls back to secondary."""

    def __init__(self, primary: Any, secondary: Any) -> None:
        self._primary = primary
        self._secondary = secondary

    def set_client(self, client: httpx.AsyncClient) -> None:
        for p in (self._primary, self._secondary):
            if hasattr(p, "set_client"):
                p.set_client(client)

    async def generate_crud_plan(
        self, question: str, schema: dict[str, str], table_name: str
    ) -> dict[str, Any]:
        try:
            return await self._primary.generate_crud_plan(question, schema, table_name)
        except LLMError as exc:
            logger.warning("Primary CRUD planner failed (%s); trying secondary.", exc)
            return await self._secondary.generate_crud_plan(question, schema, table_name)


# ------------------------------------------------------------------ #
# Shared helper
# ------------------------------------------------------------------ #

def _parse_json(content: str, source: str) -> dict[str, Any]:
    try:
        result = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMError(f"{source} returned invalid JSON: {content!r}") from exc
    if not isinstance(result, dict):
        raise LLMError(f"{source} returned a non-object plan: {result!r}")
    return result
