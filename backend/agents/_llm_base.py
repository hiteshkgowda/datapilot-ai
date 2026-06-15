"""Shared HTTP dispatch for single-provider LLM agents.

InsightAgent and RootCauseAgent both talk to Groq or Ollama with identical
wire formats.  This base class owns the network calls so subclasses only
implement prompt construction and response parsing.

Provider selection: Groq when GROQ_API_KEY is set, otherwise Ollama.
On any HTTP or parse failure, subclasses handle the fallback via their
own generate() / _fallback_from_findings() methods — this class just raises.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.core.config import Settings


class LLMAgentBase:
    """HTTP dispatch for Groq / Ollama agents.

    Subclasses set _groq_max_tokens if they need a different token limit,
    then call _call_provider(system_prompt, user_prompt) to get a raw string
    back from whichever provider is active.
    """

    _groq_max_tokens: int = 1024

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Optional[httpx.AsyncClient] = None

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _call_provider(self, system_prompt: str, user_prompt: str) -> str:
        """Route to Groq or Ollama based on settings. Raises on any failure."""
        if self._settings.groq_api_key:
            return await self._call_groq(system_prompt, user_prompt)
        return await self._call_ollama(system_prompt, user_prompt)

    async def _call_groq(self, system_prompt: str, user_prompt: str) -> str:
        assert self._client is not None  # caller checks before calling

        payload: dict[str, Any] = {
            "model": self._settings.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": self._groq_max_tokens,
        }
        response = await self._client.post(
            f"{self._settings.groq_base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self._settings.groq_api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])

    async def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        assert self._client is not None

        payload: dict[str, Any] = {
            "model": self._settings.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        response = await self._client.post(
            f"{self._settings.ollama_base_url}/api/chat",
            json=payload,
        )
        response.raise_for_status()
        return str(response.json()["message"]["content"])
