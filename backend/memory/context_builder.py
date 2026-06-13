"""Translates stored conversation turns into LLM-ready context strings.

ContextBuilder is stateless — all methods are static so the class can be used
as a singleton without instantiation overhead.

Agent prompt format (matches agent_planner._build_user_prompt expectations):
  conversation_history = [{"goal": str, "summary": str}, ...]
"""

from __future__ import annotations


class ContextBuilder:
    """Format conversation turns for injection into LLM prompts."""

    @staticmethod
    def build_agent_context(turns: list[dict]) -> list[dict]:
        """Convert turns to the agent planner's conversation_history format.

        Returns list of {"goal": str, "summary": str} dicts.
        The planner renders these as:
          "- User: <goal>  |  Assistant: <summary>"
        """
        items = []
        for t in turns:
            goal = (
                t.get("question")
                or f"[{t.get('turn_type', 'action')} on dataset {t.get('dataset_id', '?')}]"
            )
            summary = _summarize_turn(t)
            items.append({"goal": goal, "summary": summary})
        return items

    @staticmethod
    def build_summary(turns: list[dict], max_chars: int = 800) -> str:
        """Build a human-readable summary of the session for display."""
        if not turns:
            return "No prior conversation in this session."
        lines: list[str] = []
        for t in turns[-10:]:
            turn_type = t.get("turn_type", "?")
            question = t.get("question") or ""
            answer_snippet = (t.get("answer") or "")[:120]
            if answer_snippet:
                lines.append(f"[{turn_type}] {question} → {answer_snippet}")
            else:
                lines.append(f"[{turn_type}] {question or '(no question)'}")
        text = "\n".join(lines)
        return text[-max_chars:] if len(text) > max_chars else text

    @staticmethod
    def extract_dataset_ids(turns: list[dict]) -> list[str]:
        """Return unique dataset IDs referenced across turns, most-recent first."""
        seen: list[str] = []
        for t in reversed(turns):
            ds = t.get("dataset_id")
            if ds and ds not in seen:
                seen.append(ds)
        return seen


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _summarize_turn(t: dict) -> str:
    """Produce a short assistant-style summary for one stored turn."""
    turn_type = t.get("turn_type", "unknown")
    answer = (t.get("answer") or "")[:200]

    if turn_type == "query":
        rows = len(t.get("table_data") or [])
        return f"Query returned {rows} row(s). {answer}".strip()

    if turn_type == "chart":
        chart = t.get("chart_spec") or {}
        chart_type = (
            chart.get("chart_type")
            or (chart.get("data") or {}).get("type")
            or "chart"
        )
        return f"Generated a {chart_type}. {answer}".strip()

    if turn_type == "forecast":
        fc = t.get("forecast") or {}
        horizon = fc.get("horizon", "?")
        freq = fc.get("frequency", "")
        return f"Forecasted {horizon} {freq} period(s). {answer}".strip()

    if turn_type == "anomaly":
        anom = t.get("anomalies") or {}
        count = anom.get("total_anomaly_count", "?")
        severity = anom.get("severity", "")
        return f"Detected {count} anomalies (severity: {severity}).".strip()

    if turn_type == "insight":
        insights_blob = t.get("insights") or {}
        n = (
            len(insights_blob.get("insights", []))
            if isinstance(insights_blob, dict)
            else "?"
        )
        return f"Generated {n} insight(s). {answer}".strip()

    if turn_type == "recommendation":
        recs_blob = t.get("recommendations") or {}
        n = recs_blob.get("total_count", "?") if isinstance(recs_blob, dict) else "?"
        return f"Generated {n} recommendation(s).".strip()

    if turn_type == "report":
        return f"Generated report. {answer}".strip()

    if turn_type == "agent":
        return answer or "Agent task completed."

    return answer or ""
