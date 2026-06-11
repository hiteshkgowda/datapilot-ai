"""Schemas for natural-language analytics (Phase 2).

The LLM is constrained to emit a :class:`QueryPlan` — a small, validated JSON
object drawn from a fixed allowlist of operations. No free-form code is ever
produced or executed; a deterministic pandas executor interprets the plan.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.chart import ChartType


class Operation(str, Enum):
    """The complete allowlist of supported analytics operations."""

    ROW_COUNT = "row_count"
    COLUMN_COUNT = "column_count"
    SUM = "sum"
    AVERAGE = "average"
    MAX = "max"
    MIN = "min"
    GROUPBY_SUM = "groupby_sum"
    GROUPBY_COUNT = "groupby_count"
    TOP_N = "top_n"
    XY_SELECT = "xy_select"


class QueryPlan(BaseModel):
    """A structured, validated analytics instruction produced by the LLM.

    Only fields relevant to the chosen ``operation`` are populated; the
    analytics service enforces which fields are required per operation.
    """

    model_config = {"extra": "forbid"}

    operation: Operation = Field(..., description="The analytics operation to run.")
    column: Optional[str] = Field(
        default=None,
        description="Target column for value/aggregation operations.",
    )
    group_by: Optional[str] = Field(
        default=None,
        description="Column to group by (groupby_sum, top_n).",
    )
    n: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of groups to return (top_n).",
    )
    x_column: Optional[str] = Field(
        default=None,
        description="Numeric column for the x-axis (xy_select).",
    )
    y_column: Optional[str] = Field(
        default=None,
        description="Numeric column for the y-axis (xy_select).",
    )
    chart_type: Optional[ChartType] = Field(
        default=None,
        description="Advisory chart-type recommendation (not binding).",
    )


class QueryRequest(BaseModel):
    """Incoming natural-language analytics request."""

    dataset_id: str = Field(..., min_length=1, description="Dataset identifier.")
    question: str = Field(
        ..., min_length=1, description="The natural-language question."
    )


class QueryResponse(BaseModel):
    """Full response for an analytics query."""

    answer: str = Field(..., description="Human-readable answer to the question.")
    query_plan: QueryPlan
    execution_time_ms: float = Field(
        ..., ge=0, description="Pandas execution time in milliseconds."
    )
    total_time_ms: float = Field(
        ...,
        ge=0,
        description="End-to-end time including the LLM call, in milliseconds.",
    )
