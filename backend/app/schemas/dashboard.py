"""Pydantic schemas for the AI Executive Dashboard Generator.

Pipeline:
    GenerateDashboardRequest
        → KPISelectionEngine    → list[KPIMetric]
        → ChartRecommendationEngine → list[ChartPanel]
        → LayoutRecommendationEngine → LayoutConfig
        → DashboardScoringEngine → int (0–100)
        → (optional LLM) → dashboard_name, recommendations
        → DashboardConfig (returned to client or saved to disk)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# KPI metric
# ---------------------------------------------------------------------------


class KPIMetric(BaseModel):
    """One headline KPI extracted from the dataset."""

    id: str = Field(..., description="Stable identifier e.g. 'kpi_0'.")
    label: str = Field(..., description="Human-readable column label.")
    column: str = Field(..., description="Source DataFrame column name.")
    aggregation: str = Field(
        ..., description="'sum' | 'mean' | 'count' | 'max' | 'min'."
    )
    value: float = Field(..., description="Computed aggregate value.")
    formatted_value: str = Field(
        ..., description="Display string, e.g. '$2.45M', '32.1%', '1,234'."
    )
    change_pct: Optional[float] = Field(
        default=None, description="% change vs first half of dataset rows."
    )
    trend: str = Field(..., description="'up' | 'down' | 'flat'.")


# ---------------------------------------------------------------------------
# Chart panel
# ---------------------------------------------------------------------------


class ChartPanel(BaseModel):
    """One chart panel in the dashboard."""

    id: str = Field(..., description="Stable identifier e.g. 'chart_0'.")
    title: str
    chart_type: str = Field(..., description="'bar' | 'line' | 'pie' | 'scatter'.")
    x_field: str
    y_field: str
    chart_spec: dict[str, Any] = Field(
        ..., description="Plotly figure JSON (server-built, not LLM-authored)."
    )
    width: str = Field(..., description="'half' (md:col-span-6) | 'full' (col-span-12).")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


class LayoutCell(BaseModel):
    """One cell in a chart row."""

    id: str = Field(..., description="chart_id this cell renders.")
    width: str = Field(..., description="'half' | 'full'.")


class LayoutConfig(BaseModel):
    """Full dashboard grid layout."""

    kpi_row: list[str] = Field(
        default_factory=list, description="Ordered list of kpi_ids across the top row."
    )
    rows: list[list[LayoutCell]] = Field(
        default_factory=list, description="Chart rows, each row is a list of LayoutCell."
    )


# ---------------------------------------------------------------------------
# Full dashboard config (generated + persisted form)
# ---------------------------------------------------------------------------


class DashboardConfig(BaseModel):
    """Complete dashboard definition — returned by /generate and persisted by /save."""

    dashboard_id: Optional[str] = Field(
        default=None, description="Set only after the dashboard is saved."
    )
    dashboard_name: str
    dataset_id: str
    owner_sub: str = Field(default="")
    kpis: list[KPIMetric] = Field(default_factory=list)
    charts: list[ChartPanel] = Field(default_factory=list)
    layout: LayoutConfig = Field(default_factory=LayoutConfig)
    recommendations: list[str] = Field(default_factory=list)
    score: int = Field(default=0, ge=0, le=100)
    generation_time_ms: float = Field(default=0.0)
    cache_hit: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Metadata (lightweight — used in list responses)
# ---------------------------------------------------------------------------


class DashboardMetadata(BaseModel):
    """Lightweight record for listing saved dashboards."""

    dashboard_id: str
    dashboard_name: str
    dataset_id: str
    score: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class GenerateDashboardRequest(BaseModel):
    """Request body for POST /api/v1/dashboards/generate."""

    dataset_id: str
    prompt: str = Field(
        default="Create an executive dashboard",
        max_length=500,
        description="Natural-language description of the desired dashboard.",
    )
    max_kpis: int = Field(default=6, ge=1, le=10)
    max_charts: int = Field(default=6, ge=1, le=10)


class GenerateDashboardResponse(BaseModel):
    """Response from POST /api/v1/dashboards/generate."""

    dashboard_name: str
    dataset_id: str
    kpis: list[KPIMetric]
    charts: list[ChartPanel]
    layout: LayoutConfig
    recommendations: list[str]
    score: int
    generation_time_ms: float
    cache_hit: bool


class SaveDashboardRequest(BaseModel):
    """Request body for POST /api/v1/dashboards/save."""

    dashboard_config: DashboardConfig
    dashboard_name: Optional[str] = Field(
        default=None,
        description="Override the name inside dashboard_config if provided.",
    )


class SaveDashboardResponse(BaseModel):
    """Response from POST /api/v1/dashboards/save."""

    dashboard_id: str
    dashboard_name: str
    created_at: datetime
    message: str


class DashboardListResponse(BaseModel):
    """Response from GET /api/v1/dashboards."""

    count: int
    dashboards: list[DashboardMetadata]
