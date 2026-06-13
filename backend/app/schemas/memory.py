"""Pydantic schemas for the conversational memory system."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TurnType(str, Enum):
    QUERY = "query"
    CHART = "chart"
    FORECAST = "forecast"
    ANOMALY = "anomaly"
    INSIGHT = "insight"
    RECOMMENDATION = "recommendation"
    REPORT = "report"
    AGENT = "agent"


class ConversationTurn(BaseModel):
    """One recorded interaction within a session."""

    turn_id: str
    session_id: str
    user_sub: str
    created_at: str  # ISO 8601
    turn_type: TurnType
    dataset_id: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    table_data: Optional[list[dict[str, Any]]] = None
    chart_spec: Optional[dict[str, Any]] = None
    insights: Optional[dict[str, Any]] = None
    anomalies: Optional[dict[str, Any]] = None
    forecast: Optional[dict[str, Any]] = None
    recommendations: Optional[dict[str, Any]] = None
    metadata: Optional[dict[str, Any]] = None


class ConversationContext(BaseModel):
    """Full session context returned by GET /memory/context."""

    session_id: str
    turn_count: int
    turns: list[ConversationTurn]
    summary: str
    datasets_referenced: list[str] = Field(default_factory=list)
    last_dataset_id: Optional[str] = None


class MemoryClearResponse(BaseModel):
    """Returned by DELETE /memory/clear."""

    session_id: str
    turns_cleared: int
    message: str
