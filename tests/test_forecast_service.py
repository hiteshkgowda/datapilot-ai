"""Tests for the forecast service (synthetic series, mocked planner)."""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from app.core.config import Settings
from app.core.exceptions import ForecastValidationError
from app.schemas.forecast import (
    AggMethod,
    ForecastOperation,
    ForecastPlan,
    Frequency,
)
from app.services.dataset_service import DatasetService
from app.services.forecast_service import ForecastService

# ---------------------------------------------------------------------------
# _normalize_raw_plan tests
# ---------------------------------------------------------------------------


def test_normalize_aggregation_null_replaced_with_sum():
    raw = {"aggregation": None, "frequency": "M", "horizon": None}
    out = ForecastService._normalize_raw_plan(raw)
    assert out["aggregation"] == "sum"


def test_normalize_aggregation_absent_replaced_with_sum():
    raw = {"frequency": "M", "horizon": None}
    out = ForecastService._normalize_raw_plan(raw)
    assert out["aggregation"] == "sum"


def test_normalize_aggregation_sum_unchanged():
    raw = {"aggregation": "sum", "frequency": "M"}
    out = ForecastService._normalize_raw_plan(raw)
    assert out["aggregation"] == "sum"


def test_normalize_aggregation_mean_unchanged():
    raw = {"aggregation": "mean", "frequency": "M"}
    out = ForecastService._normalize_raw_plan(raw)
    assert out["aggregation"] == "mean"


def test_normalize_frequency_null_replaced_with_monthly():
    raw = {"aggregation": "sum", "frequency": None}
    out = ForecastService._normalize_raw_plan(raw)
    assert out["frequency"] == "M"


def test_normalize_horizon_null_left_as_null():
    """horizon=null is intentional; normalization must not replace it."""
    raw = {"aggregation": "sum", "frequency": "D", "horizon": None}
    out = ForecastService._normalize_raw_plan(raw)
    assert out["horizon"] is None


def test_parse_plan_aggregation_null_succeeds():
    """End-to-end: LLM returns aggregation=null → _parse_plan must not raise."""
    raw = {
        "operation": "anomaly_detection",
        "date_column": "month",
        "value_column": "revenue",
        "frequency": "D",
        "aggregation": None,
        "horizon": None,
    }
    plan = ForecastService._parse_plan(raw)
    assert plan.aggregation is AggMethod.SUM


def test_parse_plan_invalid_aggregation_raises():
    """A value that is not 'sum' or 'mean' must still raise ForecastValidationError."""
    raw = {
        "operation": "forecast",
        "date_column": "month",
        "value_column": "revenue",
        "frequency": "M",
        "aggregation": "average",   # invalid
        "horizon": 6,
    }
    with pytest.raises(ForecastValidationError):
        ForecastService._parse_plan(raw)


class FakePlanner:
    def __init__(self, plan: dict) -> None:
        self._plan = plan

    async def generate_forecast_plan(self, question, schema):
        return self._plan


class FakeDatasets:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def load_with_schema(self, dataset_id: str):
        return self._frame, DatasetService._build_schema(self._frame)


def _frame() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=24, freq="MS").astype(str)
    return pd.DataFrame(
        {
            "month": dates,
            "revenue": [100 + i * 5 for i in range(24)],
            "label": [f"item_{i}" for i in range(24)],
        }
    )


def _service(plan: dict | None = None) -> ForecastService:
    return ForecastService(FakeDatasets(_frame()), FakePlanner(plan or {}), Settings())


def _plan(**kwargs) -> ForecastPlan:
    base = dict(
        operation=ForecastOperation.FORECAST,
        date_column="month",
        value_column="revenue",
        frequency=Frequency.MONTHLY,
        aggregation=AggMethod.SUM,
        horizon=6,
    )
    base.update(kwargs)
    return ForecastPlan(**base)


def test_forecast_run_plan():
    resp = asyncio.run(_service().run_plan("d", _plan(horizon=6)))
    assert resp.horizon == 6
    assert resp.data_points == 24
    assert resp.frequency is Frequency.MONTHLY
    assert resp.chart_spec is not None
    assert any(row.get("is_forecast") for row in resp.table_data)
    assert resp.method_used  # recorded


def test_anomaly_run_plan():
    plan = _plan(operation=ForecastOperation.ANOMALY_DETECTION, horizon=None)
    resp = asyncio.run(_service().run_plan("d", plan))
    assert resp.operation is ForecastOperation.ANOMALY_DETECTION
    assert all("is_anomaly" in row for row in resp.table_data)


def test_aggregate_run_plan():
    plan = _plan(operation=ForecastOperation.TIMESERIES_AGGREGATE, horizon=None)
    resp = asyncio.run(_service().run_plan("d", plan))
    assert resp.method_used == "resample"
    assert len(resp.table_data) == 24


def test_create_forecast_uses_planner():
    plan = {
        "operation": "forecast",
        "date_column": "month",
        "value_column": "revenue",
        "frequency": "M",
        "aggregation": "sum",
        "horizon": 4,
    }
    resp = asyncio.run(_service(plan).create_forecast("d", "forecast revenue"))
    assert resp.horizon == 4


def test_validation_rejects_non_date_column():
    with pytest.raises(ForecastValidationError):
        asyncio.run(_service().run_plan("d", _plan(date_column="label")))


def test_validation_rejects_non_numeric_value():
    with pytest.raises(ForecastValidationError):
        asyncio.run(_service().run_plan("d", _plan(value_column="label")))


def test_validation_rejects_horizon_over_max():
    with pytest.raises(ForecastValidationError):
        asyncio.run(_service().run_plan("d", _plan(horizon=999)))
