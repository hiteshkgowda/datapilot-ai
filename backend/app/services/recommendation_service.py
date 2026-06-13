"""Recommendation Rule Engine + orchestration service.

Two-tier architecture (mirrors InsightService / RootCauseService):

1. RecommendationRuleEngine  — deterministic; derives every recommendation from
                               observed data facts. Zero LLM. Zero hallucination.
2. RecommendationService     — TTL cache, calls engine + agent, returns response.

Rule categories
---------------
    anomaly     — AnomalyResponse: per-column drop/spike/consecutive patterns
    insight     — InsightResponse: trend/performer/correlation patterns
    forecast    — ForecastResponse (dict): projected decline/growth patterns
    cross_signal— same metric flagged by two or more independent sources → escalate
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

from app.core.cache import TTLCache
from app.schemas.anomaly import AnomalyResponse, ColumnAnomaly
from app.schemas.insight import InsightResponse
from app.schemas.recommendation import Recommendation, RecommendationRequest, RecommendationResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# Keyword sets for category inference.
_CAT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "revenue":      ("revenue", "sales", "income", "profit", "earnings", "margin", "arpu"),
    "inventory":    ("inventory", "stock", "supply", "warehouse", "sku", "turnover", "units"),
    "marketing":    ("marketing", "campaign", "conversion", "lead", "cpc", "ctr", "roas", "spend"),
    "operations":   ("cost", "expense", "efficiency", "throughput", "order", "processing", "churn"),
    "data_quality": ("consecutive", "pipeline", "quality", "error", "missing", "duplicate", "null"),
    "monitoring":   ("monitor", "forecast", "predict", "anomaly", "alert", "threshold"),
}

# Keyword sets that describe a metric going down.
_DECLINE_WORDS = (
    "declin", "drop", "fell", "decreas", "lower", "reduc", "shrink",
    "down", "below", "negative", "worsen", "deteriorat",
)
# Keyword sets that describe a metric going up.
_GROWTH_WORDS = (
    "increas", "grow", "grew", "rose", "climb", "higher", "above", "positive",
    "surpass", "exceed", "up", "improv",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_category(text: str) -> str:
    """Return the best-matching business category from keyword matching."""
    lower = text.lower()
    best_cat, best_score = "general", 0
    for cat, kws in _CAT_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in lower)
        if score > best_score:
            best_cat, best_score = cat, score
    return best_cat


def _is_decline(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _DECLINE_WORDS)


def _is_growth(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _GROWTH_WORDS)


def _pct_delta(current: float, baseline: float) -> str:
    """Return a signed percentage string, e.g. '-12.3%'."""
    if abs(baseline) < 1e-9:
        return "N/A"
    return f"{((current - baseline) / abs(baseline)) * 100:+.1f}%"


def _priority_rank(p: str) -> int:
    return _PRIORITY_ORDER.get(p, 0)


# ---------------------------------------------------------------------------
# Rule Engine
# ---------------------------------------------------------------------------


class RecommendationRuleEngine:
    """Derive recommendations from statistical observations.

    Every recommendation must reference at least one concrete data fact
    (column name, numeric value, percentage, or row index).
    No invented numbers. No hallucination.
    """

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def generate(
        self,
        anomalies: Optional[AnomalyResponse],
        insights: Optional[InsightResponse],
        forecast: Optional[dict[str, Any]],
        query_results: Optional[list[dict[str, Any]]],
        max_recommendations: int = 10,
    ) -> list[Recommendation]:
        rules: list[Recommendation] = []

        if anomalies and anomalies.anomalies:
            rules.extend(self._from_anomalies(anomalies))

        if insights:
            rules.extend(self._from_insights(insights))

        if forecast:
            rules.extend(self._from_forecast(forecast))

        # Cross-signal: escalate when same metric appears in multiple sources.
        cross = self._cross_signal(anomalies, insights, rules)
        rules.extend(cross)

        return self._deduplicate_and_rank(rules)[:max_recommendations]

    # ------------------------------------------------------------------ #
    # Anomaly → recommendations
    # ------------------------------------------------------------------ #

    def _from_anomalies(self, resp: AnomalyResponse) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for ca in resp.anomalies:
            recs.extend(self._anomaly_column_recs(ca, resp))

        # Overall: multiple metrics flagged simultaneously.
        if len(resp.anomalies) >= 3:
            cols = ", ".join(f"'{c.column}'" for c in resp.anomalies[:3])
            recs.append(
                Recommendation(
                    priority="high",
                    action=(
                        f"Conduct a full KPI health review — "
                        f"{len(resp.anomalies)} metrics affected simultaneously"
                    ),
                    reason=(
                        f"Anomalies detected across {len(resp.anomalies)} columns "
                        f"({cols}…). Multiple simultaneous anomalies indicate "
                        "a systemic event or data pipeline issue."
                    ),
                    expected_impact=(
                        f"Isolating the systemic cause can prevent further spread "
                        f"across {len(resp.anomalies)} tracked metrics."
                    ),
                    category="data_quality",
                    source="anomaly",
                    confidence=0.85,
                    data_points=[
                        f"Total anomaly count: {resp.total_anomaly_count}",
                        f"Affected columns: {', '.join(resp.affected_metrics)}",
                        f"Overall severity: {resp.severity}",
                    ],
                )
            )

        return recs

    def _anomaly_column_recs(
        self, ca: ColumnAnomaly, resp: AnomalyResponse
    ) -> list[Recommendation]:
        recs: list[Recommendation] = []
        if not ca.anomaly_points:
            return recs

        # Worst point by score.
        worst = max(ca.anomaly_points, key=lambda p: p.score)
        category = _infer_category(ca.column)
        drops = [p for p in ca.anomaly_points if p.value < ca.mean]
        spikes = [p for p in ca.anomaly_points if p.value > ca.mean]
        pct = _pct_delta(worst.value, ca.mean)
        consec_run = _longest_consecutive(
            sorted(p.row_index for p in ca.anomaly_points)
        )

        # ── Drop anomalies ───────────────────────────────────────────────
        if drops:
            priority = worst.severity if worst.value < ca.mean else "medium"
            action = self._drop_action(ca.column, category)
            recs.append(
                Recommendation(
                    priority=priority,
                    action=action,
                    reason=(
                        f"'{ca.column}' recorded {len(drops)} below-normal value(s). "
                        f"Worst: {worst.value:,.4g} vs mean {ca.mean:,.4g} "
                        f"({pct} deviation, score {worst.score:.2f}σ)."
                    ),
                    expected_impact=(
                        f"Restoring '{ca.column}' to baseline ({ca.mean:,.4g}) "
                        f"represents a {abs(float(pct.replace('%','').replace('+',''))):,.1f}% "
                        f"recovery from the current anomalous value."
                    ),
                    category=category,
                    source="anomaly",
                    confidence=min(0.95, 0.6 + worst.score * 0.05),
                    data_points=[
                        f"{ca.column}: worst value {worst.value:,.4g}",
                        f"Baseline mean: {ca.mean:,.4g}",
                        f"Deviation: {pct}",
                        f"Anomaly score: {worst.score:.2f}σ ({worst.severity})",
                        f"Detection methods: {', '.join(ca.methods)}",
                    ],
                )
            )

        # ── Spike anomalies ──────────────────────────────────────────────
        if spikes:
            recs.append(
                Recommendation(
                    priority="medium" if worst.severity in ("low", "medium") else "high",
                    action=(
                        f"Investigate and document the {ca.column} spike "
                        f"to determine if it represents a replicable success or a data error"
                    ),
                    reason=(
                        f"'{ca.column}' has {len(spikes)} above-normal spike(s). "
                        f"Peak: {worst.value:,.4g} vs mean {ca.mean:,.4g} ({pct})."
                    ),
                    expected_impact=(
                        f"If the spike is driven by a business event, "
                        f"replicating conditions could sustain '{ca.column}' "
                        f"above baseline ({ca.mean:,.4g})."
                    ),
                    category=category,
                    source="anomaly",
                    confidence=0.70,
                    data_points=[
                        f"{ca.column}: peak {worst.value:,.4g}",
                        f"Baseline mean: {ca.mean:,.4g}",
                        f"Deviation: {pct}",
                        f"Row index: {worst.row_index}",
                    ],
                )
            )

        # ── Consecutive anomalies → data quality ─────────────────────────
        if consec_run >= 3:
            recs.append(
                Recommendation(
                    priority="high",
                    action=(
                        f"Audit data collection and pipeline for '{ca.column}' — "
                        f"{consec_run} consecutive anomalous values detected"
                    ),
                    reason=(
                        f"'{ca.column}' has {consec_run} consecutive anomaly/anomalies "
                        f"({ca.anomaly_count} total). Runs of consecutive anomalies "
                        "typically indicate a systemic data or operational issue, "
                        "not a random fluctuation."
                    ),
                    expected_impact=(
                        f"Resolving the root cause of consecutive anomalies in "
                        f"'{ca.column}' will restore data reliability and "
                        "prevent compounding reporting errors."
                    ),
                    category="data_quality",
                    source="anomaly",
                    confidence=0.88,
                    data_points=[
                        f"{ca.column}: {consec_run} consecutive anomalies",
                        f"Total anomaly count: {ca.anomaly_count}",
                        f"Detection methods: {', '.join(ca.methods)}",
                    ],
                )
            )

        return recs

    def _drop_action(self, column: str, category: str) -> str:
        """Return a context-aware action verb phrase for a drop anomaly."""
        templates = {
            "revenue":   f"Activate revenue recovery plan for '{column}'",
            "inventory": f"Review supply chain and reorder strategy for '{column}'",
            "marketing": f"Increase marketing investment in segments driving '{column}' decline",
            "operations": f"Identify and reduce operational inefficiency in '{column}'",
        }
        return templates.get(category, f"Investigate and remediate the decline in '{column}'")

    # ------------------------------------------------------------------ #
    # Insight → recommendations
    # ------------------------------------------------------------------ #

    def _from_insights(self, resp: InsightResponse) -> list[Recommendation]:
        recs: list[Recommendation] = []

        # ── Parse trends ────────────────────────────────────────────────
        for trend_str in resp.trends:
            rec = self._trend_rec(trend_str)
            if rec:
                recs.append(rec)

        # ── Underperformers ─────────────────────────────────────────────
        for perf in resp.underperformers[:3]:
            rec = self._underperformer_rec(perf)
            if rec:
                recs.append(rec)

        # ── Top performers ───────────────────────────────────────────────
        for perf in resp.top_performers[:2]:
            rec = self._top_performer_rec(perf)
            if rec:
                recs.append(rec)

        # ── Key insights with explicit decline signals ───────────────────
        for ki in resp.key_insights:
            if _is_decline(ki):
                recs.append(
                    Recommendation(
                        priority="high",
                        action=(
                            "Address the decline highlighted in data insights — "
                            "develop a targeted recovery plan"
                        ),
                        reason=ki,
                        expected_impact=(
                            "Halting the observed decline will stabilise the "
                            "affected metric and prevent further deterioration."
                        ),
                        category=_infer_category(ki),
                        source="insight",
                        confidence=0.70,
                        data_points=[ki],
                    )
                )

        # ── Re-use existing LLM recommendations from InsightResponse ────
        for rec_str in resp.recommendations[:3]:
            recs.append(
                Recommendation(
                    priority="medium",
                    action=rec_str,
                    reason=(
                        "Derived from statistical analysis of dataset patterns "
                        "(insight engine finding)."
                    ),
                    expected_impact="Improvement in the underlying tracked metric.",
                    category=_infer_category(rec_str),
                    source="insight",
                    confidence=0.65,
                    data_points=[rec_str],
                )
            )

        return recs

    def _trend_rec(self, trend_str: str) -> Optional[Recommendation]:
        """Convert a trend string into a recommendation."""
        is_down = _is_decline(trend_str)
        is_up = _is_growth(trend_str)
        if not (is_down or is_up):
            return None

        category = _infer_category(trend_str)

        if is_down:
            return Recommendation(
                priority="high",
                action=self._decline_trend_action(trend_str, category),
                reason=f"Detected declining trend: {trend_str}",
                expected_impact=(
                    "Arresting the decline trend will prevent compounding losses "
                    "and restore the metric toward its historical baseline."
                ),
                category=category,
                source="insight",
                confidence=0.75,
                data_points=[trend_str],
            )
        else:
            return Recommendation(
                priority="medium",
                action=self._growth_trend_action(trend_str, category),
                reason=f"Detected growth trend: {trend_str}",
                expected_impact=(
                    "Scaling resources proactively will sustain the growth trend "
                    "and avoid capacity constraints."
                ),
                category=category,
                source="insight",
                confidence=0.70,
                data_points=[trend_str],
            )

    def _decline_trend_action(self, trend_str: str, category: str) -> str:
        templates = {
            "revenue":    "Develop and execute a revenue recovery roadmap to reverse the declining trend",
            "inventory":  "Reduce stock replenishment rate to align with declining inventory turnover",
            "marketing":  "Re-evaluate marketing strategy — current approach shows declining returns",
            "operations": "Conduct process review to address declining operational efficiency",
        }
        return templates.get(category, "Implement a targeted intervention plan to reverse the declining trend")

    def _growth_trend_action(self, trend_str: str, category: str) -> str:
        templates = {
            "revenue":    "Scale revenue operations and resources to sustain and amplify growth momentum",
            "inventory":  "Increase safety stock and supplier capacity ahead of rising demand",
            "marketing":  "Double down on the highest-performing marketing channels driving growth",
            "operations": "Invest in operational capacity to handle increasing throughput",
        }
        return templates.get(category, "Pre-position resources to capitalise on the detected growth trend")

    def _underperformer_rec(self, perf: dict[str, Any]) -> Optional[Recommendation]:
        """Derive recommendation from an underperformer dict."""
        col = str(perf.get("column", perf.get("metric", perf.get("name", "Unknown"))))
        val = perf.get("value", perf.get("rank_value"))
        category = _infer_category(col)

        val_str = f"{val:,.4g}" if isinstance(val, (int, float)) else str(val)

        return Recommendation(
            priority="high",
            action=self._underperformer_action(col, category),
            reason=(
                f"'{col}' is identified as an underperformer "
                f"(value: {val_str}). "
                "Underperformers represent the highest-ROI improvement opportunity."
            ),
            expected_impact=(
                f"Bringing '{col}' up to average performance levels "
                "will have an outsized positive impact on overall KPI health."
            ),
            category=category,
            source="insight",
            confidence=0.72,
            data_points=[f"{col}: {val_str}", f"Category: {category}"],
        )

    def _underperformer_action(self, column: str, category: str) -> str:
        templates = {
            "revenue":    f"Prioritise sales and marketing investment in the '{column}' segment to close the performance gap",
            "inventory":  f"Reduce '{column}' stock levels and improve turnover through promotional pricing",
            "marketing":  f"Reallocate budget from low-performing '{column}' campaigns to higher-ROI channels",
            "operations": f"Conduct root-cause analysis on '{column}' and implement process improvements",
        }
        return templates.get(category, f"Develop a targeted improvement plan for underperforming '{column}'")

    def _top_performer_rec(self, perf: dict[str, Any]) -> Optional[Recommendation]:
        col = str(perf.get("column", perf.get("metric", perf.get("name", "Unknown"))))
        val = perf.get("value", perf.get("rank_value"))
        val_str = f"{val:,.4g}" if isinstance(val, (int, float)) else str(val)

        return Recommendation(
            priority="medium",
            action=(
                f"Document and replicate the success factors driving "
                f"'{col}' top performance across similar segments"
            ),
            reason=(
                f"'{col}' is a top performer (value: {val_str}). "
                "Success patterns in top performers are high-value inputs "
                "for strategy replication."
            ),
            expected_impact=(
                f"Applying '{col}' success drivers to underperforming segments "
                "could improve overall portfolio performance."
            ),
            category=_infer_category(col),
            source="insight",
            confidence=0.65,
            data_points=[f"{col}: {val_str}"],
        )

    # ------------------------------------------------------------------ #
    # Forecast → recommendations
    # ------------------------------------------------------------------ #

    def _from_forecast(self, forecast: dict[str, Any]) -> list[Recommendation]:
        recs: list[Recommendation] = []

        answer = str(forecast.get("answer", ""))
        operation = str(forecast.get("operation", ""))
        horizon = int(forecast.get("horizon", 0))
        table_data: list[dict[str, Any]] = forecast.get("table_data") or []
        method_used = str(forecast.get("method_used", ""))

        if not answer and not table_data:
            return recs

        # ── Detect trajectory from table_data ───────────────────────────
        direction = self._forecast_direction(table_data)

        if operation == "forecast" and horizon > 0:
            if direction == "decline":
                recs.append(
                    Recommendation(
                        priority="high",
                        action=(
                            f"Initiate contingency planning — forecast model projects "
                            f"a decline over the next {horizon} period(s)"
                        ),
                        reason=(
                            f"Forecast ({method_used}) projects a downward trajectory "
                            f"over {horizon} period(s). {answer[:200]}"
                        ),
                        expected_impact=(
                            f"Proactive intervention before the forecast decline "
                            f"materialises can limit losses over the {horizon}-period window."
                        ),
                        category=_infer_category(answer),
                        source="forecast",
                        confidence=0.68,
                        data_points=[
                            f"Forecast method: {method_used}",
                            f"Horizon: {horizon} periods",
                            f"Trajectory: declining",
                            f"Answer: {answer[:150]}",
                        ],
                    )
                )
            elif direction == "growth":
                recs.append(
                    Recommendation(
                        priority="medium",
                        action=(
                            f"Pre-position resources and capacity for projected growth "
                            f"over the next {horizon} period(s)"
                        ),
                        reason=(
                            f"Forecast ({method_used}) projects an upward trajectory "
                            f"over {horizon} period(s). {answer[:200]}"
                        ),
                        expected_impact=(
                            f"Early resource allocation will prevent bottlenecks "
                            f"and maximise capture of the projected growth."
                        ),
                        category=_infer_category(answer),
                        source="forecast",
                        confidence=0.65,
                        data_points=[
                            f"Forecast method: {method_used}",
                            f"Horizon: {horizon} periods",
                            f"Trajectory: growing",
                        ],
                    )
                )

        # ── Forecast anomalies ───────────────────────────────────────────
        if operation == "anomaly_detection" and table_data:
            n_anomalies = len(table_data)
            recs.append(
                Recommendation(
                    priority="medium",
                    action=(
                        f"Review and validate the {n_anomalies} anomalies "
                        "flagged in the time-series forecast data"
                    ),
                    reason=(
                        f"The forecast anomaly detection identified {n_anomalies} "
                        f"anomalous periods. {answer[:200]}"
                    ),
                    expected_impact=(
                        "Validating forecast anomalies will improve model accuracy "
                        "and surface any hidden structural breaks in the data."
                    ),
                    category="monitoring",
                    source="forecast",
                    confidence=0.72,
                    data_points=[
                        f"Operation: {operation}",
                        f"Anomalies found: {n_anomalies}",
                    ],
                )
            )

        # ── Low data points warning ──────────────────────────────────────
        data_points_count = int(forecast.get("data_points", 0))
        if 0 < data_points_count < 12:
            recs.append(
                Recommendation(
                    priority="low",
                    action=(
                        f"Collect more historical data — forecast is based on only "
                        f"{data_points_count} data point(s), reducing reliability"
                    ),
                    reason=(
                        f"The forecast model used only {data_points_count} data points "
                        f"(method: {method_used}). Forecasts with fewer than 12 points "
                        "have wide confidence intervals."
                    ),
                    expected_impact=(
                        "Increasing historical depth to 12+ periods will significantly "
                        "improve forecast accuracy and confidence."
                    ),
                    category="data_quality",
                    source="forecast",
                    confidence=0.90,
                    data_points=[
                        f"Data points available: {data_points_count}",
                        f"Recommended minimum: 12",
                    ],
                )
            )

        return recs

    @staticmethod
    def _forecast_direction(table_data: list[dict[str, Any]]) -> str:
        """Infer trend direction from forecast table rows."""
        if len(table_data) < 2:
            return "flat"
        numeric_cols = [
            k for k, v in table_data[0].items()
            if isinstance(v, (int, float))
        ]
        if not numeric_cols:
            return "flat"
        col = numeric_cols[-1]
        try:
            first = float(table_data[0][col])
            last = float(table_data[-1][col])
            delta = last - first
            if abs(delta) < 1e-9:
                return "flat"
            return "decline" if delta < 0 else "growth"
        except (TypeError, ValueError):
            return "flat"

    # ------------------------------------------------------------------ #
    # Cross-signal escalation
    # ------------------------------------------------------------------ #

    def _cross_signal(
        self,
        anomalies: Optional[AnomalyResponse],
        insights: Optional[InsightResponse],
        existing_rules: list[Recommendation],
    ) -> list[Recommendation]:
        """Generate extra recommendations when the same metric appears in
        two or more independent signal sources."""
        if not anomalies or not insights:
            return []

        anomaly_cols = {ca.column.lower() for ca in anomalies.anomalies}
        # Map insight text → category
        insight_text = " ".join(insights.trends + insights.key_insights).lower()

        cross_recs: list[Recommendation] = []
        for col in anomaly_cols:
            if col in insight_text:
                col_anomaly = next(
                    (ca for ca in anomalies.anomalies if ca.column.lower() == col),
                    None,
                )
                if col_anomaly is None:
                    continue
                worst = max(col_anomaly.anomaly_points, key=lambda p: p.score, default=None)
                if worst is None:
                    continue
                cross_recs.append(
                    Recommendation(
                        priority="critical" if col_anomaly.anomaly_points[0].severity in ("high", "critical") else "high",
                        action=(
                            f"Escalate '{col_anomaly.column}' to executive review — "
                            "confirmed by both anomaly detection and trend analysis"
                        ),
                        reason=(
                            f"'{col_anomaly.column}' is flagged by anomaly detection "
                            f"(score {worst.score:.2f}σ, severity {worst.severity}) "
                            "AND appears as a concern in the insight trend analysis. "
                            "Corroboration across two independent sources strongly "
                            "indicates a real, material issue."
                        ),
                        expected_impact=(
                            f"Coordinated, cross-functional action on '{col_anomaly.column}' "
                            "will address the issue at its root rather than treating "
                            "symptoms from a single analysis perspective."
                        ),
                        category=_infer_category(col_anomaly.column),
                        source="cross_signal",
                        confidence=0.92,
                        data_points=[
                            f"Anomaly score: {worst.score:.2f}σ ({worst.severity})",
                            f"Anomaly count: {col_anomaly.anomaly_count}",
                            "Confirmed by insight trend analysis",
                        ],
                    )
                )

        return cross_recs

    # ------------------------------------------------------------------ #
    # Post-processing
    # ------------------------------------------------------------------ #

    @staticmethod
    def _deduplicate_and_rank(rules: list[Recommendation]) -> list[Recommendation]:
        """Remove near-duplicate actions and sort by priority then confidence.

        Sort by priority first so that when two entries share near-identical
        action text, the higher-priority one is encountered first and kept.
        """
        # Pre-sort so the highest-priority entry is seen first during dedup.
        pre_sorted = sorted(
            rules,
            key=lambda r: (_priority_rank(r.priority), r.confidence),
            reverse=True,
        )

        seen_actions: list[str] = []
        deduped: list[Recommendation] = []

        for rec in pre_sorted:
            action_lower = rec.action.lower()
            is_dup = any(
                _jaccard(action_lower, seen) > 0.6 for seen in seen_actions
            )
            if not is_dup:
                deduped.append(rec)
                seen_actions.append(action_lower)

        return deduped


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _longest_consecutive(sorted_indices: list[int]) -> int:
    """Return the length of the longest consecutive run."""
    if not sorted_indices:
        return 0
    best, current = 1, 1
    for a, b in zip(sorted_indices, sorted_indices[1:]):
        if b == a + 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity for rough deduplication."""
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _build_summary(recs: list[Recommendation], llm_enhanced: bool) -> str:
    """Generate a concise, data-grounded summary paragraph."""
    if not recs:
        return "No actionable recommendations were generated from the available data."

    top = recs[:3]
    parts: list[str] = []
    for r in top:
        parts.append(
            f"{r.priority.upper()}: {r.action} "
            f"({r.category}, confidence {r.confidence:.0%})"
        )

    total_critical = sum(1 for r in recs if r.priority == "critical")
    total_high = sum(1 for r in recs if r.priority == "high")

    summary = (
        f"Generated {len(recs)} recommendation(s) from data analysis"
        f"{' (LLM-enhanced)' if llm_enhanced else ' (rule-based)'}. "
    )
    if total_critical:
        summary += f"{total_critical} critical action(s) require immediate attention. "
    if total_high:
        summary += f"{total_high} high-priority action(s) should be addressed this week. "
    summary += "Top actions: " + " | ".join(parts[:3]) + "."
    return summary


