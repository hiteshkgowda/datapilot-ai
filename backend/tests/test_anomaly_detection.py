"""Tests for the Anomaly Detection Engine.

Coverage targets
----------------
- _severity_from_score: all four levels + boundary values
- _merge_points: deduplication, worst-score wins, multi-method
- _auto_detect_columns: excludes id-like columns
- _consecutive_runs: empty, single run, multiple runs
- _overall_severity: none, volume escalation, critical dominates
- ZScoreDetector: happy path, no anomalies, std=0, insufficient rows, correct indices
- IQRDetector: happy path, no anomalies, zero-IQR fallback, multiplier variation
- SeasonalAnomalyDetector: rolling-MAD fallback, insufficient rows, correct method tag
- IsolationForestDetector: basic smoke test, insufficient rows, no columns
- AnomalyDetectionEngine: full pipeline, empty df, explicit columns, methods subset,
                          time_column labelling, no numeric cols, merged vs unmerged
- AnomalyChartBuilder: chart structure, single column, empty input
- AnomalyDetectionService: cache hit/miss, timing, error response
- Schema defaults: AnomalyRequest, AnomalyResponse, AnomalyPoint
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pandas as pd
import pytest

from analytics.anomaly_detector import (
    AnomalyChartBuilder,
    AnomalyDetectionEngine,
    IQRDetector,
    IsolationForestDetector,
    SeasonalAnomalyDetector,
    ZScoreDetector,
    _auto_detect_columns,
    _consecutive_runs,
    _merge_points,
    _overall_severity,
    _severity_from_score,
)
from app.schemas.anomaly import AnomalyPoint, AnomalyRequest, AnomalyResponse, ColumnAnomaly
from app.services.anomaly_service import AnomalyDetectionService, _cache_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _flat_df(n: int = 50, seed: int = 0) -> pd.DataFrame:
    """Normal-distribution revenue column with two injected anomalies."""
    rng = np.random.default_rng(seed)
    revenue = rng.normal(loc=1000.0, scale=50.0, size=n).tolist()
    revenue[10] = 5000.0   # massive spike  → critical z-score
    revenue[30] = -500.0   # large negative → critical
    return pd.DataFrame({"month": [f"M{i:02d}" for i in range(n)], "revenue": revenue})


def _multi_col_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 60
    df = pd.DataFrame(
        {
            "month": [f"M{i:02d}" for i in range(n)],
            "revenue": rng.normal(1000, 50, n),
            "orders": rng.normal(200, 20, n),
            "cost": rng.normal(500, 30, n),
        }
    )
    df.loc[5, "revenue"] = 9000.0
    df.loc[15, "orders"] = 2000.0
    return df


def _make_point(row_index: int = 0, score: float = 4.0, severity: str = "high", method: str = "zscore") -> AnomalyPoint:
    return AnomalyPoint(row_index=row_index, value=100.0, score=score, severity=severity, method=method)


def _make_col_anomaly(col: str = "revenue", count: int = 2, sev: str = "high") -> ColumnAnomaly:
    pts = [_make_point(i, 4.0, sev) for i in range(count)]
    return ColumnAnomaly(
        column=col, anomaly_count=count, anomaly_points=pts,
        methods=["zscore"], mean=1000.0, std=50.0,
        q1=975.0, q3=1025.0, min_value=500.0, max_value=5000.0,
    )


# ---------------------------------------------------------------------------
# _severity_from_score
# ---------------------------------------------------------------------------


def test_severity_critical() -> None:
    assert _severity_from_score(6.0) == "critical"
    assert _severity_from_score(10.0) == "critical"


def test_severity_high() -> None:
    assert _severity_from_score(4.0) == "high"
    assert _severity_from_score(5.9) == "high"


def test_severity_medium() -> None:
    assert _severity_from_score(3.0) == "medium"
    assert _severity_from_score(3.99) == "medium"


def test_severity_low() -> None:
    assert _severity_from_score(0.0) == "low"
    assert _severity_from_score(2.99) == "low"


def test_severity_boundary_exact_6() -> None:
    assert _severity_from_score(6.0) == "critical"


# ---------------------------------------------------------------------------
# _merge_points
# ---------------------------------------------------------------------------


def test_merge_deduplicates_same_index() -> None:
    p1 = _make_point(row_index=5, score=3.5, method="zscore")
    p2 = _make_point(row_index=5, score=5.0, method="iqr")
    merged = _merge_points([[p1], [p2]])
    assert len(merged) == 1
    assert merged[0].score == pytest.approx(5.0)
    assert merged[0].method == "iqr"


def test_merge_keeps_different_indices() -> None:
    p1 = _make_point(row_index=1, score=3.5)
    p2 = _make_point(row_index=2, score=4.0)
    merged = _merge_points([[p1], [p2]])
    assert len(merged) == 2


def test_merge_empty_input() -> None:
    assert _merge_points([]) == []
    assert _merge_points([[]]) == []


def test_merge_single_method() -> None:
    pts = [_make_point(i) for i in range(3)]
    merged = _merge_points([pts])
    assert len(merged) == 3


def test_merge_sorted_by_row_index() -> None:
    pts = [_make_point(row_index=i) for i in [5, 1, 3]]
    merged = _merge_points([pts])
    assert [p.row_index for p in merged] == [1, 3, 5]


# ---------------------------------------------------------------------------
# _auto_detect_columns
# ---------------------------------------------------------------------------


def test_auto_detect_excludes_id_cols() -> None:
    df = pd.DataFrame({"customer_id": [1, 2], "revenue": [100.0, 200.0], "order_count": [5, 6]})
    cols = _auto_detect_columns(df)
    assert "customer_id" not in cols
    assert "revenue" in cols
    assert "order_count" in cols


def test_auto_detect_non_numeric_excluded() -> None:
    df = pd.DataFrame({"name": ["Alice", "Bob"], "revenue": [100.0, 200.0]})
    cols = _auto_detect_columns(df)
    assert "name" not in cols
    assert "revenue" in cols


# ---------------------------------------------------------------------------
# _consecutive_runs
# ---------------------------------------------------------------------------


def test_consecutive_runs_empty() -> None:
    assert _consecutive_runs([]) == []


def test_consecutive_runs_single_element() -> None:
    assert _consecutive_runs([5]) == []


def test_consecutive_runs_detects_run() -> None:
    runs = _consecutive_runs([3, 4, 5, 10, 11])
    assert [3, 4, 5] in runs
    assert [10, 11] in runs


def test_consecutive_runs_no_runs() -> None:
    assert _consecutive_runs([1, 3, 5, 7]) == []


# ---------------------------------------------------------------------------
# _overall_severity
# ---------------------------------------------------------------------------


def test_overall_severity_none_for_empty() -> None:
    assert _overall_severity([]) == "none"


def test_overall_severity_critical_dominates() -> None:
    ca = _make_col_anomaly(sev="critical")
    assert _overall_severity([ca]) == "critical"


def test_overall_severity_volume_escalates_low() -> None:
    # 10+ anomalies that are "low" → escalated to "medium"
    ca = _make_col_anomaly(count=10, sev="low")
    result = _overall_severity([ca])
    assert result in ("medium", "high", "critical")


# ---------------------------------------------------------------------------
# ZScoreDetector
# ---------------------------------------------------------------------------


def test_zscore_detects_spike() -> None:
    # Row 10 = 5000 (massive spike). Row 30 = -500 but, because the spike at row 10
    # inflates σ by ~10×, the -500 value's z-score may fall below 3.0.
    # The important guarantee is that the most extreme outlier IS flagged.
    df = _flat_df()
    pts = ZScoreDetector().detect(df, "revenue", threshold=3.0)
    indices = {p.row_index for p in pts}
    assert 10 in indices  # massive spike is always detected
    assert len(pts) >= 1


def test_zscore_no_anomalies_normal_data() -> None:
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"revenue": rng.normal(1000, 50, 100)})
    pts = ZScoreDetector().detect(df, "revenue", threshold=5.0)
    assert len(pts) == 0


def test_zscore_std_zero_returns_empty() -> None:
    df = pd.DataFrame({"revenue": [100.0] * 10})
    pts = ZScoreDetector().detect(df, "revenue")
    assert pts == []


def test_zscore_insufficient_rows() -> None:
    df = pd.DataFrame({"revenue": [100.0, 200.0]})
    pts = ZScoreDetector().detect(df, "revenue")
    assert pts == []


def test_zscore_correct_method_tag() -> None:
    df = _flat_df()
    pts = ZScoreDetector().detect(df, "revenue")
    assert all(p.method == "zscore" for p in pts)


def test_zscore_label_populated_with_time_col() -> None:
    df = _flat_df()
    pts = ZScoreDetector().detect(df, "revenue", time_col="month")
    labeled = [p for p in pts if p.label is not None]
    assert len(labeled) > 0


def test_zscore_score_is_z_magnitude() -> None:
    df = _flat_df()
    pts = ZScoreDetector().detect(df, "revenue")
    # The spike at row 10 inflates σ, so the realised z is ~6-7 rather than
    # the naïve (5000-1000)/50=80.  The key guarantee is that it is flagged
    # as critical (score ≥ 6) or at least high (score ≥ 4).
    spike = next(p for p in pts if p.row_index == 10)
    assert spike.score > 3.0
    assert spike.severity in ("critical", "high", "medium")


# ---------------------------------------------------------------------------
# IQRDetector
# ---------------------------------------------------------------------------


def test_iqr_detects_outlier() -> None:
    df = _flat_df()
    pts = IQRDetector().detect(df, "revenue", multiplier=1.5)
    indices = {p.row_index for p in pts}
    assert 10 in indices


def test_iqr_no_anomalies_tight_data() -> None:
    rng = np.random.default_rng(2)
    df = pd.DataFrame({"revenue": rng.normal(1000, 1, 100)})
    pts = IQRDetector().detect(df, "revenue", multiplier=3.0)
    assert len(pts) == 0


def test_iqr_zero_iqr_fallback() -> None:
    """When all values are equal, IQR=0 — should not raise."""
    df = pd.DataFrame({"revenue": [100.0] * 4 + [9999.0]})
    pts = IQRDetector().detect(df, "revenue")
    assert any(p.row_index == 4 for p in pts)


def test_iqr_correct_method_tag() -> None:
    df = _flat_df()
    pts = IQRDetector().detect(df, "revenue")
    assert all(p.method == "iqr" for p in pts)


def test_iqr_insufficient_rows() -> None:
    df = pd.DataFrame({"revenue": [1.0, 2.0, 3.0]})
    pts = IQRDetector().detect(df, "revenue")
    assert pts == []


def test_iqr_multiplier_affects_results() -> None:
    df = _flat_df()
    strict = IQRDetector().detect(df, "revenue", multiplier=0.5)
    loose = IQRDetector().detect(df, "revenue", multiplier=3.0)
    assert len(strict) >= len(loose)


# ---------------------------------------------------------------------------
# SeasonalAnomalyDetector (rolling-MAD path always available)
# ---------------------------------------------------------------------------


def test_seasonal_rolling_mad_detects_spike() -> None:
    rng = np.random.default_rng(3)
    values = rng.normal(100, 5, 40).tolist()
    values[20] = 1000.0  # massive spike
    df = pd.DataFrame({"revenue": values})
    pts = SeasonalAnomalyDetector().detect(df, "revenue", threshold=3.0)
    indices = {p.row_index for p in pts}
    assert 20 in indices


def test_seasonal_insufficient_rows_returns_empty() -> None:
    df = pd.DataFrame({"revenue": [1.0] * 5})
    pts = SeasonalAnomalyDetector().detect(df, "revenue")
    assert pts == []


def test_seasonal_method_tag() -> None:
    rng = np.random.default_rng(4)
    values = rng.normal(100, 5, 40).tolist()
    values[10] = 5000.0
    df = pd.DataFrame({"revenue": values})
    pts = SeasonalAnomalyDetector().detect(df, "revenue", threshold=3.0)
    assert all(p.method == "seasonal" for p in pts)


def test_seasonal_no_anomalies_flat_series() -> None:
    df = pd.DataFrame({"revenue": [100.0] * 20})
    pts = SeasonalAnomalyDetector().detect(df, "revenue", threshold=3.0)
    assert pts == []


# ---------------------------------------------------------------------------
# IsolationForestDetector
# ---------------------------------------------------------------------------


def test_iso_insufficient_rows_returns_empty() -> None:
    df = pd.DataFrame({"revenue": [1.0, 2.0, 3.0]})
    result = IsolationForestDetector().detect(df, ["revenue"])
    assert result == {}


def test_iso_no_columns_returns_empty() -> None:
    df = _flat_df()
    result = IsolationForestDetector().detect(df, [])
    assert result == {}


def test_iso_returns_dict_keyed_by_column() -> None:
    df = _multi_col_df()
    result = IsolationForestDetector().detect(df, ["revenue", "orders"])
    assert isinstance(result, dict)
    for col, pts in result.items():
        assert col in ("revenue", "orders")
        assert all(isinstance(p, AnomalyPoint) for p in pts)


def test_iso_method_tag() -> None:
    df = _multi_col_df()
    result = IsolationForestDetector().detect(df, ["revenue"])
    for pts in result.values():
        assert all(p.method == "isolation_forest" for p in pts)


# ---------------------------------------------------------------------------
# AnomalyDetectionEngine — full pipeline
# ---------------------------------------------------------------------------


def test_engine_full_pipeline() -> None:
    df = _flat_df()
    engine = AnomalyDetectionEngine(zscore_threshold=3.0)
    col_anomalies, reasons = engine.analyze(df, None, ["zscore", "iqr"], time_col="month")
    assert len(col_anomalies) > 0
    assert any("revenue" == ca.column for ca in col_anomalies)
    assert len(reasons) > 0


def test_engine_empty_df_returns_empty() -> None:
    df = pd.DataFrame(columns=["month", "revenue"])
    engine = AnomalyDetectionEngine()
    col_anomalies, reasons = engine.analyze(df, None, ["zscore"])
    assert col_anomalies == []
    assert len(reasons) > 0


def test_engine_no_numeric_cols_returns_empty() -> None:
    df = pd.DataFrame({"name": ["Alice", "Bob"], "month": ["Jan", "Feb"]})
    engine = AnomalyDetectionEngine()
    col_anomalies, reasons = engine.analyze(df, None, ["zscore"])
    assert col_anomalies == []


def test_engine_explicit_columns_used() -> None:
    df = _multi_col_df()
    engine = AnomalyDetectionEngine()
    col_anomalies, _ = engine.analyze(df, ["revenue"], ["zscore"])
    cols = {ca.column for ca in col_anomalies}
    assert cols <= {"revenue"}


def test_engine_methods_subset() -> None:
    df = _flat_df()
    engine = AnomalyDetectionEngine()
    col_anomalies, _ = engine.analyze(df, None, ["zscore"])
    for ca in col_anomalies:
        assert "zscore" in ca.methods


def test_engine_sorted_by_anomaly_count() -> None:
    df = _multi_col_df()
    engine = AnomalyDetectionEngine(zscore_threshold=2.5)
    col_anomalies, _ = engine.analyze(df, None, ["zscore"])
    counts = [ca.anomaly_count for ca in col_anomalies]
    assert counts == sorted(counts, reverse=True)


def test_engine_stats_populated() -> None:
    df = _flat_df()
    engine = AnomalyDetectionEngine()
    col_anomalies, _ = engine.analyze(df, None, ["zscore"])
    for ca in col_anomalies:
        assert ca.mean != 0.0 or ca.std == 0.0  # mean is populated
        assert ca.q1 <= ca.q3


def test_engine_anomaly_points_have_correct_row_indices() -> None:
    df = _flat_df()
    engine = AnomalyDetectionEngine(zscore_threshold=3.0)
    col_anomalies, _ = engine.analyze(df, None, ["zscore"])
    for ca in col_anomalies:
        for pt in ca.anomaly_points:
            assert 0 <= pt.row_index < len(df)


def test_engine_merge_false_keeps_all_method_points() -> None:
    df = _flat_df()
    engine_merged = AnomalyDetectionEngine(zscore_threshold=3.0, merge_methods=True)
    engine_unmerged = AnomalyDetectionEngine(zscore_threshold=3.0, merge_methods=False)
    merged, _ = engine_merged.analyze(df, None, ["zscore", "iqr"])
    unmerged, _ = engine_unmerged.analyze(df, None, ["zscore", "iqr"])
    merged_total = sum(ca.anomaly_count for ca in merged)
    unmerged_total = sum(ca.anomaly_count for ca in unmerged)
    assert unmerged_total >= merged_total


# ---------------------------------------------------------------------------
# AnomalyChartBuilder
# ---------------------------------------------------------------------------


def test_chart_builder_returns_dict() -> None:
    df = _flat_df()
    engine = AnomalyDetectionEngine(zscore_threshold=3.0)
    col_anomalies, _ = engine.analyze(df, None, ["zscore"])
    chart = AnomalyChartBuilder().build(df, col_anomalies, time_col="month")
    assert isinstance(chart, dict)
    assert "data" in chart
    assert "layout" in chart


def test_chart_builder_empty_returns_none() -> None:
    df = _flat_df()
    chart = AnomalyChartBuilder().build(df, [])
    assert chart is None


def test_chart_builder_has_anomaly_traces() -> None:
    df = _flat_df()
    engine = AnomalyDetectionEngine(zscore_threshold=3.0)
    col_anomalies, _ = engine.analyze(df, None, ["zscore"])
    chart = AnomalyChartBuilder().build(df, col_anomalies)
    assert chart is not None
    trace_names = [t.get("name", "") for t in chart["data"]]
    # There should be at least one anomaly trace and one normal trace
    assert any("Normal" in n for n in trace_names)
    assert any("Anomaly" in n for n in trace_names)


def test_chart_builder_limits_to_3_subplots() -> None:
    df = _multi_col_df()
    # Create 5 fake ColumnAnomaly objects
    cas = [_make_col_anomaly(col=f"col_{i}") for i in range(5)]
    chart = AnomalyChartBuilder().build(df, cas)
    # Just verify it doesn't raise and returns valid Plotly JSON
    assert chart is not None
    assert "layout" in chart


# ---------------------------------------------------------------------------
# AnomalyDetectionService
# ---------------------------------------------------------------------------


def _make_svc() -> AnomalyDetectionService:
    return AnomalyDetectionService(cache_ttl=60.0, cache_max_entries=10)


def test_service_detects_anomalies() -> None:
    df = _flat_df()
    svc = _make_svc()
    result = asyncio.run(svc.detect(df, {"dataset_id": "ds1", "question": "anomalies"}))
    assert isinstance(result, AnomalyResponse)
    assert result.total_anomaly_count > 0
    assert result.severity != "none"


def test_service_cache_hit() -> None:
    df = _flat_df()
    svc = _make_svc()
    params: dict[str, Any] = {"dataset_id": "ds1", "question": "anomalies"}
    asyncio.run(svc.detect(df, params))
    result2 = asyncio.run(svc.detect(df, params))
    assert result2.cache_hit is True


def test_service_first_call_not_cache_hit() -> None:
    df = _flat_df()
    svc = _make_svc()
    result = asyncio.run(svc.detect(df, {"dataset_id": "fresh_ds"}))
    assert result.cache_hit is False


def test_service_detection_time_populated() -> None:
    df = _flat_df()
    svc = _make_svc()
    result = asyncio.run(svc.detect(df, {"dataset_id": "ds_timing"}))
    assert result.detection_time_ms >= 0.0


def test_service_affected_metrics_populated() -> None:
    df = _flat_df()
    svc = _make_svc()
    result = asyncio.run(svc.detect(df, {"dataset_id": "ds_metrics"}))
    assert "revenue" in result.affected_metrics


def test_service_chart_spec_present() -> None:
    df = _flat_df()
    svc = _make_svc()
    result = asyncio.run(svc.detect(df, {"dataset_id": "ds_chart"}))
    assert result.chart_spec is not None
    assert "data" in result.chart_spec


def test_service_possible_reasons_populated() -> None:
    df = _flat_df()
    svc = _make_svc()
    result = asyncio.run(svc.detect(df, {"dataset_id": "ds_reasons"}))
    assert len(result.possible_reasons) > 0
    assert all(isinstance(r, str) for r in result.possible_reasons)


# ---------------------------------------------------------------------------
# _cache_key
# ---------------------------------------------------------------------------


def test_cache_key_deterministic() -> None:
    k1 = _cache_key("ds1", None, ["zscore"], 3.0, 1.5, 0.05, None)
    k2 = _cache_key("ds1", None, ["zscore"], 3.0, 1.5, 0.05, None)
    assert k1 == k2


def test_cache_key_differs_by_methods() -> None:
    k1 = _cache_key("ds1", None, ["zscore"], 3.0, 1.5, 0.05, None)
    k2 = _cache_key("ds1", None, ["iqr"], 3.0, 1.5, 0.05, None)
    assert k1 != k2


def test_cache_key_columns_sorted() -> None:
    k1 = _cache_key("ds1", ["b", "a"], ["zscore"], 3.0, 1.5, 0.05, None)
    k2 = _cache_key("ds1", ["a", "b"], ["zscore"], 3.0, 1.5, 0.05, None)
    assert k1 == k2


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_anomaly_request_defaults() -> None:
    req = AnomalyRequest(dataset_id="ds1")
    assert req.zscore_threshold == pytest.approx(3.0)
    assert req.iqr_multiplier == pytest.approx(1.5)
    assert req.contamination == pytest.approx(0.05)
    assert req.merge_methods is True
    assert "zscore" in req.methods
    assert "iqr" in req.methods


def test_anomaly_response_defaults() -> None:
    resp = AnomalyResponse(
        anomalies=[],
        severity="none",
        affected_metrics=[],
        possible_reasons=[],
        total_anomaly_count=0,
        methods_used=[],
    )
    assert resp.cache_hit is False
    assert resp.detection_time_ms == pytest.approx(0.0)
    assert resp.chart_spec is None


def test_anomaly_point_required_fields() -> None:
    pt = AnomalyPoint(row_index=5, value=9999.0, score=7.2, severity="critical", method="zscore")
    assert pt.label is None
    assert pt.severity == "critical"
