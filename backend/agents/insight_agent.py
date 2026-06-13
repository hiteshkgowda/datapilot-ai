"""AI Insight Generation Agent.

Role
----
Takes a StatisticalFindings object (computed deterministically by InsightStatEngine)
and uses LLM reasoning to produce natural-language insights.

Anti-hallucination design
-------------------------
1. The LLM system prompt explicitly forbids referencing facts not present in
   the StatisticalFindings JSON that is injected into the user prompt.
2. Temperature is set to 0.1 — deterministic, minimal creative license.
3. If the LLM is unreachable or returns invalid JSON, _fallback_from_findings()
   produces a guaranteed-correct statistical summary without any LLM call.
4. The parse step rejects the LLM output and falls back if required keys are
   missing or types are wrong.

HTTP client
-----------
Follows the same set_client() pattern as OllamaQueryPlanner / GroqQueryPlanner
so the shared lifespan-managed httpx.AsyncClient is injected at startup and
closed cleanly on shutdown.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from app.core.config import Settings
from app.schemas.insight import InsightResponse, StatisticalFindings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — injected on every call to anchor the LLM to the data
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a rigorous data analysis assistant. You receive structured statistical findings that were computed deterministically from a dataset.

YOUR ONLY JOB: Translate these statistical facts into clear, precise, data-grounded natural language.

STRICT RULES — NEVER BREAK THESE:
1. ONLY reference data, columns, values, and patterns that appear in the STATISTICAL FINDINGS below.
2. NEVER invent numbers, trends, correlations, or patterns that are absent from the findings.
3. NEVER speculate about causes, future outcomes, or external factors.
4. NEVER use placeholders like "N/A" for fields that have real data in the findings.
5. If a findings section is empty (e.g. no correlations found), output [] for that field — do not invent correlations.
6. Quote specific numbers from the findings when making claims (e.g. "mean of 4,231.5").

OUTPUT FORMAT — return ONLY valid JSON, no markdown, no explanation:
{
  "summary": "One paragraph. State what the dataset is about based on column names and row count. Reference at least 2 specific numbers.",
  "key_insights": ["insight 1 with a specific number", "insight 2 with a specific number"],
  "trends": ["Column X is increasing with a slope of Y (first: A → last: B, change: C%)"],
  "top_performers": [{"label": "row label", "value": 123.4, "metric": "column_name", "rank": 1}],
  "underperformers": [{"label": "row label", "value": 0.1, "metric": "column_name", "rank": 1}],
  "recommendations": ["Actionable recommendation supported directly by a specific finding"]
}"""