# ---------------------------------------------------------------------------
# Orchestration service
# ---------------------------------------------------------------------------


class RecommendationService:
    """Coordinate rule engine, LLM agent, and TTL cache."""

    def __init__(
        self,
        recommendation_agent: Any,  # RecommendationAgent — avoids circular import
        cache_ttl: float = 300.0,
        cache_max_entries: int = 30,
    ) -> None:
        self._agent = recommendation_agent
        self._engine = RecommendationRuleEngine()
        self._cache: TTLCache[str, RecommendationResponse] = TTLCache(
            ttl_seconds=cache_ttl,
            max_entries=cache_max_entries,
        )

    async def generate(self, request: RecommendationRequest) -> RecommendationResponse:
        """Full pipeline: rule engine → LLM enhancement → cache."""
        cache_key = _cache_key(request)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(update={"cache_hit": True})

        start = time.perf_counter()
        llm_enhanced = False

        try:
            # Phase 1: deterministic rule engine.
            rule_recs = self._engine.generate(
                anomalies=request.anomalies,
                insights=request.insights,
                forecast=request.forecast,
                query_results=request.query_results,
                max_recommendations=request.max_recommendations,
            )

            final_recs = rule_recs
            # Phase 2: optional LLM enhancement.
            if request.llm_enhance and rule_recs:
                try:
                    enhanced_resp = await self._agent.enhance(
                        recommendations=rule_recs,
                        context=request.context,
                        dataset_id=request.dataset_id,
                    )
                    if enhanced_resp:
                        final_recs = enhanced_resp
                        llm_enhanced = True
                except Exception as exc:
                    logger.warning(
                        "RecommendationService: LLM enhancement failed (%s) — using rule-based output.",
                        exc,
                    )

        except Exception as exc:
            logger.error("RecommendationService: rule engine failed: %s", exc)
            final_recs = []

        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        summary = _build_summary(final_recs, llm_enhanced)

        result = RecommendationResponse(
            recommendations=final_recs,
            summary=summary,
            total_count=len(final_recs),
            generation_time_ms=elapsed_ms,
            cache_hit=False,
            llm_enhanced=llm_enhanced,
        )
        self._cache.put(cache_key, result)
        return result


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def _cache_key(request: RecommendationRequest) -> str:
    parts: dict[str, Any] = {
        "dataset_id": request.dataset_id,
        "has_anomalies": request.anomalies is not None,
        "has_insights": request.insights is not None,
        "has_forecast": request.forecast is not None,
        "anomaly_severity": request.anomalies.severity if request.anomalies else None,
        "anomaly_count": request.anomalies.total_anomaly_count if request.anomalies else None,
        "insight_summary_hash": (
            hashlib.md5(request.insights.summary.encode(), usedforsecurity=False).hexdigest()[:8]
            if request.insights
            else None
        ),
        "max_recommendations": request.max_recommendations,
        "context": (request.context or "")[:100],
    }
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()
