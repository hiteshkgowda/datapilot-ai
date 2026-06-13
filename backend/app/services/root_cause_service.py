"""Root Cause Analysis: statistical engine and orchestration service.

RCAEngine   — pure pandas/numpy; zero LLM; deterministic decomposition.
RootCauseService — orchestrates engine + agent + TTL cache.

Algorithm overview
------------------
1. Detect the metric column (from question keywords or schema heuristics).
2. Detect the period column (date/month/quarter/year column or row-based split).
3. Resolve two periods: current (more recent) vs previous (baseline).
4. Compute period totals and overall change.
5. For each dimension column (region, product, segment, …):
   a. Group by period × dimension → per-cell aggregates.
   b. Compute (current − previous) for each cell.
   c. Contribution % = cell_change / |total_change| × 100.
6. Rank all (dimension, value) pairs by |contribution %| descending.
7. Build RCAFindings — the sole input to the LLM reasoning layer.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.core.cache import TTLCache
from app.schemas.root_cause import (
    ContributionFactor,
    PeriodSummary,
    RCAFindings,
    RootCauseResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Column-name keywords → metric heuristic (ordered by priority).
_METRIC_KEYWORDS: tuple[str, ...] = (
    "revenue", "sales", "income", "profit", "earnings",
    "churn", "cancellation", "orders", "conversions",
    "users", "customers", "subscribers", "leads",
    "cost", "spend", "expense", "loss",
    "volume", "amount", "total", "value", "count",
)

# Column-name keywords → time / period heuristic.
_PERIOD_KEYWORDS: tuple[str, ...] = (
    "date", "month", "period", "year", "quarter",
    "week", "time", "day", "created_at", "timestamp",
)

# Column-name keywords → dimension heuristic.
_DIMENSION_KEYWORDS: tuple[str, ...] = (
    "region", "country", "state", "city", "territory",
    "product", "item", "sku", "category", "subcategory",
    "segment", "tier", "type", "class",
    "channel", "source", "medium", "campaign",
    "department", "team", "division", "unit",
    "customer", "client", "account", "partner",
    "gender", "age", "cohort",
)

# Maximum unique values in a dimension before it's considered too high-cardinality.
_MAX_DIM_CARDINALITY = 50
# Maximum number of dimension columns to decompose (performance guard).
_MAX_DIMENSIONS = 6
# Minimum rows needed in each split for meaningful analysis.
_MIN_PERIOD_ROWS = 1

# ---------------------------------------------------------------------------
# Statistical engine
# ---------------------------------------------------------------------------


@dataclass
class _DetectedContext:
    metric_col: str
    period_col: Optional[str]
    current_label: Optional[str]
    previous_label: Optional[str]
    period_split_method: str


class RCAEngine:
    """Deterministic root-cause decomposition.

    All computations use fixed pandas operations.  No eval, no exec, no LLM.
    """

    def __init__(
        self,
        max_dim_cardinality: int = _MAX_DIM_CARDINALITY,
        max_dimensions: int = _MAX_DIMENSIONS,
        top_contributors: int = 20,
    ) -> None:
        self._max_card = max_dim_cardinality
        self._max_dims = max_dimensions
        self._top_n = top_contributors

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def analyze(
        self,
        df: pd.DataFrame,
        question: str,
        metric_col: Optional[str] = None,
        period_col: Optional[str] = None,
        current_period: Optional[str] = None,
        previous_period: Optional[str] = None,
    ) -> RCAFindings:
        """Run the full RCA decomposition; return structured findings."""
        if df.empty:
            return self._empty_findings("Dataset is empty.")

        ctx = self._detect_context(
            df, question, metric_col, period_col, current_period, previous_period
        )

        current_df, previous_df = self._split_periods(df, ctx)
        if current_df.empty or previous_df.empty:
            return self._empty_findings(
                "Could not split the dataset into two comparable periods."
            )

        curr_total = self._safe_sum(current_df[ctx.metric_col])
        prev_total = self._safe_sum(previous_df[ctx.metric_col])
        total_change = curr_total - prev_total

        if prev_total == 0:
            total_pct_change = 0.0
        else:
            total_pct_change = (total_change / abs(prev_total)) * 100.0

        if abs(total_change) < 1e-9:
            direction = "flat"
        elif total_change < 0:
            direction = "decline"
        else:
            direction = "growth"

        dim_cols = self._detect_dimensions(df, ctx.metric_col, ctx.period_col)
        contributions: list[ContributionFactor] = []

        for dim in dim_cols:
            dim_contribs = self._decompose_dimension(
                current_df, previous_df, dim, ctx.metric_col, total_change
            )
            contributions.extend(dim_contribs)

        # Sort by |contribution_pct| descending; assign global ranks.
        contributions.sort(key=lambda c: abs(c.contribution_pct), reverse=True)
        ranked: list[ContributionFactor] = []
        for rank, c in enumerate(contributions[: self._top_n], start=1):
            ranked.append(c.model_copy(update={"rank": rank}))

        has_offsets = any(
            (c.absolute_change > 0) != (total_change > 0) and abs(c.absolute_change) > 1e-9
            for c in ranked
        )

        return RCAFindings(
            metric_column=ctx.metric_col,
            period_column=ctx.period_col,
            current_period=PeriodSummary(
                label=str(ctx.current_label) if ctx.current_label else "current",
                total=round(curr_total, 4),
            ),
            previous_period=PeriodSummary(
                label=str(ctx.previous_label) if ctx.previous_label else "previous",
                total=round(prev_total, 4),
            ),
            total_absolute_change=round(total_change, 4),
            total_pct_change=round(total_pct_change, 4),
            direction=direction,
            dimension_columns=dim_cols,
            contributions=ranked,
            has_offsets=has_offsets,
            row_count=len(df),
            period_split_method=ctx.period_split_method,
        )

    # ------------------------------------------------------------------ #
    # Context detection
    # ------------------------------------------------------------------ #

    def _detect_context(
        self,
        df: pd.DataFrame,
        question: str,
        metric_col: Optional[str],
        period_col: Optional[str],
        current_period: Optional[str],
        previous_period: Optional[str],
    ) -> _DetectedContext:
        detected_metric = metric_col or self._detect_metric(df, question)
        detected_period, method = self._detect_period_col(df, period_col)

        # Explicit period labels override auto-detection.
        if current_period and previous_period:
            method = "explicit"
            return _DetectedContext(
                metric_col=detected_metric,
                period_col=detected_period,
                current_label=current_period,
                previous_label=previous_period,
                period_split_method=method,
            )

        # Auto-detect period labels from the column.
        curr_label, prev_label = self._detect_period_labels(
            df, detected_period, method
        )
        return _DetectedContext(
            metric_col=detected_metric,
            period_col=detected_period,
            current_label=curr_label,
            previous_label=prev_label,
            period_split_method=method,
        )

    def _detect_metric(self, df: pd.DataFrame, question: str) -> str:
        """Return the best matching metric column."""
        q_lower = question.lower()
        numeric_cols = [
            c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
        ]
        if not numeric_cols:
            raise ValueError("No numeric columns found in the dataset.")

        # Score columns: +3 for keyword match in both question and column, +2 for column only.
        scores: dict[str, int] = {c: 0 for c in numeric_cols}
        for kw in _METRIC_KEYWORDS:
            kw_in_question = kw in q_lower
            for col in numeric_cols:
                col_lower = col.lower().replace("_", " ")
                col_match = kw in col_lower
                if kw_in_question and col_match:
                    scores[col] += 3
                elif col_match:
                    scores[col] += 2

        best = max(scores, key=lambda c: (scores[c], -_is_id_col(c)))
        return best

    def _detect_period_col(
        self, df: pd.DataFrame, explicit: Optional[str]
    ) -> tuple[Optional[str], str]:
        """Return (period_column, split_method)."""
        if explicit and explicit in df.columns:
            return explicit, "explicit"

        # 1. Prefer datetime-typed columns.
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                return col, "date_column"

        # 2. Try to parse object columns that look like dates.
        for col in df.select_dtypes(include=["object", "string"]).columns:
            sample = df[col].dropna().astype(str).head(10)
            if _looks_like_dates(sample):
                return col, "date_column"

        # 3. Look for period-keyword column names (month, quarter, year …).
        for kw in _PERIOD_KEYWORDS:
            for col in df.columns:
                if kw in col.lower():
                    return col, "period_column"

        # 4. Fallback: split by row halves.
        return None, "row_halves"

    def _detect_period_labels(
        self,
        df: pd.DataFrame,
        period_col: Optional[str],
        method: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Return (current_label, previous_label) for the detected period column."""
        if method == "row_halves" or period_col is None:
            return None, None

        # Coerce to string for uniform sorting.
        col_series = df[period_col].dropna().astype(str)

        # Try numeric sort (e.g. years: 2023, 2024).
        try:
            unique_sorted = sorted(col_series.unique(), key=lambda x: float(x))
        except (ValueError, TypeError):
            unique_sorted = sorted(col_series.unique())

        if len(unique_sorted) < 2:
            return None, None

        return str(unique_sorted[-1]), str(unique_sorted[-2])

    # ------------------------------------------------------------------ #
    # Period splitting
    # ------------------------------------------------------------------ #

    def _split_periods(
        self, df: pd.DataFrame, ctx: _DetectedContext
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (current_df, previous_df)."""
        if ctx.period_col is None:
            # Row-halves split.
            mid = max(len(df) // 2, 1)
            return df.iloc[mid:].copy(), df.iloc[:mid].copy()

        col_series = df[ctx.period_col].astype(str)

        if ctx.current_label and ctx.previous_label:
            current_mask = col_series == str(ctx.current_label)
            previous_mask = col_series == str(ctx.previous_label)
        else:
            # Auto-detected labels.
            curr_lbl, prev_lbl = self._detect_period_labels(
                df, ctx.period_col, ctx.period_split_method
            )
            if curr_lbl is None:
                mid = max(len(df) // 2, 1)
                return df.iloc[mid:].copy(), df.iloc[:mid].copy()
            current_mask = col_series == curr_lbl
            previous_mask = col_series == prev_lbl

        return df[current_mask].copy(), df[previous_mask].copy()

    # ------------------------------------------------------------------ #
    # Dimension detection
    # ------------------------------------------------------------------ #

    def _detect_dimensions(
        self,
        df: pd.DataFrame,
        metric_col: str,
        period_col: Optional[str],
    ) -> list[str]:
        """Return candidate dimension columns, ordered by keyword priority."""
        exclude = {metric_col}
        if period_col:
            exclude.add(period_col)

        numeric_cols = {
            c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
        }

        # Candidate = categorical (non-numeric) and not excluded.
        candidates = [
            c for c in df.columns
            if c not in exclude and c not in numeric_cols
        ]

        # Filter out high-cardinality columns.
        candidates = [
            c for c in candidates
            if df[c].nunique() <= self._max_card
        ]

        if not candidates:
            return []

        # Score by keyword match.
        def _score(col: str) -> int:
            col_lower = col.lower().replace("_", " ")
            for i, kw in enumerate(_DIMENSION_KEYWORDS):
                if kw in col_lower:
                    return len(_DIMENSION_KEYWORDS) - i  # higher = earlier keyword
            return 0

        candidates.sort(key=_score, reverse=True)
        return candidates[: self._max_dims]

    # ------------------------------------------------------------------ #
    # Contribution decomposition
    # ------------------------------------------------------------------ #

    def _decompose_dimension(
        self,
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        dim_col: str,
        metric_col: str,
        total_change: float,
    ) -> list[ContributionFactor]:
        """Compute per-value contribution for one dimension column."""
        if dim_col not in current_df.columns or dim_col not in previous_df.columns:
            return []

        curr_agg = current_df.groupby(dim_col)[metric_col].sum().rename("curr")
        prev_agg = previous_df.groupby(dim_col)[metric_col].sum().rename("prev")

        combined = (
            pd.concat([curr_agg, prev_agg], axis=1)
            .fillna(0.0)
            .reset_index()
        )
        combined.columns = [dim_col, "curr", "prev"]
        combined["change"] = combined["curr"] - combined["prev"]

        if abs(total_change) < 1e-9:
            combined["contribution_pct"] = 0.0
        else:
            combined["contribution_pct"] = (combined["change"] / abs(total_change)) * 100.0

        # pct change within cell
        def _cell_pct(row: Any) -> float:
            if row["prev"] == 0:
                return 0.0
            return float((row["change"] / abs(row["prev"])) * 100.0)

        combined["pct_change"] = combined.apply(_cell_pct, axis=1)

        factors: list[ContributionFactor] = []
        for _, row in combined.iterrows():
            curr_v = _safe_float(row["curr"])
            prev_v = _safe_float(row["prev"])
            abs_ch = _safe_float(row["change"])
            pct_ch = _safe_float(row["pct_change"])
            contr = _safe_float(row["contribution_pct"])
            if curr_v is None or prev_v is None or abs_ch is None:
                continue
            factors.append(
                ContributionFactor(
                    dimension=dim_col,
                    value=str(row[dim_col]),
                    current_value=curr_v,
                    previous_value=prev_v,
                    absolute_change=abs_ch,
                    percentage_change=pct_ch or 0.0,
                    contribution_pct=contr or 0.0,
                    rank=0,  # assigned globally by caller
                )
            )
        return factors

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _safe_sum(series: "pd.Series[Any]") -> float:
        total = pd.to_numeric(series, errors="coerce").sum()
        if pd.isna(total):
            return 0.0
        return float(total)

    def _empty_findings(self, reason: str) -> RCAFindings:
        return RCAFindings(
            metric_column=reason,
            period_column=None,
            current_period=PeriodSummary(label="current", total=0.0),
            previous_period=PeriodSummary(label="previous", total=0.0),
            total_absolute_change=0.0,
            total_pct_change=0.0,
            direction="flat",
            dimension_columns=[],
            contributions=[],
            has_offsets=False,
            row_count=0,
            period_split_method="none",
        )


# ---------------------------------------------------------------------------
# Orchestration service
# ---------------------------------------------------------------------------


class RootCauseService:
    """Coordinate RCAEngine, RootCauseAgent, and TTL response cache."""

    def __init__(
        self,
        root_cause_agent: Any,  # RootCauseAgent — avoids circular import
        cache_ttl: float = 300.0,
        cache_max_entries: int = 30,
    ) -> None:
        self._agent = root_cause_agent
        self._engine = RCAEngine()
        self._cache: TTLCache[str, RootCauseResponse] = TTLCache(
            ttl_seconds=cache_ttl,
            max_entries=cache_max_entries,
        )

    async def analyze(
        self,
        df: pd.DataFrame,
        request_dict: dict[str, Any],
    ) -> RootCauseResponse:
        """Full RCA pipeline: stats → LLM → cache."""
        dataset_id = request_dict["dataset_id"]
        question = request_dict["question"]

        cache_key = _cache_key(dataset_id, question, request_dict)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(update={"cache_hit": True})

        start = time.perf_counter()

        try:
            findings = self._engine.analyze(
                df=df,
                question=question,
                metric_col=request_dict.get("metric_column"),
                period_col=request_dict.get("period_column"),
                current_period=request_dict.get("current_period"),
                previous_period=request_dict.get("previous_period"),
            )
            response = await self._agent.generate(findings=findings, question=question)
        except Exception as exc:
            logger.error("RootCauseService: analysis failed: %s", exc)
            response = _error_response(str(exc))

        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        result = response.model_copy(
            update={"cache_hit": False, "analysis_time_ms": elapsed_ms}
        )
        self._cache.put(cache_key, result)
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cache_key(dataset_id: str, question: str, params: dict[str, Any]) -> str:
    parts = {
        "dataset_id": dataset_id,
        "question": question.strip().lower(),
        "metric_column": params.get("metric_column"),
        "period_column": params.get("period_column"),
        "current_period": params.get("current_period"),
        "previous_period": params.get("previous_period"),
    }
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return 0.0
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _is_id_col(col: str) -> bool:
    """Return True if the column looks like an ID/index column (lower score for metrics)."""
    lower = col.lower()
    return any(kw in lower for kw in ("id", "index", "idx", "key", "code", "num"))


def _looks_like_dates(sample: "pd.Series[Any]") -> bool:
    """Heuristic: try to parse a sample of values as dates."""
    success = 0
    for val in sample:
        try:
            pd.to_datetime(str(val), errors="raise")
            success += 1
        except Exception:
            pass
    return success >= len(sample) * 0.8


def _error_response(message: str) -> RootCauseResponse:
    return RootCauseResponse(
        problem=f"Analysis could not be completed: {message}",
        root_causes=[],
        contribution_analysis=[],
        recommendations=[],
    )