class InsightAgent:
    """LLM reasoning layer — takes statistical findings, produces InsightResponse.

    Supports both Groq (OpenAI-compatible) and Ollama (local) with automatic
    provider selection based on Settings.  Falls back to a deterministic
    statistics-only response on any failure.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Optional[httpx.AsyncClient] = None

    def set_client(self, client: httpx.AsyncClient) -> None:
        """Attach the shared HTTP client.  Called once from the app lifespan."""
        self._client = client

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    async def generate(
        self,
        findings: StatisticalFindings,
        question: str,
    ) -> InsightResponse:
        """Generate insights from statistical findings.

        Tries the LLM; falls back silently to a purely statistical response
        if the LLM is unavailable or returns unparseable output.

        Never raises.
        """
        if self._client is None:
            logger.warning(
                "InsightAgent: HTTP client not set — using statistical fallback."
            )
            return self._fallback_from_findings(findings)

        try:
            return await self._call_llm(findings, question)
        except Exception as exc:
            logger.warning(
                "InsightAgent: LLM call failed (%s) — using statistical fallback.", exc
            )
            return self._fallback_from_findings(findings)

    # ------------------------------------------------------------------ #
    # LLM dispatch
    # ------------------------------------------------------------------ #

    async def _call_llm(
        self, findings: StatisticalFindings, question: str
    ) -> InsightResponse:
        user_prompt = self._build_user_prompt(findings, question)

        if self._settings.groq_api_key:
            raw = await self._call_groq(user_prompt)
        else:
            raw = await self._call_ollama(user_prompt)

        return self._parse_response(raw, findings)

    async def _call_groq(self, user_prompt: str) -> str:
        assert self._client is not None  # guaranteed by caller

        payload: dict[str, Any] = {
            "model": self._settings.groq_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 1024,
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
        data: dict[str, Any] = response.json()
        return str(data["choices"][0]["message"]["content"])

    async def _call_ollama(self, user_prompt: str) -> str:
        assert self._client is not None

        payload: dict[str, Any] = {
            "model": self._settings.ollama_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
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
        data: dict[str, Any] = response.json()
        return str(data["message"]["content"])

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def _build_user_prompt(
        self, findings: StatisticalFindings, question: str
    ) -> str:
        findings_json = json.dumps(findings.model_dump(), indent=2, default=str)
        return (
            f"ORIGINAL USER QUESTION: {question}\n\n"
            f"STATISTICAL FINDINGS (the ONLY facts you may reference — "
            f"do not invent anything beyond these):\n"
            f"```json\n{findings_json}\n```\n\n"
            "Generate the JSON insight analysis now."
        )

    # ------------------------------------------------------------------ #
    # Response parsing
    # ------------------------------------------------------------------ #

    def _parse_response(
        self,
        raw_content: str,
        findings: StatisticalFindings,
    ) -> InsightResponse:
        """Parse LLM JSON; fall back to statistics if parsing fails."""
        try:
            data: dict[str, Any] = json.loads(raw_content)
            return InsightResponse(
                summary=str(data.get("summary", "")).strip(),
                key_insights=_to_str_list(data.get("key_insights")),
                trends=_to_str_list(data.get("trends")),
                top_performers=_to_dict_list(data.get("top_performers")),
                underperformers=_to_dict_list(data.get("underperformers")),
                recommendations=_to_str_list(data.get("recommendations")),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "InsightAgent: failed to parse LLM JSON response (%s); "
                "using statistical fallback.",
                exc,
            )
            return self._fallback_from_findings(findings)

    # ------------------------------------------------------------------ #
    # Statistical fallback (guaranteed correct — no LLM)
    # ------------------------------------------------------------------ #

    def _fallback_from_findings(self, findings: StatisticalFindings) -> InsightResponse:
        """Build a purely data-driven InsightResponse without any LLM call.

        Every claim here is derived from specific fields in StatisticalFindings.
        Zero hallucination risk.
        """
        # ── Summary ──────────────────────────────────────────────────────────
        parts = [
            f"The dataset contains {findings.row_count} rows "
            f"and {findings.column_count} columns."
        ]
        if findings.numeric_columns:
            parts.append(
                f"Numeric columns: {', '.join(findings.numeric_columns)}."
            )
        if findings.categorical_columns:
            parts.append(
                f"Categorical columns: {', '.join(findings.categorical_columns)}."
            )
        summary = " ".join(parts)

        # ── Key insights (one per numeric column with basic stats) ───────────
        key_insights: list[str] = []
        for stat in findings.column_stats:
            if stat.mean is not None and stat.min is not None and stat.max is not None:
                key_insights.append(
                    f"{stat.column}: mean = {stat.mean:.2f}, "
                    f"range [{stat.min:.2f} – {stat.max:.2f}]"
                    + (
                        f", std = {stat.std:.2f}"
                        if stat.std is not None
                        else ""
                    )
                )
        key_insights = key_insights[:5]

        # ── Trends ───────────────────────────────────────────────────────────
        trend_strs: list[str] = []
        for t in findings.trends:
            change = (
                f" ({t.change_pct:+.1f}% total)" if t.change_pct is not None else ""
            )
            trend_strs.append(
                f"{t.column} is {t.direction} (slope = {t.slope:.4f}){change}"
            )

        # ── Performers ───────────────────────────────────────────────────────
        top_performers = [p.model_dump() for p in findings.top_performers]
        underperformers = [p.model_dump() for p in findings.underperformers]

        # ── Recommendations based on correlations and growth ────────────────
        recommendations: list[str] = []
        for corr in findings.correlations:
            if "strong" in corr.strength:
                direction_word = "positive" if "positive" in corr.strength else "negative"
                recommendations.append(
                    f"Strong {direction_word} correlation detected between "
                    f"'{corr.column_a}' and '{corr.column_b}' (r = {corr.coefficient:.2f}). "
                    f"Investigate the relationship for potential predictive value."
                )
        for gp in findings.growth_patterns:
            if gp.pattern == "volatile" and gp.avg_period_change_pct is not None:
                recommendations.append(
                    f"'{gp.column}' is volatile (avg change = "
                    f"{gp.avg_period_change_pct:+.1f}% per period). "
                    f"Consider smoothing or monitoring for stability."
                )

        return InsightResponse(
            summary=summary,
            key_insights=key_insights,
            trends=trend_strs,
            top_performers=top_performers,
            underperformers=underperformers,
            recommendations=recommendations,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_str_list(val: Any) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(item).strip() for item in val if item]


def _to_dict_list(val: Any) -> list[dict[str, Any]]:
    if not isinstance(val, list):
        return []
    return [item for item in val if isinstance(item, dict)]
