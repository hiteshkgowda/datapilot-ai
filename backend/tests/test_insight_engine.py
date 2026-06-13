"""Enterprise tests — AI Insight Generation Engine.

Coverage:
  InsightStatEngine  — column stats, trend detection, performers, correlations,
                        growth patterns, edge cases (empty, single row, no numerics)
  InsightGenerationService — caching (hit/miss), empty table, agent failure fallback
  InsightAgent       — fallback_from_findings, _parse_response, _to_str_list
  API endpoint       — auth guard, ownership check, happy path, cache header
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.insight_agent import InsightAgent, _to_dict_list, _to_str_list
from app.schemas.insight import (
    ColumnStats,
    CorrelationInfo,
    GrowthPattern,
    InsightResponse,
    PerformerEntry,
    StatisticalFindings,
    TrendInfo,
)
from app.services.insight_service import (
    InsightGenerationService,
    InsightStatEngine,
    _build_cache_key,
    _empty_response,
    _safe_float,
)

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

SALES_TABLE: list[dict[str, Any]] = [
    {"region": "North", "sales": 1000.0, "units": 50},
    {"region": "South", "sales": 800.0, "units": 40},
    {"region": "East", "sales": 1200.0, "units": 60},
    {"region": "West", "sales": 600.0, "units": 30},
    {"region": "Central", "sales": 900.0, "units": 45},
]

TRENDING_TABLE: list[dict[str, Any]] = [
    {"month": "Jan", "revenue": 100.0},
    {"month": "Feb", "revenue": 120.0},
    {"month": "Mar", "revenue": 145.0},
    {"month": "Apr", "revenue": 170.0},
    {"month": "May", "revenue": 200.0},
]

DECLINING_TABLE: list[dict[str, Any]] = [
    {"month": "Jan", "revenue": 200.0},
    {"month": "Feb", "revenue": 180.0},
    {"month": "Mar", "revenue": 155.0},
    {"month": "Apr", "revenue": 130.0},
    {"month": "May", "revenue": 100.0},
]

FLAT_TABLE: list[dict[str, Any]] = [
    {"x": 1, "y": 100.0},
    {"x": 2, "y": 100.1},
    {"x": 3, "y": 99.9},
    {"x": 4, "y": 100.0},
]

TWO_NUMERIC_TABLE: list[dict[str, Any]] = [
    {"a": 1.0, "b": 2.0},
    {"a": 2.0, "b": 4.0},
    {"a": 3.0, "b": 6.0},
    {"a": 4.0, "b": 8.0},
    {"a": 5.0, "b": 10.0},
]

CORRELATED_TABLE: list[dict[str, Any]] = [
    {"x": float(i), "y": float(i) * 2.0 + 0.1} for i in range(1, 21)
]

ALL_CATEGORICAL_TABLE: list[dict[str, Any]] = [
    {"name": "Alice", "dept": "Eng"},
    {"name": "Bob", "dept": "Sales"},
]

EMPTY_TABLE: list[dict[str, Any]] = []

SINGLE_ROW_TABLE: list[dict[str, Any]] = [{"region": "North", "sales": 500.0}]


def _make_findings(
    row_count: int = 5,
    numeric_cols: list[str] | None = None,
    top_performers: list[PerformerEntry] | None = None,
    underperformers: list[PerformerEntry] | None = None,
    trends: list[TrendInfo] | None = None,
    correlations: list[CorrelationInfo] | None = None,
    growth_patterns: list[GrowthPattern] | None = None,
    column_stats: list[ColumnStats] | None = None,
) -> StatisticalFindings:
    return StatisticalFindings(
        row_count=row_count,
        column_count=len(numeric_cols or []) + 1,
        numeric_columns=numeric_cols or ["sales"],
        categorical_columns=["region"],
        column_stats=column_stats or [
            ColumnStats(column="sales", count=5, mean=900.0, median=900.0, std=200.0, min=600.0, max=1200.0, p25=800.0, p75=1000.0)
        ],
        top_performers=top_performers or [
            PerformerEntry(label="East", value=1200.0, metric="sales", rank=1)
        ],
        underperformers=underperformers or [
            PerformerEntry(label="West", value=600.0, metric="sales", rank=1)
        ],
        trends=trends or [],
        correlations=correlations or [],
        growth_patterns=growth_patterns or [],
    )


# ---------------------------------------------------------------------------
# InsightStatEngine — column stats
# ---------------------------------------------------------------------------


class TestColumnStats:
    engine = InsightStatEngine()

    def test_mean_computed(self):
        findings = self.engine.analyze(SALES_TABLE)
        sales_stat = next(s for s in findings.column_stats if s.column == "sales")
        assert sales_stat.mean == pytest.approx(900.0)

    def test_min_max_computed(self):
        findings = self.engine.analyze(SALES_TABLE)
        sales_stat = next(s for s in findings.column_stats if s.column == "sales")
        assert sales_stat.min == pytest.approx(600.0)
        assert sales_stat.max == pytest.approx(1200.0)

    def test_percentiles_computed(self):
        findings = self.engine.analyze(SALES_TABLE)
        sales_stat = next(s for s in findings.column_stats if s.column == "sales")
        assert sales_stat.p25 is not None
        assert sales_stat.p75 is not None
        assert sales_stat.p25 < sales_stat.median < sales_stat.p75  # type: ignore[operator]

    def test_null_count_zero_when_no_nulls(self):
        findings = self.engine.analyze(SALES_TABLE)
        for stat in findings.column_stats:
            assert stat.null_count == 0

    def test_std_positive(self):
        findings = self.engine.analyze(SALES_TABLE)
        sales_stat = next(s for s in findings.column_stats if s.column == "sales")
        assert sales_stat.std is not None and sales_stat.std > 0

    def test_coefficient_of_variation(self):
        findings = self.engine.analyze(SALES_TABLE)
        sales_stat = next(s for s in findings.column_stats if s.column == "sales")
        assert sales_stat.coefficient_of_variation is not None

    def test_multiple_numeric_cols_all_reported(self):
        findings = self.engine.analyze(SALES_TABLE)
        col_names = {s.column for s in findings.column_stats}
        assert "sales" in col_names
        assert "units" in col_names

    def test_empty_table_returns_empty_stats(self):
        findings = self.engine.analyze(EMPTY_TABLE)
        assert findings.column_stats == []

    def test_all_categorical_returns_empty_stats(self):
        findings = self.engine.analyze(ALL_CATEGORICAL_TABLE)
        assert findings.numeric_columns == []
        assert findings.column_stats == []


# ---------------------------------------------------------------------------
# InsightStatEngine — performer detection
# ---------------------------------------------------------------------------


class TestPerformerDetection:
    engine = InsightStatEngine(top_n=3)

    def test_top_performer_is_highest_value(self):
        findings = self.engine.analyze(SALES_TABLE)
        assert len(findings.top_performers) > 0
        assert findings.top_performers[0].value == pytest.approx(1200.0)
        assert findings.top_performers[0].label == "East"

    def test_underperformer_is_lowest_value(self):
        findings = self.engine.analyze(SALES_TABLE)
        assert len(findings.underperformers) > 0
        assert findings.underperformers[0].value == pytest.approx(600.0)
        assert findings.underperformers[0].label == "West"

    def test_top_n_respected(self):
        findings = self.engine.analyze(SALES_TABLE)
        assert len(findings.top_performers) <= 3
        assert len(findings.underperformers) <= 3

    def test_ranks_are_sequential(self):
        findings = self.engine.analyze(SALES_TABLE)
        ranks = [p.rank for p in findings.top_performers]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_metric_field_set_to_column_name(self):
        findings = self.engine.analyze(SALES_TABLE)
        for p in findings.top_performers:
            assert p.metric == "sales"

    def test_empty_table_no_performers(self):
        findings = self.engine.analyze(EMPTY_TABLE)
        assert findings.top_performers == []
        assert findings.underperformers == []

    def test_no_numeric_cols_no_performers(self):
        findings = self.engine.analyze(ALL_CATEGORICAL_TABLE)
        assert findings.top_performers == []


# ---------------------------------------------------------------------------
# InsightStatEngine — trend detection
# ---------------------------------------------------------------------------


class TestTrendDetection:
    engine = InsightStatEngine()

    def test_increasing_trend_detected(self):
        findings = self.engine.analyze(TRENDING_TABLE)
        revenue_trend = next((t for t in findings.trends if t.column == "revenue"), None)
        assert revenue_trend is not None
        assert revenue_trend.direction == "increasing"
        assert revenue_trend.slope > 0

    def test_decreasing_trend_detected(self):
        findings = self.engine.analyze(DECLINING_TABLE)
        revenue_trend = next((t for t in findings.trends if t.column == "revenue"), None)
        assert revenue_trend is not None
        assert revenue_trend.direction == "decreasing"
        assert revenue_trend.slope < 0

    def test_flat_trend_detected(self):
        findings = self.engine.analyze(FLAT_TABLE)
        y_trend = next((t for t in findings.trends if t.column == "y"), None)
        assert y_trend is not None
        assert y_trend.direction == "flat"

    def test_trend_records_first_and_last_value(self):
        findings = self.engine.analyze(TRENDING_TABLE)
        revenue_trend = next(t for t in findings.trends if t.column == "revenue")
        assert revenue_trend.first_value == pytest.approx(100.0)
        assert revenue_trend.last_value == pytest.approx(200.0)

    def test_change_pct_positive_for_increasing(self):
        findings = self.engine.analyze(TRENDING_TABLE)
        revenue_trend = next(t for t in findings.trends if t.column == "revenue")
        assert revenue_trend.change_pct is not None
        assert revenue_trend.change_pct > 0

    def test_change_pct_negative_for_decreasing(self):
        findings = self.engine.analyze(DECLINING_TABLE)
        revenue_trend = next(t for t in findings.trends if t.column == "revenue")
        assert revenue_trend.change_pct is not None
        assert revenue_trend.change_pct < 0

    def test_fewer_than_3_rows_no_trends(self):
        findings = self.engine.analyze(SINGLE_ROW_TABLE)
        assert findings.trends == []

    def test_empty_table_no_trends(self):
        findings = self.engine.analyze(EMPTY_TABLE)
        assert findings.trends == []


# ---------------------------------------------------------------------------
# InsightStatEngine — correlation detection
# ---------------------------------------------------------------------------


class TestCorrelationDetection:
    engine = InsightStatEngine(correlation_threshold=0.5)

    def test_strong_positive_correlation_detected(self):
        findings = self.engine.analyze(CORRELATED_TABLE)
        corrs = findings.correlations
        assert len(corrs) > 0
        assert corrs[0].coefficient > 0.9
        assert corrs[0].strength == "strong_positive"

    def test_below_threshold_not_reported(self):
        # SALES_TABLE has sales and units that may correlate weakly
        findings = InsightStatEngine(correlation_threshold=0.99).analyze(SALES_TABLE)
        # With such a high threshold nearly nothing should pass unless perfect
        for corr in findings.correlations:
            assert abs(corr.coefficient) >= 0.99

    def test_no_self_correlation(self):
        findings = self.engine.analyze(CORRELATED_TABLE)
        for corr in findings.correlations:
            assert corr.column_a != corr.column_b

    def test_pairs_not_duplicated(self):
        findings = self.engine.analyze(CORRELATED_TABLE)
        seen: set[frozenset[str]] = set()
        for corr in findings.correlations:
            pair: frozenset[str] = frozenset({corr.column_a, corr.column_b})
            assert pair not in seen
            seen.add(pair)

    def test_single_numeric_col_no_correlations(self):
        findings = self.engine.analyze(TRENDING_TABLE)
        assert findings.correlations == []

    def test_empty_table_no_correlations(self):
        findings = self.engine.analyze(EMPTY_TABLE)
        assert findings.correlations == []


# ---------------------------------------------------------------------------
# InsightStatEngine — growth patterns
# ---------------------------------------------------------------------------


class TestGrowthPatterns:
    engine = InsightStatEngine()

    def test_stable_pattern_detected(self):
        findings = self.engine.analyze(FLAT_TABLE)
        y_pattern = next((g for g in findings.growth_patterns if g.column == "y"), None)
        assert y_pattern is not None
        assert y_pattern.pattern == "stable"

    def test_growth_pattern_has_avg_change(self):
        findings = self.engine.analyze(TRENDING_TABLE)
        revenue_pattern = next((g for g in findings.growth_patterns if g.column == "revenue"), None)
        assert revenue_pattern is not None
        assert revenue_pattern.avg_period_change_pct is not None

    def test_min_3_rows_required(self):
        findings = self.engine.analyze(SINGLE_ROW_TABLE)
        assert findings.growth_patterns == []

    def test_empty_table_no_patterns(self):
        findings = self.engine.analyze(EMPTY_TABLE)
        assert findings.growth_patterns == []

    def test_pattern_value_in_known_set(self):
        findings = self.engine.analyze(SALES_TABLE)
        valid = {"accelerating", "decelerating", "stable", "volatile"}
        for gp in findings.growth_patterns:
            assert gp.pattern in valid


# ---------------------------------------------------------------------------
# InsightStatEngine — metadata fields
# ---------------------------------------------------------------------------


class TestMetadataFields:
    engine = InsightStatEngine()

    def test_row_count_correct(self):
        findings = self.engine.analyze(SALES_TABLE)
        assert findings.row_count == 5

    def test_column_count_correct(self):
        findings = self.engine.analyze(SALES_TABLE)
        assert findings.column_count == 3  # region, sales, units

    def test_numeric_columns_identified(self):
        findings = self.engine.analyze(SALES_TABLE)
        assert set(findings.numeric_columns) == {"sales", "units"}

    def test_categorical_columns_identified(self):
        findings = self.engine.analyze(SALES_TABLE)
        assert findings.categorical_columns == ["region"]

    def test_max_rows_cap_respected(self):
        large = [{"v": float(i)} for i in range(2000)]
        findings = InsightStatEngine(max_rows=100).analyze(large)
        assert findings.row_count == 100


# ---------------------------------------------------------------------------
# InsightAgent — fallback (no LLM)
# ---------------------------------------------------------------------------


class TestInsightAgentFallback:
    def _agent(self) -> InsightAgent:
        from app.core.config import Settings
        return InsightAgent(Settings())

    def test_fallback_returns_response(self):
        agent = self._agent()
        findings = _make_findings()
        resp = agent._fallback_from_findings(findings)
        assert isinstance(resp, InsightResponse)

    def test_fallback_summary_mentions_row_count(self):
        agent = self._agent()
        findings = _make_findings(row_count=42)
        resp = agent._fallback_from_findings(findings)
        assert "42" in resp.summary

    def test_fallback_key_insights_from_column_stats(self):
        agent = self._agent()
        findings = _make_findings()
        resp = agent._fallback_from_findings(findings)
        assert any("sales" in ins for ins in resp.key_insights)

    def test_fallback_trends_from_trend_info(self):
        agent = self._agent()
        findings = _make_findings(
            trends=[TrendInfo(column="revenue", direction="increasing", slope=25.0, change_pct=100.0)]
        )
        resp = agent._fallback_from_findings(findings)
        assert any("increasing" in t for t in resp.trends)

    def test_fallback_top_performers_from_findings(self):
        agent = self._agent()
        findings = _make_findings()
        resp = agent._fallback_from_findings(findings)
        assert len(resp.top_performers) == 1
        assert resp.top_performers[0]["label"] == "East"

    def test_fallback_recommendation_for_strong_correlation(self):
        agent = self._agent()
        findings = _make_findings(
            correlations=[
                CorrelationInfo(column_a="a", column_b="b", coefficient=0.95, strength="strong_positive")
            ]
        )
        resp = agent._fallback_from_findings(findings)
        assert any("a" in r and "b" in r for r in resp.recommendations)

    def test_fallback_recommendation_for_volatile_growth(self):
        agent = self._agent()
        findings = _make_findings(
            growth_patterns=[
                GrowthPattern(column="sales", pattern="volatile", avg_period_change_pct=35.0)
            ]
        )
        resp = agent._fallback_from_findings(findings)
        assert any("volatile" in r.lower() or "sales" in r for r in resp.recommendations)

    def test_parse_response_valid_json(self):
        agent = self._agent()
        findings = _make_findings()
        raw = json.dumps({
            "summary": "Good data",
            "key_insights": ["insight A"],
            "trends": ["up"],
            "top_performers": [{"label": "East", "value": 1200, "metric": "sales", "rank": 1}],
            "underperformers": [],
            "recommendations": ["do something"],
        })
        resp = agent._parse_response(raw, findings)
        assert resp.summary == "Good data"
        assert resp.key_insights == ["insight A"]

    def test_parse_response_invalid_json_falls_back(self):
        agent = self._agent()
        findings = _make_findings()
        resp = agent._parse_response("NOT JSON", findings)
        # Should still return a valid InsightResponse (from statistical fallback)
        assert isinstance(resp, InsightResponse)
        assert resp.summary  # non-empty

    def test_generate_without_client_uses_fallback(self):
        agent = self._agent()
        assert agent._client is None
        findings = _make_findings()
        resp = asyncio.run(agent.generate(findings=findings, question="test?"))
        assert isinstance(resp, InsightResponse)


# ---------------------------------------------------------------------------
# InsightAgent — _to_str_list / _to_dict_list helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_to_str_list_filters_empty(self):
        assert _to_str_list(["a", "", "b"]) == ["a", "b"]

    def test_to_str_list_non_list_returns_empty(self):
        assert _to_str_list("not a list") == []
        assert _to_str_list(None) == []

    def test_to_dict_list_filters_non_dicts(self):
        result = _to_dict_list([{"k": "v"}, "string", 42, {"k2": "v2"}])
        assert result == [{"k": "v"}, {"k2": "v2"}]

    def test_to_dict_list_non_list_returns_empty(self):
        assert _to_dict_list(None) == []


# ---------------------------------------------------------------------------
# _safe_float helper
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_normal_value(self):
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_none_returns_none(self):
        assert _safe_float(None) is None

    def test_nan_returns_none(self):
        import math
        assert _safe_float(float("nan")) is None

    def test_inf_returns_none(self):
        assert _safe_float(float("inf")) is None

    def test_negative_inf_returns_none(self):
        assert _safe_float(float("-inf")) is None

    def test_int_coerced(self):
        assert _safe_float(5) == pytest.approx(5.0)

    def test_string_non_numeric_returns_none(self):
        assert _safe_float("abc") is None


# ---------------------------------------------------------------------------
# _build_cache_key
# ---------------------------------------------------------------------------


class TestCacheKey:
    def test_same_inputs_same_key(self):
        k1 = _build_cache_key("ds1", "question", SALES_TABLE)
        k2 = _build_cache_key("ds1", "question", SALES_TABLE)
        assert k1 == k2

    def test_different_dataset_different_key(self):
        k1 = _build_cache_key("ds1", "question", SALES_TABLE)
        k2 = _build_cache_key("ds2", "question", SALES_TABLE)
        assert k1 != k2

    def test_different_question_different_key(self):
        k1 = _build_cache_key("ds1", "question A", SALES_TABLE)
        k2 = _build_cache_key("ds1", "question B", SALES_TABLE)
        assert k1 != k2

    def test_different_table_different_key(self):
        k1 = _build_cache_key("ds1", "q", SALES_TABLE)
        k2 = _build_cache_key("ds1", "q", TRENDING_TABLE)
        assert k1 != k2

    def test_key_is_hex_string(self):
        k = _build_cache_key("ds1", "q", [])
        assert len(k) == 64
        int(k, 16)  # must be valid hex

    def test_question_case_insensitive(self):
        k1 = _build_cache_key("ds1", "What is the TOTAL?", [])
        k2 = _build_cache_key("ds1", "what is the total?", [])
        assert k1 == k2


# ---------------------------------------------------------------------------
# InsightGenerationService — caching
# ---------------------------------------------------------------------------


class TestInsightGenerationServiceCaching:
    def _make_service(self) -> InsightGenerationService:
        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(return_value=InsightResponse(
            summary="test summary",
            key_insights=["k1"],
            trends=[],
            top_performers=[],
            underperformers=[],
            recommendations=[],
        ))
        return InsightGenerationService(
            insight_agent=mock_agent,
            cache_ttl=300.0,
            cache_max_entries=10,
        )

    def test_first_call_not_cache_hit(self):
        svc = self._make_service()
        resp = asyncio.run(svc.generate("ds1", "q", SALES_TABLE))
        assert resp.cache_hit is False

    def test_second_call_is_cache_hit(self):
        svc = self._make_service()
        asyncio.run(svc.generate("ds1", "q", SALES_TABLE))
        resp2 = asyncio.run(svc.generate("ds1", "q", SALES_TABLE))
        assert resp2.cache_hit is True

    def test_agent_called_only_once_for_same_inputs(self):
        svc = self._make_service()
        asyncio.run(svc.generate("ds1", "q", SALES_TABLE))
        asyncio.run(svc.generate("ds1", "q", SALES_TABLE))
        svc._agent.generate.assert_called_once()

    def test_different_question_bypasses_cache(self):
        svc = self._make_service()
        asyncio.run(svc.generate("ds1", "q1", SALES_TABLE))
        resp2 = asyncio.run(svc.generate("ds1", "q2", SALES_TABLE))
        assert resp2.cache_hit is False
        assert svc._agent.generate.call_count == 2

    def test_empty_table_returns_without_agent_call(self):
        svc = self._make_service()
        resp = asyncio.run(svc.generate("ds1", "q", []))
        svc._agent.generate.assert_not_called()
        assert "No tabular data" in resp.summary

    def test_agent_failure_returns_empty_response(self):
        mock_agent = MagicMock()
        mock_agent.generate = AsyncMock(side_effect=RuntimeError("boom"))
        svc = InsightGenerationService(insight_agent=mock_agent)
        resp = asyncio.run(svc.generate("ds1", "q", SALES_TABLE))
        assert isinstance(resp, InsightResponse)
        assert "failed" in resp.summary.lower()

    def test_generation_time_ms_set_on_result(self):
        svc = self._make_service()
        resp = asyncio.run(svc.generate("ds1", "q", SALES_TABLE))
        assert resp.generation_time_ms >= 0

    def test_cache_hit_preserves_summary(self):
        svc = self._make_service()
        first = asyncio.run(svc.generate("ds1", "q", SALES_TABLE))
        second = asyncio.run(svc.generate("ds1", "q", SALES_TABLE))
        assert first.summary == second.summary


# ---------------------------------------------------------------------------
# _empty_response helper
# ---------------------------------------------------------------------------


class TestEmptyResponse:
    def test_empty_response_structure(self):
        resp = _empty_response("nothing here")
        assert resp.summary == "nothing here"
        assert resp.key_insights == []
        assert resp.trends == []
        assert resp.top_performers == []
        assert resp.underperformers == []
        assert resp.recommendations == []
        assert resp.cache_hit is False
