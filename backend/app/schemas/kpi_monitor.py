"""Pydantic schemas for the KPI Monitoring API."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class KPIAlert(BaseModel):
    severity: Literal["critical", "high", "medium", "low"]
    kpi_name: str
    message: str
    value: float
    threshold: float
    row_index: int
    label: Optional[str] = None  # date/period label if available


class KPIStat(BaseModel):
    column: str
    label: str
    current_value: float
    formatted_value: str
    mean: float
    std: float
    min_value: float
    max_value: float
    p25: float
    p75: float
    change_pct: Optional[float] = None
    trend: Literal["up", "down", "flat"]
    health: Literal["healthy", "warning", "critical", "unknown"]
    alert_count: int
    sparkline: list[float] = Field(default_factory=list)
    chart_spec: Optional[dict[str, Any]] = None


class KPIRecommendation(BaseModel):
    priority: Literal["critical", "high", "medium", "low"]
    kpi: str
    issue: str
    action: str


class KPIMonitorRequest(BaseModel):
    dataset_id: str
    max_kpis: int = Field(default=12, ge=1, le=24)


class KPIMonitorResponse(BaseModel):
    dataset_id: str
    overall_health: Literal["healthy", "warning", "critical", "unknown"]
    healthy_count: int
    warning_count: int
    critical_count: int
    kpis: list[KPIStat]
    alerts: list[KPIAlert]
    recommendations: list[KPIRecommendation]
    time_column: Optional[str] = None
    row_count: int
    analysis_time_ms: float
    cache_hit: bool = False
