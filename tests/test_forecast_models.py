"""Unit tests for deterministic forecasting/anomaly models (synthetic series)."""

from __future__ import annotations

import numpy as np

from app.services import forecast_models as fm
from app.services.forecast_models import detect_anomalies, forecast_series


def test_linear_forecast_continues_trend_and_orders_intervals():
    values = np.arange(1, 13, dtype=float)  # strictly increasing
    out = forecast_series(values, horizon=3, seasonal_periods=0)
    assert len(out.forecast) == 3
    assert out.forecast[0] > values[-1] - 1  # continues upward (~13)
    for lo, fc, up in zip(out.lower, out.forecast, out.upper):
        assert lo <= fc <= up


def test_forecast_horizon_length():
    out = forecast_series(np.arange(1, 13, dtype=float), horizon=5, seasonal_periods=0)
    assert len(out.forecast) == len(out.lower) == len(out.upper) == 5


def test_fallback_when_statsmodels_unavailable(monkeypatch):
    monkeypatch.setattr(fm, "STATSMODELS_AVAILABLE", False)
    out = forecast_series(np.arange(1, 13, dtype=float), horizon=3, seasonal_periods=12)
    assert out.method_used in ("linear", "naive")
    assert out.fallback_used is True


def test_naive_for_very_short_series():
    out = forecast_series(np.array([5.0, 5.0]), horizon=2, seasonal_periods=0)
    assert out.method_used == "naive"
    assert out.forecast == [5.0, 5.0]


def test_anomaly_detects_spike():
    values = np.array([10, 11, 9, 10, 100, 10, 11, 9, 10, 11], dtype=float)
    out = detect_anomalies(values, sensitivity=3.0, seasonal_periods=0)
    assert out.flags[4] is True  # the spike
    assert out.flags[0] is False
