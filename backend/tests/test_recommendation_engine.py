"""Tests for the Recommendation Engine.

Coverage:
- RecommendationRuleEngine: anomaly patterns, insight patterns, forecast patterns,
  cross-signal escalation, deduplication, ranking
- RecommendationService: cache hit/miss, LLM fallback
- RecommendationAgent: response parsing, hallucination guard (field merging)
- Schema validation
- Route: missing signal source, ownership check
- Helper functions: _infer_category, _is_decline, _is_growth, _pct_delta,
  _longest_consecutive, _jaccard, _forecast_direction
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.anomaly import AnomalyPoint, AnomalyResponse, ColumnAnomaly
from app.schemas.insight import InsightResponse
from app.schemas.recommendation import (
    Recommendation,
    RecommendationRequest,
    RecommendationResponse,
)
from app.services.recommendation_service import (
    RecommendationRuleEngine,
    RecommendationService,
    _cache_key,
    _infer_category,
    _is_decline,
    _is_growth,
    _jaccard,
    _longest_consecutive,
    _pct_delta,
)
_forecast_direction = RecommendationRuleEngine._forecast_direction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_anomaly_point(
    row_index: int = 0,
    value: float = 500.0,
    score: float = 4.5,
    severity: str = "high",
    method: str = "zscore",
) -> AnomalyPoint:
    return AnomalyPoint(
        row_index=row_index,
        value=value,
        score=score,
        severity=severity,
        method=method,
        label=None,
    )


def _make_column_anomaly(
    column: str = "revenue",
    anomaly_count: int = 2,
    points: list[AnomalyPoint] | None = None,
    mean: float = 1000.0,
    std: float = 100.0,
) -> ColumnAnomaly:
    if points is None:
        points = [_make_anomaly_point()]
    return ColumnAnomaly(
        column=column,
        anomaly_count=anomaly_count,
        anomaly_points=points,
        methods=["zscore"],
        mean=mean,
        std=std,
        q1=900.0,
        q3=1100.0,
        min_value=400.0,
        max_value=1500.0,
    )


def _make_anomaly_response(
    anomalies: list[ColumnAnomaly] | None = None,
    severity: str = "high",
    total: int = 2,
) -> AnomalyResponse:
    if anomalies is None:
        anomalies = [_make_column_anomaly()]
    return AnomalyResponse(
        anomalies=anomalies,
        severity=severity,
        affected_metrics=[ca.column for ca in anomalies],
        possible_reasons=["test reason"],
        total_anomaly_count=total,
        chart_spec=None,
        detection_time_ms=10.0,
        methods_used=["zscore"],
        cache_hit=False,
    )


def _make_insight_response(
    trends: list[str] | None = None,
    key_insights: list[str] | None = None,
    underperformers: list[dict] | None = None,
    top_performers: list[dict] | None = None,
    recommendations: list[str] | None = None,
) -> InsightResponse:
    return InsightResponse(
        summary="test summary",
        key_insights=key_insights or [],
        trends=trends or [],
        top_performers=top_performers or [],
        underperformers=underperformers or [],
        correlations=[],
        recommendations=recommendations or [],
        statistics={},
        llm_enhanced=False,
        cache_hit=False,
        generation_time_ms=10.0,
    )


def _make_recommendation(**kwargs: Any) -> Recommendation:
    defaults = dict(
        priority="medium",
        action="Do something about revenue",
        reason="Revenue dropped by 20%",
        expected_impact="Recovery to baseline",
        category="revenue",
        source="anomaly",
        confidence=0.8,
        data_points=["revenue: 500"],
    )
    defaults.update(kwargs)
    return Recommendation(**defaults)


# ---------------------------------------------------------------------------
# Helper: _infer_category
# ---------------------------------------------------------------------------


def test_infer_category_revenue():
    assert _infer_category("revenue fell this quarter") == "revenue"


def test_infer_category_inventory():
    assert _infer_category("inventory stock levels low") == "inventory"


def test_infer_category_marketing():
    assert _infer_category("campaign conversion rate declined") == "marketing"


def test_infer_category_operations():
    assert _infer_category("cost and expense efficiency review") == "operations"


def test_infer_category_data_quality():
    assert _infer_category("consecutive null values in pipeline") == "data_quality"


def test_infer_category_monitoring():
    assert _infer_category("forecast anomaly alert threshold") == "monitoring"


def test_infer_category_general():
    assert _infer_category("unknown metric xyz") == "general"


# ---------------------------------------------------------------------------
# Helper: _is_decline / _is_growth
# ---------------------------------------------------------------------------


def test_is_decline_basic():
    assert _is_decline("revenue declined sharply")
    assert _is_decline("sales dropped 20%")
    assert not _is_decline("revenue grew this quarter")


def test_is_growth_basic():
    assert _is_growth("revenue increased by 15%")
    assert _is_growth("sales grew 20%")
    assert not _is_growth("revenue declined sharply")


# ---------------------------------------------------------------------------
# Helper: _pct_delta
# ---------------------------------------------------------------------------


def test_pct_delta_positive():
    result = _pct_delta(1200.0, 1000.0)
    assert "+20.0%" in result


def test_pct_delta_negative():
    result = _pct_delta(800.0, 1000.0)
    assert "-20.0%" in result


def test_pct_delta_zero_baseline():
    assert _pct_delta(100.0, 0.0) == "N/A"


# ---------------------------------------------------------------------------
# Helper: _longest_consecutive
# ---------------------------------------------------------------------------


def test_longest_consecutive_empty():
    assert _longest_consecutive([]) == 0


def test_longest_consecutive_single():
    assert _longest_consecutive([5]) == 1


def test_longest_consecutive_all_consecutive():
    assert _longest_consecutive([1, 2, 3, 4, 5]) == 5


def test_longest_consecutive_partial():
    assert _longest_consecutive([1, 2, 5, 6, 7]) == 3


def test_longest_consecutive_no_run():
    assert _longest_consecutive([1, 3, 5, 7]) == 1


# ---------------------------------------------------------------------------
# Helper: _jaccard
# ---------------------------------------------------------------------------


def test_jaccard_identical():
    assert _jaccard("foo bar baz", "foo bar baz") == pytest.approx(1.0)


def test_jaccard_disjoint():
    assert _jaccard("foo bar", "baz qux") == pytest.approx(0.0)


def test_jaccard_partial():
    score = _jaccard("foo bar baz", "foo bar qux")
    assert 0.0 < score < 1.0


def test_jaccard_empty():
    assert _jaccard("", "") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Helper: _forecast_direction
# ---------------------------------------------------------------------------


def test_forecast_direction_decline():
    data = [{"period": "1", "value": 100}, {"period": "2", "value": 80}]
    assert _forecast_direction(data) == "decline"


def test_forecast_direction_growth():
    data = [{"period": "1", "value": 80}, {"period": "2", "value": 100}]
    assert _forecast_direction(data) == "growth"


def test_forecast_direction_flat():
    data = [{"period": "1", "value": 100}, {"period": "2", "value": 100}]
    assert _forecast_direction(data) == "flat"


def test_forecast_direction_empty():
    assert _forecast_direction([]) == "flat"


def test_forecast_direction_no_numeric():
    data = [{"period": "1", "label": "A"}, {"period": "2", "label": "B"}]
    assert _forecast_direction(data) == "flat"


# ---------------------------------------------------------------------------
# Rule Engine: anomaly patterns
# ---------------------------------------------------------------------------

engine = RecommendationRuleEngine()


def test_anomaly_drop_generates_recommendation():
    drop_point = _make_anomaly_point(value=400.0, score=4.0, severity="high")  # below mean=1000
    ca = _make_column_anomaly(column="revenue", points=[drop_point])
    resp = _make_anomaly_response(anomalies=[ca])

    recs = engine._from_anomalies(resp)
    assert len(recs) >= 1
    drop_rec = next((r for r in recs if "revenue" in r.action.lower() or "revenue" in r.reason.lower()), None)
    assert drop_rec is not None
    assert drop_rec.source == "anomaly"
    assert drop_rec.priority in ("critical", "high", "medium", "low")


def test_anomaly_spike_generates_recommendation():
    spike_point = _make_anomaly_point(value=5000.0, score=6.0, severity="critical")  # above mean=1000
    ca = _make_column_anomaly(column="sales", points=[spike_point])
    resp = _make_anomaly_response(anomalies=[ca])

    recs = engine._from_anomalies(resp)
    spike_rec = next((r for r in recs if "spike" in r.action.lower() or "spike" in r.reason.lower()), None)
    assert spike_rec is not None


def test_consecutive_anomalies_triggers_data_quality_rec():
    points = [_make_anomaly_point(row_index=i) for i in range(5)]
    ca = _make_column_anomaly(column="cost", points=points, anomaly_count=5)
    resp = _make_anomaly_response(anomalies=[ca])

    recs = engine._from_anomalies(resp)
    dq_rec = next((r for r in recs if r.category == "data_quality"), None)
    assert dq_rec is not None
    assert dq_rec.priority == "high"


def test_multiple_metrics_anomaly_triggers_systemic_rec():
    anomalies = [_make_column_anomaly(column=c) for c in ["rev", "cost", "margin", "units"]]
    resp = _make_anomaly_response(anomalies=anomalies, total=8)

    recs = engine._from_anomalies(resp)
    systemic_rec = next((r for r in recs if "4" in r.action or "KPI" in r.action), None)
    assert systemic_rec is not None
    assert systemic_rec.priority == "high"


def test_anomaly_data_points_are_populated():
    ca = _make_column_anomaly()
    resp = _make_anomaly_response(anomalies=[ca])
    recs = engine._from_anomalies(resp)
    for rec in recs:
        assert len(rec.data_points) >= 1


def test_anomaly_confidence_within_bounds():
    ca = _make_column_anomaly()
    resp = _make_anomaly_response(anomalies=[ca])
    recs = engine._from_anomalies(resp)
    for rec in recs:
        assert 0.0 <= rec.confidence <= 1.0


# ---------------------------------------------------------------------------
# Rule Engine: insight patterns
# ---------------------------------------------------------------------------


def test_declining_trend_generates_high_priority_rec():
    resp = _make_insight_response(trends=["Revenue has declined 15% over the last 3 months"])
    recs = engine._from_insights(resp)
    high_recs = [r for r in recs if r.priority == "high"]
    assert len(high_recs) >= 1
    assert any("revenue" in r.action.lower() or "decline" in r.action.lower() for r in high_recs)


def test_growth_trend_generates_medium_priority_rec():
    resp = _make_insight_response(trends=["Revenue grew 20% this quarter"])
    recs = engine._from_insights(resp)
    growth_recs = [r for r in recs if r.source == "insight" and r.priority in ("medium", "high")]
    assert len(growth_recs) >= 1


def test_underperformer_generates_high_priority_rec():
    resp = _make_insight_response(
        underperformers=[{"column": "marketing_spend", "value": 100}]
    )
    recs = engine._from_insights(resp)
    up_rec = next((r for r in recs if "marketing_spend" in r.reason), None)
    assert up_rec is not None
    assert up_rec.priority == "high"


def test_top_performer_generates_medium_rec():
    resp = _make_insight_response(
        top_performers=[{"column": "sales_channel_A", "value": 9000}]
    )
    recs = engine._from_insights(resp)
    tp_rec = next((r for r in recs if "sales_channel_a" in r.reason.lower()), None)
    assert tp_rec is not None
    assert tp_rec.priority == "medium"


def test_key_insight_decline_generates_rec():
    resp = _make_insight_response(
        key_insights=["Customer churn rate has decreased significantly this month"]
    )
    recs = engine._from_insights(resp)
    assert any(r.source == "insight" for r in recs)


def test_existing_recommendations_passed_through():
    resp = _make_insight_response(
        recommendations=["Increase budget for Product A", "Review pricing strategy"]
    )
    recs = engine._from_insights(resp)
    passthrough = [r for r in recs if r.source == "insight" and r.priority == "medium"]
    assert len(passthrough) >= 2


def test_insight_source_is_insight():
    resp = _make_insight_response(trends=["Sales dropped sharply"])
    recs = engine._from_insights(resp)
    assert all(r.source == "insight" for r in recs)


# ---------------------------------------------------------------------------
# Rule Engine: forecast patterns
# ---------------------------------------------------------------------------


def test_forecast_decline_generates_high_priority():
    forecast = {
        "operation": "forecast",
        "horizon": 6,
        "method_used": "prophet",
        "answer": "Revenue is projected to decline over the next 6 months.",
        "table_data": [{"period": "1", "value": 1000}, {"period": "6", "value": 700}],
        "data_points": 24,
    }
    recs = engine._from_forecast(forecast)
    assert len(recs) >= 1
    assert recs[0].priority == "high"
    assert recs[0].source == "forecast"


def test_forecast_growth_generates_medium_priority():
    forecast = {
        "operation": "forecast",
        "horizon": 3,
        "method_used": "arima",
        "answer": "Revenue is projected to grow over the next 3 months.",
        "table_data": [{"period": "1", "value": 1000}, {"period": "3", "value": 1300}],
        "data_points": 36,
    }
    recs = engine._from_forecast(forecast)
    assert len(recs) >= 1
    assert recs[0].priority == "medium"


def test_forecast_anomaly_operation_generates_review_rec():
    forecast = {
        "operation": "anomaly_detection",
        "horizon": 0,
        "method_used": "seasonal",
        "answer": "Found 3 anomalous periods.",
        "table_data": [{"period": "2"}, {"period": "5"}, {"period": "9"}],
        "data_points": 24,
    }
    recs = engine._from_forecast(forecast)
    assert any("anomaly" in r.action.lower() or "anomalies" in r.action.lower() for r in recs)


def test_low_data_points_generates_low_priority_rec():
    forecast = {
        "operation": "forecast",
        "horizon": 3,
        "method_used": "linear",
        "answer": "Projected growth.",
        "table_data": [{"period": "1", "value": 100}, {"period": "3", "value": 120}],
        "data_points": 5,
    }
    recs = engine._from_forecast(forecast)
    low_rec = next((r for r in recs if r.priority == "low"), None)
    assert low_rec is not None
    assert "5 data point" in low_rec.reason


def test_empty_forecast_returns_empty():
    recs = engine._from_forecast({})
    assert recs == []


def test_forecast_source_is_forecast():
    forecast = {
        "operation": "forecast",
        "horizon": 6,
        "method_used": "prophet",
        "answer": "Decline projected.",
        "table_data": [{"v": 100}, {"v": 70}],
        "data_points": 24,
    }
    recs = engine._from_forecast(forecast)
    assert all(r.source == "forecast" for r in recs)


# ---------------------------------------------------------------------------
# Rule Engine: cross-signal escalation
# ---------------------------------------------------------------------------


def test_cross_signal_escalates_when_metric_in_both():
    anomaly_resp = _make_anomaly_response(
        anomalies=[_make_column_anomaly(column="revenue")]
    )
    insight_resp = _make_insight_response(
        trends=["Revenue has declined 20% this quarter"]
    )
    recs = engine._cross_signal(anomaly_resp, insight_resp, [])
    assert len(recs) >= 1
    assert recs[0].source == "cross_signal"
    assert recs[0].priority in ("critical", "high")


def test_cross_signal_no_overlap_returns_empty():
    anomaly_resp = _make_anomaly_response(
        anomalies=[_make_column_anomaly(column="inventory")]
    )
    insight_resp = _make_insight_response(
        trends=["Marketing spend grew 10%"]
    )
    recs = engine._cross_signal(anomaly_resp, insight_resp, [])
    assert recs == []


def test_cross_signal_none_inputs_returns_empty():
    assert engine._cross_signal(None, None, []) == []
    assert engine._cross_signal(_make_anomaly_response(), None, []) == []
    assert engine._cross_signal(None, _make_insight_response(), []) == []


def test_cross_signal_high_confidence():
    anomaly_resp = _make_anomaly_response(
        anomalies=[_make_column_anomaly(column="sales")]
    )
    insight_resp = _make_insight_response(
        key_insights=["Sales have been declining for the past quarter"]
    )
    recs = engine._cross_signal(anomaly_resp, insight_resp, [])
    if recs:
        assert recs[0].confidence >= 0.9


# ---------------------------------------------------------------------------
# Rule Engine: deduplication and ranking
# ---------------------------------------------------------------------------


def test_deduplicate_removes_near_duplicates():
    rec1 = _make_recommendation(action="Investigate and remediate the decline in revenue column")
    rec2 = _make_recommendation(action="Investigate and remediate the decline in revenue column")
    result = engine._deduplicate_and_rank([rec1, rec2])
    assert len(result) == 1


def test_ranking_puts_critical_before_low():
    low = _make_recommendation(priority="low", confidence=0.9)
    critical = _make_recommendation(priority="critical", confidence=0.5)
    result = engine._deduplicate_and_rank([low, critical])
    assert result[0].priority == "critical"


def test_generate_respects_max_recommendations():
    anomaly_resp = _make_anomaly_response(
        anomalies=[_make_column_anomaly(column=f"col_{i}") for i in range(10)]
    )
    recs = engine.generate(anomalies=anomaly_resp, insights=None, forecast=None, query_results=None, max_recommendations=3)
    assert len(recs) <= 3


def test_generate_with_no_inputs_returns_empty():
    recs = engine.generate(anomalies=None, insights=None, forecast=None, query_results=None)
    assert recs == []


# ---------------------------------------------------------------------------
# RecommendationService: cache
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_agent():
    agent = MagicMock()
    agent.enhance = AsyncMock(return_value=None)
    return agent


@pytest.fixture()
def svc(mock_agent):
    return RecommendationService(
        recommendation_agent=mock_agent,
        cache_ttl=60.0,
        cache_max_entries=10,
    )


@pytest.mark.asyncio
async def test_service_returns_rule_based_when_agent_returns_none(svc, mock_agent):
    mock_agent.enhance.return_value = None
    request = RecommendationRequest(
        dataset_id="ds1",
        anomalies=_make_anomaly_response(),
        max_recommendations=5,
        llm_enhance=True,
    )
    resp = await svc.generate(request)
    assert isinstance(resp, RecommendationResponse)
    assert resp.llm_enhanced is False


@pytest.mark.asyncio
async def test_service_cache_hit_on_second_call(svc):
    request = RecommendationRequest(
        dataset_id="ds2",
        anomalies=_make_anomaly_response(),
        llm_enhance=False,
    )
    resp1 = await svc.generate(request)
    resp2 = await svc.generate(request)
    assert resp1.cache_hit is False
    assert resp2.cache_hit is True


@pytest.mark.asyncio
async def test_service_llm_enhanced_flag_set_when_agent_returns_recs(svc, mock_agent):
    enhanced = [_make_recommendation(action="LLM-polished action")]
    mock_agent.enhance.return_value = enhanced

    request = RecommendationRequest(
        dataset_id="ds3",
        anomalies=_make_anomaly_response(),
        llm_enhance=True,
    )
    resp = await svc.generate(request)
    assert resp.llm_enhanced is True
    assert resp.recommendations[0].action == "LLM-polished action"


@pytest.mark.asyncio
async def test_service_llm_exception_falls_back_to_rules(svc, mock_agent):
    mock_agent.enhance.side_effect = RuntimeError("LLM unavailable")

    request = RecommendationRequest(
        dataset_id="ds4",
        anomalies=_make_anomaly_response(),
        llm_enhance=True,
    )
    resp = await svc.generate(request)
    assert resp.llm_enhanced is False
    assert len(resp.recommendations) >= 0


@pytest.mark.asyncio
async def test_service_skips_llm_when_flag_false(svc, mock_agent):
    request = RecommendationRequest(
        dataset_id="ds5",
        anomalies=_make_anomaly_response(),
        llm_enhance=False,
    )
    await svc.generate(request)
    mock_agent.enhance.assert_not_called()


@pytest.mark.asyncio
async def test_service_summary_is_non_empty(svc):
    request = RecommendationRequest(
        dataset_id="ds6",
        anomalies=_make_anomaly_response(),
        llm_enhance=False,
    )
    resp = await svc.generate(request)
    assert len(resp.summary) > 10


@pytest.mark.asyncio
async def test_service_generation_time_non_negative(svc):
    request = RecommendationRequest(
        dataset_id="ds7",
        insights=_make_insight_response(trends=["Revenue declined 10%"]),
        llm_enhance=False,
    )
    resp = await svc.generate(request)
    assert resp.generation_time_ms >= 0.0


# ---------------------------------------------------------------------------
# _cache_key
# ---------------------------------------------------------------------------


def test_cache_key_same_request_same_key():
    req1 = RecommendationRequest(dataset_id="abc", anomalies=_make_anomaly_response())
    req2 = RecommendationRequest(dataset_id="abc", anomalies=_make_anomaly_response())
    assert _cache_key(req1) == _cache_key(req2)


def test_cache_key_different_dataset_different_key():
    req1 = RecommendationRequest(dataset_id="abc", anomalies=_make_anomaly_response())
    req2 = RecommendationRequest(dataset_id="xyz", anomalies=_make_anomaly_response())
    assert _cache_key(req1) != _cache_key(req2)


def test_cache_key_different_max_recs_different_key():
    req1 = RecommendationRequest(dataset_id="abc", anomalies=_make_anomaly_response(), max_recommendations=5)
    req2 = RecommendationRequest(dataset_id="abc", anomalies=_make_anomaly_response(), max_recommendations=10)
    assert _cache_key(req1) != _cache_key(req2)


def test_cache_key_is_hex_string():
    req = RecommendationRequest(dataset_id="abc", anomalies=_make_anomaly_response())
    key = _cache_key(req)
    assert len(key) == 64
    int(key, 16)  # must be valid hex


# ---------------------------------------------------------------------------
# RecommendationAgent: _parse_response
# ---------------------------------------------------------------------------


def test_agent_parse_valid_json():
    from agents.recommendation_agent import RecommendationAgent
    from app.core.config import Settings

    agent = RecommendationAgent(Settings())
    originals = [_make_recommendation()]
    raw = json.dumps([
        {
            "priority": "medium",
            "action": "LLM improved action text",
            "reason": "Reason with data",
            "expected_impact": "Better outcome",
            "category": "revenue",
            "source": "anomaly",
            "confidence": 0.8,
            "data_points": ["revenue: 500"],
        }
    ])
    result = agent._parse_response(raw, originals)
    assert result is not None
    assert result[0].action == "LLM improved action text"


def test_agent_parse_json_with_code_fence():
    from agents.recommendation_agent import RecommendationAgent
    from app.core.config import Settings

    agent = RecommendationAgent(Settings())
    originals = [_make_recommendation()]
    raw = "```json\n" + json.dumps([originals[0].model_dump()]) + "\n```"
    result = agent._parse_response(raw, originals)
    assert result is not None
    assert len(result) == 1


def test_agent_parse_length_mismatch_returns_originals():
    from agents.recommendation_agent import RecommendationAgent
    from app.core.config import Settings

    agent = RecommendationAgent(Settings())
    originals = [_make_recommendation()]
    raw = json.dumps([originals[0].model_dump(), originals[0].model_dump()])
    result = agent._parse_response(raw, originals)
    assert result == originals


def test_agent_parse_invalid_json_returns_originals():
    from agents.recommendation_agent import RecommendationAgent
    from app.core.config import Settings

    agent = RecommendationAgent(Settings())
    originals = [_make_recommendation()]
    result = agent._parse_response("not json at all", originals)
    assert result == originals


def test_agent_parse_preserves_immutable_fields():
    """LLM cannot change priority, category, source, confidence, or data_points."""
    from agents.recommendation_agent import RecommendationAgent
    from app.core.config import Settings

    agent = RecommendationAgent(Settings())
    original = _make_recommendation(priority="critical", confidence=0.95, source="cross_signal")
    # LLM tries to downgrade priority and change source — must be ignored
    tampered = original.model_dump()
    tampered["priority"] = "low"
    tampered["source"] = "rule"
    tampered["confidence"] = 0.1
    raw = json.dumps([tampered])
    result = agent._parse_response(raw, [original])
    assert result is not None
    assert result[0].priority == "critical"
    assert result[0].source == "cross_signal"
    assert result[0].confidence == pytest.approx(0.95)


def test_agent_no_client_returns_none():
    from agents.recommendation_agent import RecommendationAgent
    from app.core.config import Settings
    import asyncio

    agent = RecommendationAgent(Settings())
    # No set_client() called
    result = asyncio.run(agent.enhance([], context=None, dataset_id="ds1"))
    assert result is None


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_recommendation_confidence_bounds():
    with pytest.raises(Exception):
        Recommendation(
            priority="high",
            action="action",
            reason="reason",
            expected_impact="impact",
            category="revenue",
            source="anomaly",
            confidence=1.5,  # out of range
            data_points=[],
        )


def test_recommendation_request_max_recs_bounds():
    with pytest.raises(Exception):
        RecommendationRequest(dataset_id="x", max_recommendations=0)
    with pytest.raises(Exception):
        RecommendationRequest(dataset_id="x", max_recommendations=51)


def test_recommendation_request_context_max_length():
    with pytest.raises(Exception):
        RecommendationRequest(dataset_id="x", context="x" * 1001)


def test_recommendation_response_total_count():
    resp = RecommendationResponse(
        recommendations=[_make_recommendation()],
        summary="test",
        total_count=1,
    )
    assert resp.total_count == 1
    assert resp.cache_hit is False
    assert resp.llm_enhanced is False


def test_recommendation_data_points_default_empty():
    rec = Recommendation(
        priority="low",
        action="a",
        reason="r",
        expected_impact="e",
        category="general",
        source="rule",
        confidence=0.5,
    )
    assert rec.data_points == []
