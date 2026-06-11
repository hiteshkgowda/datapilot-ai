"""Forecast service: validation, series preparation and deterministic models.

Parallel to AnalyticsService. The LLM (via ForecastPlanner) only chooses the
plan; series preparation, model selection and anomaly detection are all
deterministic. Results carry method/fallback metadata.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import ForecastValidationError
from app.schemas.forecast import (
    AggMethod,
    ForecastOperation,
    ForecastPlan,
    ForecastResponse,
    Frequency,
)
from app.services import forecast_chart
from app.services.dataset_service import DatasetSchema, DatasetService
from app.services.forecast_models import detect_anomalies, forecast_series
from app.services.forecast_planner import ForecastPlanner

# pandas resample rule and seasonal period per frequency.
_FREQUENCY = {
    Frequency.DAILY: ("D", 7),
    Frequency.WEEKLY: ("W", 52),
    Frequency.MONTHLY: ("MS", 12),
    Frequency.QUARTERLY: ("QS", 4),
    Frequency.YEARLY: ("YS", 0),
}


class ForecastService:
    """Produce forecasts and anomaly detections over a dataset."""

    def __init__(
        self,
        dataset_service: DatasetService,
        planner: ForecastPlanner,
        settings: Settings,
    ) -> None:
        self._datasets = dataset_service
        self._planner = planner
        self._max_horizon = settings.max_forecast_horizon
        self._default_horizon = settings.forecast_default_horizon
        self._min_points = settings.forecast_min_points
        self._sensitivity = settings.anomaly_sensitivity

    async def create_forecast(
        self, dataset_id: str, question: str
    ) -> ForecastResponse:
        """Plan (via LLM), validate and execute a forecast for a question."""
        frame, schema = await run_in_threadpool(
            self._datasets.load_with_schema, dataset_id
        )
        raw_plan = await self._planner.generate_forecast_plan(
            question, schema.dtypes
        )
        plan = self._parse_plan(raw_plan)
        return await self._execute_async(plan, frame, schema)

    async def run_plan(
        self, dataset_id: str, plan: ForecastPlan
    ) -> ForecastResponse:
        """Execute a caller-supplied plan deterministically (no LLM)."""
        frame, schema = await run_in_threadpool(
            self._datasets.load_with_schema, dataset_id
        )
        return await self._execute_async(plan, frame, schema)

    async def _execute_async(
        self, plan: ForecastPlan, frame: pd.DataFrame, schema: DatasetSchema
    ) -> ForecastResponse:
        total_start = time.perf_counter()
        self._validate(plan, schema, frame)
        exec_start = time.perf_counter()
        response = await run_in_threadpool(self._execute, plan, frame)
        execution_ms = (time.perf_counter() - exec_start) * 1000.0
        total_ms = (time.perf_counter() - total_start) * 1000.0
        return response.model_copy(
            update={
                "execution_time_ms": round(execution_ms, 3),
                "total_time_ms": round(total_ms, 3),
            }
        )

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_raw_plan(raw: dict[str, Any]) -> dict[str, Any]:
        """Replace null LLM outputs with safe defaults before Pydantic validation.

        Pydantic Field(default=...) only fires when the key is *absent*; an
        explicit null bypasses it and raises a ValidationError. LLMs routinely
        emit null for fields they consider "not applicable" to the chosen
        operation (e.g. aggregation=null for anomaly_detection). We correct
        those here so ForecastPlan stays strict and non-Optional.
        """
        out = dict(raw)
        if out.get("aggregation") is None:
            out["aggregation"] = "sum"
        if out.get("frequency") is None:
            out["frequency"] = "M"
        # horizon null is intentional and accepted by the schema — leave it.
        return out

    @staticmethod
    def _parse_plan(raw_plan: dict[str, Any]) -> ForecastPlan:
        normalized = ForecastService._normalize_raw_plan(raw_plan)
        try:
            return ForecastPlan.model_validate(normalized)
        except ValidationError as exc:
            raise ForecastValidationError(
                f"The generated forecast plan is malformed: {exc}"
            ) from exc

    def _validate(
        self, plan: ForecastPlan, schema: DatasetSchema, frame: pd.DataFrame
    ) -> None:
        columns = set(schema.column_names)
        if plan.date_column not in columns:
            raise ForecastValidationError(
                f"Unknown date column '{plan.date_column}'."
            )
        if plan.value_column not in columns:
            raise ForecastValidationError(
                f"Unknown value column '{plan.value_column}'."
            )
        # The value column must be numeric.
        if plan.value_column not in schema.numeric_columns:
            raise ForecastValidationError(
                f"Value column '{plan.value_column}' is not numeric."
            )
        # The date column must be parseable as datetime.
        parsed = pd.to_datetime(frame[plan.date_column], errors="coerce")
        if parsed.notna().mean() < 0.5:
            raise ForecastValidationError(
                f"Column '{plan.date_column}' is not parseable as dates."
            )
        if plan.operation is ForecastOperation.FORECAST:
            horizon = plan.horizon or self._default_horizon
            if horizon > self._max_horizon:
                raise ForecastValidationError(
                    f"Horizon {horizon} exceeds the maximum "
                    f"of {self._max_horizon}."
                )

    # ------------------------------------------------------------------ #
    # Execution (deterministic)
    # ------------------------------------------------------------------ #
    def _execute(self, plan: ForecastPlan, frame: pd.DataFrame) -> ForecastResponse:
        series, seasonal_periods, rule = self._prepare_series(plan, frame)
        data_points = int(series.size)

        if plan.operation is ForecastOperation.FORECAST:
            return self._do_forecast(plan, series, seasonal_periods, rule, data_points)
        if plan.operation is ForecastOperation.ANOMALY_DETECTION:
            return self._do_anomaly(plan, series, seasonal_periods, data_points)
        return self._do_aggregate(plan, series, data_points)

    def _prepare_series(
        self, plan: ForecastPlan, frame: pd.DataFrame
    ) -> tuple[pd.Series, int, str]:
        rule, seasonal_periods = _FREQUENCY[plan.frequency]
        timestamps = pd.to_datetime(frame[plan.date_column], errors="coerce")
        values = pd.to_numeric(frame[plan.value_column], errors="coerce")
        prepared = (
            pd.DataFrame({"ts": timestamps, "val": values})
            .dropna()
            .set_index("ts")
            .sort_index()
        )
        agg = "sum" if plan.aggregation is AggMethod.SUM else "mean"
        series = prepared["val"].resample(rule).agg(agg)
        if agg == "sum":
            series = series.fillna(0.0)
        else:
            series = series.interpolate().bfill().fillna(0.0)
        return series, seasonal_periods, rule

    def _do_forecast(
        self, plan, series, seasonal_periods, rule, data_points
    ) -> ForecastResponse:
        horizon = min(plan.horizon or self._default_horizon, self._max_horizon)
        output = forecast_series(series.to_numpy(), horizon, seasonal_periods)

        future_index = pd.date_range(
            start=series.index[-1], periods=horizon + 1, freq=rule
        )[1:]
        table = [
            {"timestamp": ts.isoformat(), "value": float(v), "is_forecast": False}
            for ts, v in series.items()
        ] + [
            {
                "timestamp": ts.isoformat(),
                "value": round(fv, 4),
                "lower": round(lo, 4),
                "upper": round(up, 4),
                "is_forecast": True,
            }
            for ts, fv, lo, up in zip(
                future_index, output.forecast, output.lower, output.upper
            )
        ]
        chart_spec = forecast_chart.forecast_figure(
            series, future_index, output.forecast, output.lower, output.upper,
            plan.value_column,
        )
        note = (
            " (a simpler model was used due to limited data)"
            if output.fallback_used and data_points < self._min_points
            else ""
        )
        answer = (
            f"Forecast of '{plan.value_column}' for the next {horizon} "
            f"period(s) using {output.method_used}{note}."
        )
        return self._response(
            plan, answer, table, chart_spec, output.method_used,
            output.fallback_used, data_points, horizon,
        )

    def _do_anomaly(
        self, plan, series, seasonal_periods, data_points
    ) -> ForecastResponse:
        output = detect_anomalies(
            series.to_numpy(), self._sensitivity, seasonal_periods
        )
        table = [
            {
                "timestamp": ts.isoformat(),
                "value": float(v),
                "is_anomaly": bool(flag),
            }
            for (ts, v), flag in zip(series.items(), output.flags)
        ]
        chart_spec = forecast_chart.anomaly_figure(
            series, output.flags, plan.value_column
        )
        count = sum(output.flags)
        answer = (
            f"Detected {count} anomaly(ies) in '{plan.value_column}' "
            f"using {output.method_used}."
        )
        return self._response(
            plan, answer, table, chart_spec, output.method_used,
            output.fallback_used, data_points, 0,
        )

    def _do_aggregate(self, plan, series, data_points) -> ForecastResponse:
        table = [
            {"timestamp": ts.isoformat(), "value": float(v)}
            for ts, v in series.items()
        ]
        chart_spec = forecast_chart.timeseries_figure(series, plan.value_column)
        answer = (
            f"Aggregated '{plan.value_column}' into {data_points} "
            f"{plan.frequency.value} period(s)."
        )
        return self._response(
            plan, answer, table, chart_spec, "resample", False, data_points, 0
        )

    def _response(
        self, plan, answer, table, chart_spec, method, fallback, data_points, horizon
    ) -> ForecastResponse:
        return ForecastResponse(
            answer=answer,
            operation=plan.operation,
            table_data=table,
            chart_type="line",
            chart_spec=chart_spec,
            method_used=method,
            fallback_used=fallback,
            data_points=data_points,
            horizon=horizon,
            frequency=plan.frequency,
            execution_time_ms=0.0,
            total_time_ms=0.0,
        )
