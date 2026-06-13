"""Schemas for the AI Insight Generation Engine.

The pipeline is:
    table_data (list[dict]) →  InsightStatEngine  →  StatisticalFindings
                             →  InsightAgent (LLM)  →  InsightResponse

StatisticalFindings is passed verbatim to the LLM so it can only reference
facts that were computed deterministically — preventing hallucination.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Internal statistical fact types (engine → agent)
# ---------------------------------------------------------------------------


class ColumnStats(BaseModel):
    """Descriptive statistics for one numeric column."""

    column: str
    count: int
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None
    null_count: int = 0
    coefficient_of_variation: Optional[float] = None


class TrendInfo(BaseModel):
    """Linear trend for one column across the row sequence."""

    column: str
    direction: str  # "increasing" | "decreasing" | "flat"
    slope: float
    first_value: Optional[float] = None
    last_value: Optional[float] = None
    change_pct: Optional[float] = None


class CorrelationInfo(BaseModel):
    """Pearson correlation between two numeric columns."""

    column_a: str
    column_b: str
    coefficient: float
    strength: str  # "strong_positive" | "moderate_positive" | "moderate_negative" | "strong_negative"


class PerformerEntry(BaseModel):
    """A single top-N or bottom-N entry."""

    label: str
    value: float
    metric: str
    rank: int


class GrowthPattern(BaseModel):
    """Period-over-period growth characteristics for one column."""

    column: str
    pattern: str  # "accelerating" | "decelerating" | "stable" | "volatile"
    avg_period_change_pct: Optional[float] = None
    max_period_change_pct: Optional[float] = None
    min_period_change_pct: Optional[float] = None


class StatisticalFindings(BaseModel):
    """All deterministic facts about the dataset.

    This object is serialised to JSON and injected verbatim into the LLM
    prompt.  The LLM is instructed — and architecturally constrained — to
    produce its output solely from these facts.
    """

    row_count: int
    column_count: int
    numeric_columns: list[str]
    categorical_columns: list[str]
    column_stats: list[ColumnStats]
    top_performers: list[PerformerEntry]
    underperformers: list[PerformerEntry]
    trends: list[TrendInfo]
    correlations: list[CorrelationInfo]
    growth_patterns: list[GrowthPattern]


# ---------------------------------------------------------------------------
# Public API schemas
# ---------------------------------------------------------------------------


class InsightRequest(BaseModel):
    """Request body for POST /api/v1/insights/generate."""

    dataset_id: str = Field(..., min_length=1, description="Dataset identifier.")
    question: str = Field(
        ..., min_length=1, description="The original question the user asked."
    )
    table_data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rows from the query result (list of dicts). "
        "If empty the response will explain no data is available.",
    )


class InsightResponse(BaseModel):
    """AI-generated insight output.

    Matches the required JSON contract:
        {
          "summary": "",
          "key_insights": [],
          "trends": [],
          "top_performers": [],
          "underperformers": [],
          "recommendations": []
        }
    """

    summary: str = Field(..., description="One-paragraph summary of the dataset and its key findings.")
    key_insights: list[str] = Field(default_factory=list, description="Top 3–5 key findings with specific numbers.")
    trends: list[str] = Field(default_factory=list, description="Detected directional trends.")
    top_performers: list[dict[str, Any]] = Field(default_factory=list)
    underperformers: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list, description="Actionable recommendations based only on the data.")

    # Metadata (not part of the contractual JSON structure above, extras for the API)
    cache_hit: bool = Field(default=False, description="True when this response was served from cache.")
    generation_time_ms: float = Field(default=0.0, description="Wall-clock time to generate insights.")
