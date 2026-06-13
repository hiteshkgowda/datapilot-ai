"""Schemas for the Root Cause Analysis (RCA) Agent.

Pipeline:
    RootCauseRequest  →  RCAEngine  →  RCAFindings  →  RootCauseAgent  →  RootCauseResponse

RCAFindings is passed verbatim as JSON to the LLM prompt.  The agent is
structurally constrained to produce output only from those facts.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class RootCauseRequest(BaseModel):
    """POST /api/v1/root-cause request body."""

    dataset_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1,
        description="E.g. 'Why did revenue drop?' or 'Why is churn increasing?'")

    # Optional overrides — auto-detected from data when omitted.
    metric_column: Optional[str] = Field(
        default=None,
        description="Column to analyse (e.g. 'revenue').  Auto-detected when not set.",
    )
    period_column: Optional[str] = Field(
        default=None,
        description="Date/period column for time-slicing.  Auto-detected when not set.",
    )
    current_period: Optional[str] = Field(
        default=None,
        description="The more recent period label (e.g. '2024-02').  "
        "Must pair with previous_period.",
    )
    previous_period: Optional[str] = Field(
        default=None,
        description="The baseline period label (e.g. '2024-01').  "
        "Must pair with current_period.",
    )


# ---------------------------------------------------------------------------
# Internal analytical findings (engine → agent)
# ---------------------------------------------------------------------------


class ContributionFactor(BaseModel):
    """Change contribution for one (dimension, value) pair."""

    dimension: str = Field(..., description="Column name, e.g. 'region'.")
    value: str = Field(..., description="Dimension value, e.g. 'West'.")
    current_value: float
    previous_value: float
    absolute_change: float
    percentage_change: float = Field(
        ..., description="Period-over-period % change for this cell."
    )
    contribution_pct: float = Field(
        ...,
        description=(
            "Fraction of the total metric change attributable to this cell. "
            "Can exceed ±100 % when offsetting movements are present."
        ),
    )
    rank: int = Field(..., description="Global rank by |contribution_pct|.")


class PeriodSummary(BaseModel):
    """Aggregate totals for one period."""

    label: str
    total: float


class RCAFindings(BaseModel):
    """All deterministic facts about the root cause analysis.

    Serialised to JSON and injected verbatim into the LLM prompt.
    The LLM may only reference facts contained here.
    """

    metric_column: str
    period_column: Optional[str]
    current_period: PeriodSummary
    previous_period: PeriodSummary
    total_absolute_change: float
    total_pct_change: float
    direction: str  # "decline" | "growth" | "flat"
    dimension_columns: list[str]
    contributions: list[ContributionFactor]  # pre-sorted by |contribution_pct|
    has_offsets: bool = Field(
        default=False,
        description="True when some dimensions moved opposite to the overall direction.",
    )
    row_count: int
    period_split_method: str  # "explicit" | "date_column" | "period_column" | "row_halves"


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class RootCause(BaseModel):
    """A single causal factor, ready for display."""

    dimension: str = Field(..., description="The column that was decomposed, e.g. 'region'.")
    value: str = Field(..., description="The specific value driving the change, e.g. 'West'.")
    impact_level: str = Field(..., description="'high' | 'medium' | 'low'")
    description: str = Field(..., description="One-sentence human-readable explanation.")
    contribution_pct: float
    rank: int


class RootCauseResponse(BaseModel):
    """Full root cause analysis result.

    Matches the contractual JSON structure:
        {
          "problem": "",
          "root_causes": [],
          "contribution_analysis": [],
          "recommendations": []
        }
    """

    problem: str = Field(
        ...,
        description="One-sentence problem statement with specific numbers, "
        "e.g. 'Revenue dropped 12% from 10,000 to 8,800.'",
    )
    root_causes: list[RootCause] = Field(
        default_factory=list,
        description="Top causal factors ranked by impact.",
    )
    contribution_analysis: list[ContributionFactor] = Field(
        default_factory=list,
        description="Full per-(dimension, value) decomposition.",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Actionable recommendations derived from the root causes.",
    )

    # Metadata
    metric_column: str = ""
    period_column: Optional[str] = None
    current_period: Optional[str] = None
    previous_period: Optional[str] = None
    current_total: float = 0.0
    previous_total: float = 0.0
    total_change_pct: float = 0.0
    analysis_time_ms: float = 0.0
    cache_hit: bool = False
