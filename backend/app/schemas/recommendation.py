"""Pydantic schemas for the Recommendation Engine API.

Data flow:
    RecommendationRequest
        (anomalies: AnomalyResponse, insights: InsightResponse, forecast: ForecastResponse)
        → RecommendationRuleEngine    (deterministic, zero LLM)
            → list[Recommendation]
        → RecommendationAgent         (LLM enhancement, optional)
        → RecommendationResponse
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.anomaly import AnomalyResponse
from app.schemas.insight import InsightResponse


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class Recommendation(BaseModel):
    """A single actionable recommendation grounded in observed data."""

    priority: str = Field(
        ...,
        description="'critical', 'high', 'medium', or 'low'.",
    )
    action: str = Field(
        ...,
        description="Imperative sentence describing the specific action to take.",
    )
    reason: str = Field(
        ...,
        description="Data-grounded rationale referencing specific numbers from the analysis.",
    )
    expected_impact: str = Field(
        ...,
        description=(
            "Quantified expected outcome derived from the observed data — "
            "never invented numbers."
        ),
    )
    category: str = Field(
        ...,
        description=(
            "Business domain: 'revenue', 'operations', 'inventory', "
            "'marketing', 'data_quality', 'monitoring', or 'general'."
        ),
    )
    source: str = Field(
        ...,
        description="Signal source: 'anomaly', 'insight', 'forecast', 'cross_signal', or 'rule'.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in this recommendation based on data support strength.",
    )
    data_points: list[str] = Field(
        default_factory=list,
        description="Specific data facts (column names, values, percentages) supporting this recommendation.",
    )


class RecommendationResponse(BaseModel):
    """Full recommendation report returned by POST /api/v1/recommendations."""

    recommendations: list[Recommendation] = Field(
        description="Ranked recommendations, highest priority first."
    )
    summary: str = Field(
        description="One-paragraph synthesis of the top actions and their data rationale."
    )
    total_count: int
    generation_time_ms: float = Field(default=0.0)
    cache_hit: bool = Field(default=False)
    llm_enhanced: bool = Field(
        default=False,
        description="True when an LLM successfully enhanced the rule-based output.",
    )


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------


class RecommendationRequest(BaseModel):
    """Request body for POST /api/v1/recommendations.

    Accepts the outputs of any combination of previous API calls
    (anomaly detection, insight generation, forecasting, or raw query results)
    and synthesises them into prioritised, actionable recommendations.

    At least one of ``anomalies``, ``insights``, or ``forecast`` must be provided.
    """

    dataset_id: str

    # Outputs from upstream APIs — all optional but at least one required.
    anomalies: Optional[AnomalyResponse] = Field(
        default=None,
        description="AnomalyResponse from POST /api/v1/anomalies.",
    )
    insights: Optional[InsightResponse] = Field(
        default=None,
        description="InsightResponse from POST /api/v1/insights/generate.",
    )
    forecast: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "ForecastResponse from POST /api/v1/forecast — "
            "accepted as a raw dict to avoid coupling to forecast schema version."
        ),
    )
    query_results: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Raw table_data rows from POST /api/v1/query or /api/v1/chart.",
    )

    # Optional caller context.
    context: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Free-text business context to inform recommendations (e.g. 'Q4 planning cycle').",
    )

    # Controls.
    max_recommendations: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of recommendations to return, ranked by priority.",
    )
    llm_enhance: bool = Field(
        default=True,
        description=(
            "When True, use LLM to improve recommendation language. "
            "Rule-based output is always returned if LLM fails or is unavailable."
        ),
    )
