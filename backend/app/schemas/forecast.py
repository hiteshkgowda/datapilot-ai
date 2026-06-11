"""Schemas for forecasting and predictive analytics (Phase 8).

As elsewhere, the LLM only emits a validated :class:`ForecastPlan`; the actual
forecasting and anomaly detection is deterministic statistics.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Frequency(str, Enum):
    """Resampling frequency for the time series."""

    DAILY = "D"
    WEEKLY = "W"
    MONTHLY = "M"
    QUARTERLY = "Q"
    YEARLY = "Y"


class AggMethod(str, Enum):
    """How to aggregate the value column within each period."""

    SUM = "sum"
    MEAN = "mean"


class ForecastOperation(str, Enum):
    """Supported predictive operations."""

    FORECAST = "forecast"
    ANOMALY_DETECTION = "anomaly_detection"
    TIMESERIES_AGGREGATE = "timeseries_aggregate"


class ForecastPlan(BaseModel):
    """A structured, validated forecasting instruction produced by the LLM."""

    model_config = {"extra": "forbid"}

    operation: ForecastOperation
    date_column: str = Field(..., description="Temporal column.")
    value_column: str = Field(..., description="Numeric column to analyze.")
    frequency: Frequency = Field(default=Frequency.MONTHLY)
    aggregation: AggMethod = Field(default=AggMethod.SUM)
    horizon: Optional[int] = Field(
        default=None, ge=1, description="Periods to forecast (forecast only)."
    )


class ForecastRequest(BaseModel):
    """Incoming forecasting request."""

    dataset_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)


class ForecastResponse(BaseModel):
    """Result of a forecasting/anomaly operation."""

    answer: str
    operation: ForecastOperation
    table_data: list[dict[str, Any]] = Field(default_factory=list)
    chart_type: Optional[str] = None
    chart_spec: Optional[dict[str, Any]] = None

    # Metadata
    method_used: str
    fallback_used: bool
    data_points: int = Field(..., ge=0)
    horizon: int = Field(..., ge=0)
    frequency: Frequency

    execution_time_ms: float = Field(..., ge=0)
    total_time_ms: float = Field(..., ge=0)
