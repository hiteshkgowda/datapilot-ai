"""Pydantic schemas for the Data Quality API."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class DataQualityRequest(BaseModel):
    dataset_id: str = Field(..., description="ID of the dataset to profile.")


class ColumnQuality(BaseModel):
    name: str
    dtype: str
    health_score: float = Field(..., description="0–100 column health score.")
    missing_count: int
    missing_pct: float
    unique_count: int
    unique_pct: float
    outlier_count: int
    outlier_pct: float
    # Numeric summary (None for non-numeric)
    mean: Optional[float] = None
    std: Optional[float] = None
    col_min: Optional[float] = None
    col_max: Optional[float] = None
    q1: Optional[float] = None
    q3: Optional[float] = None
    issues: list[str] = Field(default_factory=list)


class DuplicateInfo(BaseModel):
    duplicate_row_count: int
    duplicate_pct: float


class MissingValueSummary(BaseModel):
    total_missing: int
    total_missing_pct: float
    columns_with_missing: int
    chart_spec: Optional[dict[str, Any]] = None


class OutlierSummary(BaseModel):
    total_outlier_count: int
    columns_with_outliers: int
    chart_spec: Optional[dict[str, Any]] = None


class QualityDimensions(BaseModel):
    completeness: float = Field(..., description="0–100. % of cells that are non-null.")
    uniqueness: float = Field(..., description="0–100. % of rows that are non-duplicate.")
    validity: float = Field(..., description="0–100. % of numeric values that are non-outlier.")
    consistency: float = Field(..., description="0–100. % of columns with no mixed-type issues.")


class DataQualityRecommendation(BaseModel):
    priority: Literal["critical", "high", "medium", "low"]
    issue: str
    action: str
    affected_columns: list[str] = Field(default_factory=list)


class DataQualityResponse(BaseModel):
    dataset_id: str
    overall_score: float = Field(..., description="0–100 composite quality score.")
    grade: Literal["A", "B", "C", "D", "F"]
    dimensions: QualityDimensions
    columns: list[ColumnQuality]
    duplicates: DuplicateInfo
    missing_summary: MissingValueSummary
    outlier_summary: OutlierSummary
    recommendations: list[DataQualityRecommendation]
    row_count: int
    column_count: int
    analysis_time_ms: float
    cache_hit: bool = False
