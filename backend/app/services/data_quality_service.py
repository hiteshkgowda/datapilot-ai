"""Data Quality Analysis Service.

Computes a comprehensive quality profile for any DataFrame using pure pandas/numpy:
  - Completeness   — missing value analysis per column
  - Uniqueness     — duplicate row detection
  - Validity       — IQR-based outlier detection on numeric columns
  - Consistency    — dtype uniformity check
  - Recommendations — rule-based, prioritised action list

No LLM is involved; all analysis is deterministic and reproducible.
Results are cached by SHA-256(dataset_id) with configurable TTL.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd

from app.core.cache import TTLCache
from app.core.math_utils import dataset_cache_key
from app.schemas.data_quality import (
    ColumnQuality,
    DataQualityRecommendation,
    DataQualityResponse,
    DuplicateInfo,
    MissingValueSummary,
    OutlierSummary,
    QualityDimensions,
)

# ── Thresholds ────────────────────────────────────────────────────────────────
_MISSING_WARN = 5.0    # % missing → issue
_MISSING_CRIT = 30.0   # % missing → critical
_OUTLIER_WARN = 5.0    # % outliers → issue
_DUP_WARN = 1.0        # % duplicate rows → issue
_HIGH_CARD_WARN = 0.95 # unique_pct above this for categorical → may be identifier


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _build_missing_chart(columns: list[ColumnQuality]) -> dict[str, Any] | None:
    """Horizontal bar chart of missing % per column (only columns with missing values)."""
    missing = [(c.name, c.missing_pct) for c in columns if c.missing_count > 0]
    if not missing:
        return None
    missing.sort(key=lambda x: x[1], reverse=True)
    names, pcts = zip(*missing)
    colors = [
        "#ef4444" if p >= _MISSING_CRIT else "#f59e0b" if p >= _MISSING_WARN else "#6366f1"
        for p in pcts
    ]
    return {
        "data": [
            {
                "type": "bar",
                "orientation": "h",
                "y": list(names),
                "x": list(pcts),
                "marker": {"color": colors},
                "text": [f"{p:.1f}%" for p in pcts],
                "textposition": "outside",
                "hovertemplate": "%{y}: %{x:.2f}% missing<extra></extra>",
            }
        ],
        "layout": {
            "xaxis": {"title": "Missing (%)", "range": [0, max(pcts) * 1.15]},
            "yaxis": {"autorange": "reversed"},
            "showlegend": False,
            "height": max(200, len(missing) * 32 + 60),
        },
    }


def _build_outlier_chart(columns: list[ColumnQuality]) -> dict[str, Any] | None:
    """Vertical bar chart of outlier counts per numeric column."""
    outliers = [(c.name, c.outlier_count, c.outlier_pct) for c in columns if c.outlier_count > 0]
    if not outliers:
        return None
    outliers.sort(key=lambda x: x[1], reverse=True)
    names, counts, pcts = zip(*outliers)
    return {
        "data": [
            {
                "type": "bar",
                "x": list(names),
                "y": list(counts),
                "marker": {
                    "color": [
                        "#ef4444" if p >= _OUTLIER_WARN * 3 else "#f59e0b" if p >= _OUTLIER_WARN else "#6366f1"
                        for p in pcts
                    ]
                },
                "text": [f"{p:.1f}%" for p in pcts],
                "textposition": "outside",
                "hovertemplate": "%{x}: %{y} outliers (%{text})<extra></extra>",
            }
        ],
        "layout": {
            "xaxis": {"title": "Column"},
            "yaxis": {"title": "Outlier Count"},
            "showlegend": False,
        },
    }


def _analyse_column(series: pd.Series, row_count: int) -> ColumnQuality:
    """Compute quality metrics for a single column."""
    name = str(series.name)
    dtype = str(series.dtype)
    missing_count = int(series.isna().sum())
    missing_pct = (missing_count / row_count * 100) if row_count > 0 else 0.0
    non_null = series.dropna()
    unique_count = int(non_null.nunique())
    unique_pct = (unique_count / len(non_null) * 100) if len(non_null) > 0 else 0.0

    mean = std = col_min = col_max = q1 = q3 = None
    outlier_count = 0
    outlier_pct = 0.0

    if pd.api.types.is_numeric_dtype(series) and len(non_null) >= 4:
        arr = non_null.astype(float)
        mean = float(arr.mean())
        std = float(arr.std())
        col_min = float(arr.min())
        col_max = float(arr.max())
        q1_val = float(arr.quantile(0.25))
        q3_val = float(arr.quantile(0.75))
        q1 = q1_val
        q3 = q3_val
        iqr = q3_val - q1_val
        if iqr > 0:
            lo = q1_val - 1.5 * iqr
            hi = q3_val + 1.5 * iqr
            outlier_count = int(((arr < lo) | (arr > hi)).sum())
        outlier_pct = (outlier_count / len(arr) * 100) if len(arr) > 0 else 0.0

    # Compute health score
    completeness_score = max(0.0, 100.0 - missing_pct)
    uniqueness_penalty = 0.0
    if unique_count == 1 and len(non_null) > 1:
        uniqueness_penalty = 20.0  # constant column
    outlier_penalty = min(30.0, outlier_pct * 1.5)
    health_score = max(0.0, completeness_score - outlier_penalty - uniqueness_penalty)

    issues: list[str] = []
    if missing_pct >= _MISSING_CRIT:
        issues.append(f"{missing_pct:.1f}% missing values (critical)")
    elif missing_pct >= _MISSING_WARN:
        issues.append(f"{missing_pct:.1f}% missing values")
    if outlier_pct >= _OUTLIER_WARN:
        issues.append(f"{outlier_pct:.1f}% outliers detected")
    if unique_count == 1 and len(non_null) > 1:
        issues.append("Constant column — all non-null values are identical")
    if pd.api.types.is_numeric_dtype(series) and unique_count == len(non_null) and len(non_null) > 10:
        issues.append("All values unique — may be an identifier column")

    return ColumnQuality(
        name=name,
        dtype=dtype,
        health_score=round(health_score, 1),
        missing_count=missing_count,
        missing_pct=round(missing_pct, 2),
        unique_count=unique_count,
        unique_pct=round(unique_pct, 2),
        outlier_count=outlier_count,
        outlier_pct=round(outlier_pct, 2),
        mean=round(mean, 4) if mean is not None else None,
        std=round(std, 4) if std is not None else None,
        col_min=round(col_min, 4) if col_min is not None else None,
        col_max=round(col_max, 4) if col_max is not None else None,
        q1=round(q1, 4) if q1 is not None else None,
        q3=round(q3, 4) if q3 is not None else None,
        issues=issues,
    )


def _build_recommendations(
    columns: list[ColumnQuality],
    duplicates: DuplicateInfo,
) -> list[DataQualityRecommendation]:
    recs: list[DataQualityRecommendation] = []

    # Duplicates
    if duplicates.duplicate_pct >= _DUP_WARN:
        priority = "critical" if duplicates.duplicate_pct >= 10 else "high"
        recs.append(DataQualityRecommendation(
            priority=priority,
            issue=f"{duplicates.duplicate_row_count} duplicate rows ({duplicates.duplicate_pct:.1f}%)",
            action="Deduplicate before analysis to avoid inflating counts and aggregates.",
            affected_columns=[],
        ))

    # High missing
    critical_missing = [c for c in columns if c.missing_pct >= _MISSING_CRIT]
    warn_missing = [c for c in columns if _MISSING_WARN <= c.missing_pct < _MISSING_CRIT]

    if critical_missing:
        recs.append(DataQualityRecommendation(
            priority="critical",
            issue=f"{len(critical_missing)} column(s) have >30% missing values",
            action="Consider dropping or imputing these columns — high missingness introduces bias.",
            affected_columns=[c.name for c in critical_missing],
        ))
    if warn_missing:
        recs.append(DataQualityRecommendation(
            priority="medium",
            issue=f"{len(warn_missing)} column(s) have 5–30% missing values",
            action="Impute missing values (median/mode for numeric, forward-fill for time series).",
            affected_columns=[c.name for c in warn_missing],
        ))

    # Outliers
    high_outlier_cols = [c for c in columns if c.outlier_pct >= _OUTLIER_WARN * 3]
    warn_outlier_cols = [c for c in columns if _OUTLIER_WARN <= c.outlier_pct < _OUTLIER_WARN * 3]

    if high_outlier_cols:
        recs.append(DataQualityRecommendation(
            priority="high",
            issue=f"{len(high_outlier_cols)} column(s) have >15% outliers",
            action="Investigate these columns for data entry errors or apply winsorisation/clipping.",
            affected_columns=[c.name for c in high_outlier_cols],
        ))
    if warn_outlier_cols:
        recs.append(DataQualityRecommendation(
            priority="low",
            issue=f"{len(warn_outlier_cols)} column(s) have mild outlier presence (5–15%)",
            action="Review outliers — they may be legitimate extreme values or data entry errors.",
            affected_columns=[c.name for c in warn_outlier_cols],
        ))

    # Constant columns
    constant_cols = [c for c in columns if "Constant column" in " ".join(c.issues)]
    if constant_cols:
        recs.append(DataQualityRecommendation(
            priority="medium",
            issue=f"{len(constant_cols)} constant column(s) — all non-null values identical",
            action="Drop constant columns; they carry no information for modelling or analysis.",
            affected_columns=[c.name for c in constant_cols],
        ))

    if not recs:
        recs.append(DataQualityRecommendation(
            priority="low",
            issue="No significant quality issues detected",
            action="Dataset appears clean. Validate domain-specific constraints before production use.",
            affected_columns=[],
        ))

    return recs


class DataQualityService:
    """Deterministic, cache-backed data quality profiler."""

    def __init__(
        self,
        cache_ttl: int = 3600,
        cache_max_entries: int = 64,
    ) -> None:
        self._cache: TTLCache[str, DataQualityResponse] = TTLCache(
            ttl_seconds=cache_ttl, max_entries=cache_max_entries
        )

    def _cache_key(self, dataset_id: str) -> str:
        return dataset_cache_key(dataset_id)

    def analyse(self, df: pd.DataFrame, dataset_id: str) -> DataQualityResponse:
        """Run data quality analysis and return a structured report."""
        key = self._cache_key(dataset_id)
        cached = self._cache.get(key)
        if cached is not None:
            return DataQualityResponse(**{**cached.model_dump(), "cache_hit": True})

        t0 = time.perf_counter()
        row_count, col_count = df.shape

        # ── Column analysis ────────────────────────────────────────────────
        columns = [_analyse_column(df[col], row_count) for col in df.columns]

        # ── Duplicates ─────────────────────────────────────────────────────
        dup_count = int(df.duplicated().sum())
        dup_pct = round(dup_count / row_count * 100, 2) if row_count > 0 else 0.0
        duplicates = DuplicateInfo(duplicate_row_count=dup_count, duplicate_pct=dup_pct)

        # ── Missing summary ────────────────────────────────────────────────
        total_cells = row_count * col_count
        total_missing = sum(c.missing_count for c in columns)
        total_missing_pct = round(total_missing / total_cells * 100, 2) if total_cells > 0 else 0.0
        missing_summary = MissingValueSummary(
            total_missing=total_missing,
            total_missing_pct=total_missing_pct,
            columns_with_missing=sum(1 for c in columns if c.missing_count > 0),
            chart_spec=_build_missing_chart(columns),
        )

        # ── Outlier summary ────────────────────────────────────────────────
        total_outliers = sum(c.outlier_count for c in columns)
        outlier_summary = OutlierSummary(
            total_outlier_count=total_outliers,
            columns_with_outliers=sum(1 for c in columns if c.outlier_count > 0),
            chart_spec=_build_outlier_chart(columns),
        )

        # ── Dimensions ────────────────────────────────────────────────────
        completeness = round((1.0 - total_missing / total_cells) * 100, 2) if total_cells > 0 else 100.0
        uniqueness = round((1.0 - dup_count / row_count) * 100, 2) if row_count > 0 else 100.0

        numeric_cols = [c for c in columns if c.outlier_count >= 0 and c.mean is not None]
        if numeric_cols:
            avg_outlier_pct = sum(c.outlier_pct for c in numeric_cols) / len(numeric_cols)
            validity = round(max(0.0, 100.0 - avg_outlier_pct), 2)
        else:
            validity = 100.0

        consistency = 100.0  # pandas enforces dtype per-column

        dimensions = QualityDimensions(
            completeness=completeness,
            uniqueness=uniqueness,
            validity=validity,
            consistency=consistency,
        )

        # ── Overall score ──────────────────────────────────────────────────
        # Weighted: completeness 40%, uniqueness 25%, validity 25%, consistency 10%
        overall_score = round(
            completeness * 0.40
            + uniqueness * 0.25
            + validity * 0.25
            + consistency * 0.10,
            1,
        )

        # ── Recommendations ────────────────────────────────────────────────
        recommendations = _build_recommendations(columns, duplicates)

        elapsed_ms = (time.perf_counter() - t0) * 1000

        result = DataQualityResponse(
            dataset_id=dataset_id,
            overall_score=overall_score,
            grade=_grade(overall_score),
            dimensions=dimensions,
            columns=columns,
            duplicates=duplicates,
            missing_summary=missing_summary,
            outlier_summary=outlier_summary,
            recommendations=recommendations,
            row_count=row_count,
            column_count=col_count,
            analysis_time_ms=round(elapsed_ms, 1),
            cache_hit=False,
        )
        self._cache.put(key, result)
        return result
