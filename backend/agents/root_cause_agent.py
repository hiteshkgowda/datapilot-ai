"""Root Cause Analysis Agent — LLM reasoning layer.

Takes RCAFindings (computed deterministically by RCAEngine) and uses LLM
reasoning to produce natural-language root causes, a ranked problem
statement, and actionable recommendations.

Anti-hallucination guarantees
------------------------------
1. The system prompt explicitly forbids referencing any fact not present in
   the RCAFindings JSON that is injected into the user prompt.
2. Temperature = 0.1 — near-deterministic output.
3. All LLM outputs are structurally validated against the expected JSON schema.
4. On any failure (unreachable LLM, invalid JSON, missing keys), the agent
   falls back to _fallback_from_findings() which generates the full response
   purely from RCAFindings with zero LLM involvement.

HTTP client
-----------
Inherits set_client() and provider dispatch from LLMAgentBase. The shared
lifespan-managed httpx.AsyncClient is injected at startup.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents._llm_base import LLMAgentBase
from app.schemas.root_cause import (
    RCAFindings,
    RootCause,
    RootCauseResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a rigorous data analyst performing Root Cause Analysis.

You receive structured statistical findings computed from a dataset.
Your job is to translate these findings into a clear, precise, data-grounded analysis.

STRICT ANTI-HALLUCINATION RULES:
1. ONLY reference columns, values, and numbers that appear in the STATISTICAL FINDINGS below.
2. Do NOT invent causes, assumptions, or external context not in the data.
3. Do NOT speculate about why something happened outside of what the numbers show.
4. Quote specific numbers (contribution_pct, absolute_change, percentage_change) in your descriptions.
5. Impact levels: "high" if |contribution_pct| ≥ 30, "medium" if ≥ 10, else "low".
6. Recommendations must be directly supported by a specific finding (dimension, value, number).

OUTPUT: Return ONLY valid JSON matching this exact structure:
{
  "problem": "One sentence with metric name, direction (dropped/grew), percentage change, and period labels.",
  "root_causes": [
    {
      "dimension": "column name",
      "value": "specific value",
      "impact_level": "high|medium|low",
      "description": "One sentence with specific numbers from findings.",
      "contribution_pct": 45.2,
      "rank": 1
    }
  ],
  "recommendations": [
    "Specific recommendation that references the root cause by name and number."
  ]
}

Rules for root_causes:
- Include at most 5 root causes.
- Rank by |contribution_pct| descending.
- Only include causes where |contribution_pct| ≥ 5.
- If no causes meet the threshold, include the top 3.
"""


