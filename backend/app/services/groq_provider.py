"""Groq LLM provider and fallback wrappers.

Groq exposes an OpenAI-compatible chat completions endpoint. The system prompts
are identical to the Ollama implementations — only the HTTP wire format differs
(Bearer auth, ``choices[0].message.content`` response path, and
``response_format`` instead of Ollama's ``format`` field).

Exports:
    GroqQueryPlanner      — implements QueryPlanner protocol
    GroqForecastPlanner   — implements ForecastPlanner protocol
    FallbackQueryPlanner  — QueryPlanner that tries primary, falls back to secondary
    FallbackForecastPlanner — ForecastPlanner with the same fallback pattern
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import LLMError
from app.services.forecast_planner import SYSTEM_PROMPT as _FORECAST_SYSTEM_PROMPT
from app.services.llm_provider import SYSTEM_PROMPT as _QUERY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------

class _GroqChatClient:
    """Low-level caller for Groq's OpenAI-compatible chat completions API."""

    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def chat(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """POST a chat request and return the parsed JSON plan dict."""
        if self._client is None:
            raise LLMError("The LLM HTTP client has not been initialized.")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(
                f"Could not reach Groq model '{self._model}' at "
                f"{self._base_url}: {exc}"
            ) from exc

        content = (
            response.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        try:
            plan = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMError(
                f"Groq returned invalid JSON: {content!r}"
            ) from exc
        if not isinstance(plan, dict):
            raise LLMError(f"Groq returned a non-object plan: {plan!r}")
        return plan


# ---------------------------------------------------------------------------
# Groq query planner  (implements QueryPlanner protocol)
# ---------------------------------------------------------------------------

class GroqQueryPlanner:
    """Query planner backed by Groq's API (llama3-8b-8192 or similar)."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.groq_api_key
        self._groq = _GroqChatClient(
            settings.groq_api_key or "",
            settings.groq_model,
            settings.groq_base_url,
        )

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._groq.set_client(client)

    async def generate_plan(
        self, question: str, schema: dict[str, str]
    ) -> dict[str, Any]:
        if not self._api_key:
            raise LLMError(
                "GROQ_API_KEY is not configured. "
                "Set the GROQ_API_KEY environment variable."
            )
        schema_lines = "\n".join(f"- {n}: {t}" for n, t in schema.items())
        user_prompt = (
            "Dataset columns (name: type):\n"
            f"{schema_lines}\n\n"
            f"Question: {question}\n"
            "JSON plan:"
        )
        return await self._groq.chat(_QUERY_SYSTEM_PROMPT, user_prompt)


# ---------------------------------------------------------------------------
# Groq forecast planner  (implements ForecastPlanner protocol)
# ---------------------------------------------------------------------------

class GroqForecastPlanner:
    """Forecast planner backed by Groq's API."""

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.groq_api_key
        self._groq = _GroqChatClient(
            settings.groq_api_key or "",
            settings.groq_model,
            settings.groq_base_url,
        )

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._groq.set_client(client)

    async def generate_forecast_plan(
        self, question: str, schema: dict[str, str]
    ) -> dict[str, Any]:
        if not self._api_key:
            raise LLMError(
                "GROQ_API_KEY is not configured. "
                "Set the GROQ_API_KEY environment variable."
            )
        schema_lines = "\n".join(f"- {n}: {t}" for n, t in schema.items())
        user_prompt = (
            f"Dataset columns (name: type):\n{schema_lines}\n\n"
            f"Question: {question}\nJSON plan:"
        )
        return await self._groq.chat(_FORECAST_SYSTEM_PROMPT, user_prompt)


# ---------------------------------------------------------------------------
# Fallback wrapper base
# ---------------------------------------------------------------------------

class _Fallback:
    """Tries the primary planner; on LLMError falls back to secondary.

    Subclasses just implement the protocol method and delegate via _try().
    """

    def __init__(self, primary: Any, secondary: Any) -> None:
        self._primary = primary
        self._secondary = secondary

    def set_client(self, client: httpx.AsyncClient) -> None:
        for p in (self._primary, self._secondary):
            if hasattr(p, "set_client"):
                p.set_client(client)

    async def _try(self, method: str, *args: Any) -> dict[str, Any]:
        try:
            return await getattr(self._primary, method)(*args)
        except LLMError as exc:
            logger.warning("Primary planner failed (%s); falling back to secondary.", exc)
            return await getattr(self._secondary, method)(*args)


class FallbackQueryPlanner(_Fallback):
    async def generate_plan(self, question: str, schema: dict[str, str]) -> dict[str, Any]:
        return await self._try("generate_plan", question, schema)


class FallbackForecastPlanner(_Fallback):
    async def generate_forecast_plan(self, question: str, schema: dict[str, str]) -> dict[str, Any]:
        return await self._try("generate_forecast_plan", question, schema)
