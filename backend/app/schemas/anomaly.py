"""Pydantic schemas for the Anomaly Detection API.

Data flow:
    AnomalyRequest
        → AnomalyDetectionEngine (analytics/anomaly_detector.py)
            → list[ColumnAnomaly]          (per-column statistical results)
            → list[str]                    (rule-based possible_reasons)
        → AnomalyChartBuilder              (Plotly JSON)
        → AnomalyResponse
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AnomalyPoint(BaseModel):
    """A single anomalous data point within one column."""

    row_index: int = Field(..., description="Zero-based row index in the original DataFrame.")
    value: float = Field(..., description="Observed numeric value at this row.")
    score: float = Field(
        ...,
        description=(
            "Normalised anomaly score in units comparable to standard deviations. "
            "Z-score: |z|. IQR: IQR-fence distances / IQR. "
            "Isolation Forest: re-scaled isolation depth. "
            "Seasonal: |residual z-score|."
        ),
    )
    severity: str = Field(
        ...,
        description="'low' (<3σ equiv.), 'medium' (≥3), 'high' (≥4), 'critical' (≥6).",
    )
    method: str = Field(
        ...,
        description="Detection method: 'zscore', 'iqr', 'isolation_forest', or 'seasonal'.",
    )
    label: Optional[str] = Field(
        default=None,
        description="Human-readable x-axis label (period, date, or category) when available.",
    )


class ColumnAnomaly(BaseModel):
    """Aggregated anomaly results for one numeric column."""

    column: str
    anomaly_count: int
    anomaly_points: list[AnomalyPoint]
    methods: list[str] = Field(description="Which detection methods flagged this column.")
    mean: float
    std: float
    q1: float
    q3: float
    min_value: float
    max_value: float


class AnomalyRequest(BaseModel):
    """Request body for POST /api/v1/anomalies."""

    dataset_id: str
    columns: Optional[list[str]] = Field(
        default=None,
        description="Numeric columns to analyse. None = all numeric columns (auto-detected).",
    )
    methods: list[str] = Field(
        default=["zscore", "iqr", "isolation_forest", "seasonal"],
        description="Detection methods to apply. Any subset of the four supported methods.",
    )
    zscore_threshold: float = Field(
        default=3.0,
        ge=1.0,
        le=10.0,
        description="Z-score magnitude threshold for flagging a point.",
    )
    iqr_multiplier: float = Field(
        default=1.5,
        ge=0.5,
        le=5.0,
        description="IQR fence multiplier: Q1 − k·IQR  …  Q3 + k·IQR.",
    )
    contamination: float = Field(
        default=0.05,
        ge=0.01,
        le=0.5,
        description="Expected proportion of anomalies — used by Isolation Forest.",
    )
    seasonal_period: Optional[int] = Field(
        default=None,
        ge=2,
        description="Period length for seasonal decomposition (auto-detected when None).",
    )
    time_column: Optional[str] = Field(
        default=None,
        description="Column used as x-axis in charts and for seasonal ordering.",
    )
    merge_methods: bool = Field(
        default=True,
        description=(
            "When True, deduplicate anomaly points across methods — "
            "keep worst severity per row index."
        ),
    )


class AnomalyResponse(BaseModel):
    """Response body for POST /api/v1/anomalies."""

    anomalies: list[ColumnAnomaly] = Field(
        description="Per-column anomaly results, ordered by anomaly_count descending."
    )
    severity: str = Field(
        description="Overall severity: 'none', 'low', 'medium', 'high', or 'critical'."
    )
    affected_metrics: list[str] = Field(
        description="Column names that contain at least one anomaly."
    )
    possible_reasons: list[str] = Field(
        description="Rule-based explanations for the detected anomalies (no LLM hallucination)."
    )
    total_anomaly_count: int
    chart_spec: Optional[dict] = Field(
        default=None,
        description="Plotly figure JSON with anomaly points highlighted by severity.",
    )
    detection_time_ms: float = Field(default=0.0)
    methods_used: list[str]
    cache_hit: bool = Field(default=False)