class RootCauseAgent(LLMAgentBase):
    """LLM reasoning for Root Cause Analysis.

    Supports Groq (OpenAI-compatible) and Ollama (local) with automatic
    provider selection.  Always produces a valid response even on failure.
    """

    _groq_max_tokens = 1500

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    async def generate(
        self,
        findings: RCAFindings,
        question: str,
    ) -> RootCauseResponse:
        """Generate root cause analysis from statistical findings.

        Falls back to a deterministic statistical response on any failure.
        Never raises.
        """
        if self._client is None:
            logger.warning("RootCauseAgent: no HTTP client — using statistical fallback.")
            return self._fallback_from_findings(findings)

        try:
            return await self._call_llm(findings, question)
        except Exception as exc:
            logger.warning("RootCauseAgent: LLM call failed (%s) — using fallback.", exc)
            return self._fallback_from_findings(findings)

    # ------------------------------------------------------------------ #
    # LLM dispatch
    # ------------------------------------------------------------------ #

    async def _call_llm(
        self, findings: RCAFindings, question: str
    ) -> RootCauseResponse:
        user_prompt = self._build_prompt(findings, question)
        raw = await self._call_provider(_SYSTEM_PROMPT, user_prompt)
        return self._parse_response(raw, findings)

    # ------------------------------------------------------------------ #
    # Prompt construction
    # ------------------------------------------------------------------ #

    def _build_prompt(self, findings: RCAFindings, question: str) -> str:
        findings_json = json.dumps(findings.model_dump(), indent=2, default=str)
        return (
            f"ORIGINAL USER QUESTION: {question}\n\n"
            f"STATISTICAL FINDINGS (the ONLY facts you may reference):\n"
            f"```json\n{findings_json}\n```\n\n"
            "Generate the root cause analysis JSON now. "
            "Reference specific numbers. Do not invent anything outside the findings."
        )

    # ------------------------------------------------------------------ #
    # Response parsing
    # ------------------------------------------------------------------ #

    def _parse_response(
        self, raw_content: str, findings: RCAFindings
    ) -> RootCauseResponse:
        """Parse LLM JSON; fall back to statistics on failure."""
        try:
            data: dict[str, Any] = json.loads(raw_content)
            root_causes = self._parse_root_causes(data.get("root_causes", []), findings)
            return RootCauseResponse(
                problem=str(data.get("problem", "")).strip(),
                root_causes=root_causes,
                contribution_analysis=findings.contributions,
                recommendations=_to_str_list(data.get("recommendations")),
                metric_column=findings.metric_column,
                period_column=findings.period_column,
                current_period=findings.current_period.label,
                previous_period=findings.previous_period.label,
                current_total=findings.current_period.total,
                previous_total=findings.previous_period.total,
                total_change_pct=findings.total_pct_change,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "RootCauseAgent: failed to parse LLM response (%s); falling back.", exc
            )
            return self._fallback_from_findings(findings)

    def _parse_root_causes(
        self, raw: Any, findings: RCAFindings
    ) -> list[RootCause]:
        if not isinstance(raw, list):
            return self._root_causes_from_findings(findings)

        causes: list[RootCause] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                impact = str(item.get("impact_level", "low")).lower()
                if impact not in ("high", "medium", "low"):
                    impact = "low"
                causes.append(
                    RootCause(
                        dimension=str(item.get("dimension", "")),
                        value=str(item.get("value", "")),
                        impact_level=impact,
                        description=str(item.get("description", "")).strip(),
                        contribution_pct=float(item.get("contribution_pct", 0.0)),
                        rank=int(item.get("rank", len(causes) + 1)),
                    )
                )
            except (TypeError, ValueError):
                continue

        return causes or self._root_causes_from_findings(findings)

    # ------------------------------------------------------------------ #
    # Statistical fallback — guaranteed correct, zero LLM
    # ------------------------------------------------------------------ #

    def _fallback_from_findings(self, findings: RCAFindings) -> RootCauseResponse:
        """Build a complete RootCauseResponse purely from RCAFindings.

        Every claim here is directly derived from findings fields.
        Zero hallucination risk.
        """
        problem = self._build_problem_statement(findings)
        root_causes = self._root_causes_from_findings(findings)
        recommendations = self._build_recommendations(findings)

        return RootCauseResponse(
            problem=problem,
            root_causes=root_causes,
            contribution_analysis=findings.contributions,
            recommendations=recommendations,
            metric_column=findings.metric_column,
            period_column=findings.period_column,
            current_period=findings.current_period.label,
            previous_period=findings.previous_period.label,
            current_total=findings.current_period.total,
            previous_total=findings.previous_period.total,
            total_change_pct=findings.total_pct_change,
        )

    def _build_problem_statement(self, findings: RCAFindings) -> str:
        direction_word = {
            "decline": "dropped",
            "growth": "grew",
            "flat": "remained flat",
        }.get(findings.direction, "changed")

        pct_str = f"{abs(findings.total_pct_change):.1f}%"
        prev_lbl = findings.previous_period.label
        curr_lbl = findings.current_period.label
        metric = findings.metric_column

        if findings.direction == "flat":
            return (
                f"{metric} remained flat between {prev_lbl} and {curr_lbl} "
                f"({findings.previous_period.total:,.2f} → {findings.current_period.total:,.2f})."
            )

        return (
            f"{metric.capitalize()} {direction_word} {pct_str} "
            f"from {findings.previous_period.total:,.2f} to "
            f"{findings.current_period.total:,.2f} "
            f"(period: {prev_lbl} → {curr_lbl})."
        )

    def _root_causes_from_findings(self, findings: RCAFindings) -> list[RootCause]:
        causes: list[RootCause] = []
        seen_dims: set[str] = set()

        for c in findings.contributions[:5]:
            if abs(c.contribution_pct) < 1e-4:
                continue

            abs_pct = abs(c.contribution_pct)
            impact = "high" if abs_pct >= 30 else ("medium" if abs_pct >= 10 else "low")

            same_direction = (
                (c.absolute_change < 0) == (findings.total_absolute_change < 0)
            )
            role = "primary driver" if same_direction else "partial offset"

            pct_ch_str = (
                f"{c.percentage_change:+.1f}%"
                if abs(c.percentage_change) < 999_999
                else "N/A"
            )
            description = (
                f"{c.dimension.capitalize()} '{c.value}' {role}: "
                f"{c.absolute_change:+,.2f} change ({pct_ch_str} period-over-period), "
                f"accounting for {c.contribution_pct:.1f}% of total {findings.direction}."
            )

            causes.append(
                RootCause(
                    dimension=c.dimension,
                    value=c.value,
                    impact_level=impact,
                    description=description,
                    contribution_pct=c.contribution_pct,
                    rank=c.rank,
                )
            )
            seen_dims.add(c.dimension)

        return causes

    def _build_recommendations(self, findings: RCAFindings) -> list[str]:
        recs: list[str] = []
        added_dims: set[str] = set()

        for c in findings.contributions[:5]:
            if abs(c.contribution_pct) < 5.0:
                break
            if c.dimension in added_dims:
                continue
            added_dims.add(c.dimension)

            same_dir = (
                (c.absolute_change < 0) == (findings.total_absolute_change < 0)
            )

            if findings.direction == "decline" and same_dir:
                recs.append(
                    f"Investigate {c.dimension} '{c.value}' which drove "
                    f"{abs(c.contribution_pct):.1f}% of the {findings.metric_column} decline "
                    f"({c.absolute_change:+,.2f}). Identify root cause and set recovery targets."
                )
            elif findings.direction == "growth" and same_dir:
                recs.append(
                    f"Scale {c.dimension} '{c.value}' which drove "
                    f"{abs(c.contribution_pct):.1f}% of {findings.metric_column} growth. "
                    f"Replicate success in other {c.dimension} segments."
                )
            elif not same_dir:
                recs.append(
                    f"Protect {c.dimension} '{c.value}' which is offsetting "
                    f"{abs(c.contribution_pct):.1f}% of the overall change — "
                    f"this segment is performing against the trend."
                )

        return recs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_str_list(val: Any) -> list[str]:
    if not isinstance(val, list):
        return []
    return [str(item).strip() for item in val if item]
