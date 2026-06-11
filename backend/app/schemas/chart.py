"""Schemas for visualization (Phase 3).

The LLM only ever *recommends* a chart type (an enum value). The actual chart
specification is built deterministically server-side from validated data, so
none of these schemas carry model-authored code.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ChartType(str, Enum):
    """The supported, allowlisted chart types."""

    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"


class ChartRecommendation(BaseModel):
    """A resolved, validated chart decision produced by the service.

    Distinct from the LLM's advisory ``chart_type`` on the query plan: this is
    what the service actually renders, after compatibility checks and fallback.
    """

    chart_type: ChartType
    x_field: str = Field(..., description="Column mapped to the x-axis/labels.")
    y_field: str = Field(..., description="Column mapped to the y-axis/values.")


class ChartResponse(BaseModel):
    """Response for the ``POST /chart`` endpoint."""

    answer: str = Field(..., description="Human-readable answer to the question.")
    table_data: list[dict[str, Any]] = Field(
        default_factory=list, description="Tabular result rows."
    )
    chart_type: Optional[ChartType] = Field(
        default=None, description="Resolved chart type, or null if not chartable."
    )
    chart_spec: Optional[dict[str, Any]] = Field(
        default=None, description="Plotly figure JSON, or null if not chartable."
    )
    execution_time_ms: float = Field(
        ..., ge=0, description="Pandas execution time in milliseconds."
    )
    total_time_ms: float = Field(
        ..., ge=0, description="End-to-end time including the LLM call."
    )
