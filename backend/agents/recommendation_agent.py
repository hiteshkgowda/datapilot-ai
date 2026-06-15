"""LLM Enhancement Agent for the Recommendation Engine.

Follows the same set_client() / _call_groq() / _call_ollama() pattern as
InsightAgent and RootCauseAgent.

Anti-hallucination guarantees
------------------------------
- Receives ONLY the rule-based recommendations as input (structured JSON).
- System prompt explicitly forbids the model from inventing numbers, column
  names, or facts not present in the input.
- Temperature = 0.1 for near-deterministic output.
- Any exception → agent returns the original rule-based recommendations
  unchanged.  The service never surfaces LLM errors to the caller.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from app.core.config import Settings
from app.core.math_utils import strip_json_fences
from app.schemas.recommendation import Recommendation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a concise business-writing assistant for a data analytics platform.

Your job is to improve the language quality of pre-written data recommendations.

STRICT RULES — violation is not allowed:
1. You must NOT invent, fabricate, or modify any numbers, percentages, metric names,
   column names, dates, row indices, or statistical values.  Every fact in the output
   must come from the input recommendations verbatim.
2. You must NOT add new recommendations or remove existing ones.
3. You must NOT change the priority, category, source, confidence, or data_points fields.
4. You may ONLY rewrite the "action", "reason", and "expected_impact" fields to be:
   - More concise (aim for ≤20 words per field where possible)
   - More business-friendly in tone
   - More specific and actionable
5. Return a JSON array of recommendation objects.  Every object in your output must
   have exactly the same fields as the corresponding input object.
6. If you cannot improve a recommendation without violating these rules, return it unchanged.
7. Do NOT wrap the JSON in markdown code fences.  Return raw JSON only.
8. The array length must equal the input array length exactly.
"""

_USER_TEMPLATE = """\
Business context: {context}

Improve the language quality of these {n} data-driven recommendations.
Follow all STRICT RULES in the system prompt.

INPUT RECOMMENDATIONS:
{recs_json}
"""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class RecommendationAgent:
    """Thin LLM wrapper that polishes rule-based recommendations."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Optional[httpx.AsyncClient] = None

    # --------------------------------------------------------------------- #
    # Lifecycle (called by main.py lifespan)
    # --------------------------------------------------------------------- #

    def set_client(self, client: httpx.AsyncClient) -> None:
        self._client = client

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    async def enhance(
        self,
        recommendations: list[Recommendation],
        context: Optional[str],
        dataset_id: str,
    ) -> Optional[list[Recommendation]]:
        """Return language-polished recommendations, or None on any error."""
        if not self._client:
            logger.debug("RecommendationAgent: no HTTP client — skipping LLM enhancement.")
            return None
        if not recommendations:
            return None

        recs_json = json.dumps(
            [r.model_dump() for r in recommendations],
            indent=2,
            default=str,
        )
        prompt = _USER_TEMPLATE.format(
            context=context or "general business analysis",
            n=len(recommendations),
            recs_json=recs_json,
        )

        raw: Optional[str] = None
        if self._settings.groq_api_key:
            raw = await self._call_groq(prompt)
        if raw is None and self._settings.ollama_base_url:
            raw = await self._call_ollama(prompt)

        if raw is None:
            return None

        return self._parse_response(raw, recommendations)

    # --------------------------------------------------------------------- #
    # LLM back-ends
    # --------------------------------------------------------------------- #

    async def _call_groq(self, user_prompt: str) -> Optional[str]:
        try:
            resp = await self._client.post(
                f"{self._settings.groq_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._settings.groq_model or "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("RecommendationAgent._call_groq failed: %s", exc)
            return None

    async def _call_ollama(self, user_prompt: str) -> Optional[str]:
        try:
            resp = await self._client.post(
                f"{self._settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self._settings.ollama_model or "llama3.2",
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1},
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"].strip()
        except Exception as exc:
            logger.warning("RecommendationAgent._call_ollama failed: %s", exc)
            return None

    # --------------------------------------------------------------------- #
    # Response parsing
    # --------------------------------------------------------------------- #

    def _parse_response(
        self,
        raw: str,
        originals: list[Recommendation],
    ) -> Optional[list[Recommendation]]:
        """Parse LLM JSON output and fall back to originals on any error."""
        try:
            text = strip_json_fences(raw)

            parsed: list[dict[str, Any]] = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError("Expected JSON array")
            if len(parsed) != len(originals):
                raise ValueError(
                    f"Length mismatch: got {len(parsed)}, expected {len(originals)}"
                )

            enhanced: list[Recommendation] = []
            for enhanced_dict, original in zip(parsed, originals):
                # Merge: only override the three text fields; keep all data fields.
                merged = original.model_dump()
                for field in ("action", "reason", "expected_impact"):
                    if field in enhanced_dict and isinstance(enhanced_dict[field], str):
                        text_val = enhanced_dict[field].strip()
                        if text_val:
                            merged[field] = text_val
                enhanced.append(Recommendation(**merged))

            return enhanced

        except Exception as exc:
            logger.warning(
                "RecommendationAgent._parse_response: parse error (%s) — returning originals.",
                exc,
            )
            return originals
