"""Statistical analysis engine and insight orchestration service.

Architecture
------------
InsightStatEngine   — pure pandas/numpy; no LLM; deterministic
InsightGenerationService — orchestrates engine + agent + TTL cache

The stat engine is the source-of-truth layer.  Everything it produces is
grounded in the actual table data.  The InsightAgent (LLM) receives only the
StatisticalFindings struct and is prohibited from inventing facts beyond it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.core.cache import TTLCache
from app.schemas.insight import (
    ColumnStats,
    CorrelationInfo,
    GrowthPattern,
    InsightResponse,
    PerformerEntry,
    StatisticalFindings,
    TrendInfo,
)

logger = logging.getLogger(__name__)

_MIN_ROWS_FOR_TREND = 3
_MIN_NUMERIC_COLS_FOR_CORR = 2


# ---------------------------------------------------------------------------
# Statistical engine
# ---------------------------------------------------------------------------


class InsightStatEngine:
    """Deterministic statistical analysis over tabular data.

    All operations use fixed pandas / numpy calls.  No dynamic code execution,
    no eval, no string-to-pandas evaluation anywhere.
    """

    def __init__(
        self,
        top_n: int = 3,
        correlation_threshold: float = 0.5,
        max_rows: int = 1000,
    ) -> None:
        self._top_n = top_n
        self._corr_threshold = correlation_threshold
        self._max_rows = max_rows

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #

    def analyze(self, table_data: list[dict[str, Any]]) -> StatisticalFindings:
        """Run all statistical analyses; return structured findings."""
        if not table_data:
            return StatisticalFindings(
                row_count=0,
                column_count=0,
                numeric_columns=[],
                categorical_columns=[],
                column_stats=[],
                top_performers=[],
                underperformers=[],
                trends=[],
                correlations=[],
                growth_patterns=[],
            )

        df = pd.DataFrame(table_data[: self._max_rows])

        # Attempt numeric coercion for object-typed columns (e.g. string "123").
        # errors="coerce" turns unparseable values to NaN; we keep the result only
        # when it produces at least one non-NaN value so we never demote a
        # genuinely categorical column to an all-NaN float series.
        for col in df.select_dtypes(include=["object", "string"]).columns:
            coerced = pd.to_numeric(df[col], errors="coerce")
            if coerced.notna().any():
                df[col] = coerced

        numeric_cols: list[str] = [
            c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
        ]
        categorical_cols: list[str] = [c for c in df.columns if c not in numeric_cols]
        label_col: Optional[str] = categorical_cols[0] if categorical_cols else None

        return StatisticalFindings(
            row_count=len(df),
            column_count=len(df.columns),
            numeric_columns=numeric_cols,
            categorical_columns=categorical_cols,
            column_stats=self._column_stats(df, numeric_cols),
            top_performers=self._top_performers(df, numeric_cols, label_col),
            underperformers=self._underperformers(df, numeric_cols, label_col),
            trends=self._detect_trends(df, numeric_cols),
            correlations=self._detect_correlations(df, numeric_cols),
            growth_patterns=self._growth_patterns(df, numeric_cols),
        )

    # ------------------------------------------------------------------ #
    # Column statistics
    # ------------------------------------------------------------------ #

    def _column_stats(
        self, df: pd.DataFrame, numeric_cols: list[str]
    ) -> list[ColumnStats]:
        stats: list[ColumnStats] = []
        for col in numeric_cols:
            series = df[col].dropna()
            null_count = int(df[col].isna().sum())

            if series.empty:
                stats.append(ColumnStats(column=col, count=0, null_count=null_count))
                continue

            mean_val = float(series.mean())
            std_val = float(series.std(ddof=1)) if len(series) > 1 else 0.0
            cv = (std_val / mean_val * 100) if mean_val != 0 else None

            stats.append(
                ColumnStats(
                    column=col,
                    count=int(series.count()),
                    mean=_safe_float(mean_val),
                    median=_safe_float(float(series.median())),
                    std=_safe_float(std_val),
                    min=_safe_float(float(series.min())),
                    max=_safe_float(float(series.max())),
                    p25=_safe_float(float(series.quantile(0.25))),
                    p75=_safe_float(float(series.quantile(0.75))),
                    null_count=null_count,
                    coefficient_of_variation=_safe_float(cv),
                )
            )
        return stats

    # ------------------------------------------------------------------ #
    # Performer detection
    # ------------------------------------------------------------------ #

    def _top_performers(
        self,
        df: pd.DataFrame,
        numeric_cols: list[str],
        label_col: Optional[str],
    ) -> list[PerformerEntry]:
        return self._ranked_entries(df, numeric_cols, label_col, largest=True)

    def _underperformers(
        self,
        df: pd.DataFrame,
        numeric_cols: list[str],
        label_col: Optional[str],
    ) -> list[PerformerEntry]:
        return self._ranked_entries(df, numeric_cols, label_col, largest=False)

    def _ranked_entries(
        self,
        df: pd.DataFrame,
        numeric_cols: list[str],
        label_col: Optional[str],
        *,
        largest: bool,
    ) -> list[PerformerEntry]:
        if not numeric_cols:
            return []

        metric_col = numeric_cols[0]
        series = df[metric_col].dropna()
        if series.empty:
            return []

        ranked_series = series.nlargest(self._top_n) if largest else series.nsmallest(self._top_n)
        entries: list[PerformerEntry] = []
        for rank, (idx, val) in enumerate(ranked_series.items(), start=1):
            if label_col and idx in df.index:
                label = str(df.at[idx, label_col])
            else:
                label = f"row_{idx}"
            val_f = _safe_float(float(val))
            if val_f is None:
                continue
            entries.append(
                PerformerEntry(label=label, value=val_f, metric=metric_col, rank=rank)
            )
        return entries

    # ------------------------------------------------------------------ #
    # Trend detection (linear regression via numpy.polyfit)
    # ------------------------------------------------------------------ #

    def _detect_trends(
        self, df: pd.DataFrame, numeric_cols: list[str]
    ) -> list[TrendInfo]:
        if len(df) < _MIN_ROWS_FOR_TREND:
            return []

        trends: list[TrendInfo] = []
        x = np.arange(len(df), dtype=float)

        for col in numeric_cols:
            y = pd.to_numeric(df[col], errors="coerce").values.astype(float)
            mask = ~np.isnan(y)
            if mask.sum() < _MIN_ROWS_FOR_TREND:
                continue

            x_clean = x[mask]
            y_clean = y[mask]

            try:
                coeffs = np.polyfit(x_clean, y_clean, deg=1)
                slope = float(coeffs[0])
            except (np.linalg.LinAlgError, ValueError):
                continue

            first_val = float(y_clean[0])
            last_val = float(y_clean[-1])
            mean_abs = abs(float(np.mean(y_clean)))
            threshold = mean_abs * 0.01 if mean_abs > 0 else 1e-6

            if slope > threshold:
                direction = "increasing"
            elif slope < -threshold:
                direction = "decreasing"
            else:
                direction = "flat"

            change_pct: Optional[float] = None
            if first_val != 0:
                change_pct = (last_val - first_val) / abs(first_val) * 100.0

            trends.append(
                TrendInfo(
                    column=col,
                    direction=direction,
                    slope=_safe_float(slope),  # type: ignore[arg-type]
                    first_value=_safe_float(first_val),
                    last_value=_safe_float(last_val),
                    change_pct=_safe_float(change_pct),
                )
            )
        return trends

    # ------------------------------------------------------------------ #
    # Correlation matrix (Pearson)
    # ------------------------------------------------------------------ #

    def _detect_correlations(
        self, df: pd.DataFrame, numeric_cols: list[str]
    ) -> list[CorrelationInfo]:
        if len(numeric_cols) < _MIN_NUMERIC_COLS_FOR_CORR:
            return []

        numeric_df = df[numeric_cols].apply(pd.to_numeric, errors="coerce").dropna()
        if len(numeric_df) < 3:
            return []

        try:
            corr_matrix = numeric_df.corr(method="pearson")
        except Exception:
            return []

        correlations: list[CorrelationInfo] = []
        seen: set[frozenset[str]] = set()

        for col_a in numeric_cols:
            for col_b in numeric_cols:
                if col_a == col_b:
                    continue
                pair: frozenset[str] = frozenset({col_a, col_b})
                if pair in seen:
                    continue
                seen.add(pair)

                try:
                    coeff = float(corr_matrix.loc[col_a, col_b])
                except KeyError:
                    continue

                if pd.isna(coeff) or abs(coeff) < self._corr_threshold:
                    continue

                if coeff >= 0.8:
                    strength = "strong_positive"
                elif coeff >= 0.5:
                    strength = "moderate_positive"
                elif coeff <= -0.8:
                    strength = "strong_negative"
                else:
                    strength = "moderate_negative"

                correlations.append(
                    CorrelationInfo(
                        column_a=col_a,
                        column_b=col_b,
                        coefficient=_safe_float(coeff),  # type: ignore[arg-type]
                        strength=strength,
                    )
                )
        return correlations

    # ------------------------------------------------------------------ #
    # Growth / volatility pattern detection
    # ------------------------------------------------------------------ #

    def _growth_patterns(
        self, df: pd.DataFrame, numeric_cols: list[str]
    ) -> list[GrowthPattern]:
        if len(df) < 3:
            return []

        patterns: list[GrowthPattern] = []

        for col in numeric_cols:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(series) < 3:
                continue

            pct_changes = (
                series.pct_change()
                .replace([np.inf, -np.inf], np.nan)
                .dropna()
            )
            if pct_changes.empty:
                continue

            avg_pct = float(pct_changes.mean() * 100)
            max_pct = float(pct_changes.max() * 100)
            min_pct = float(pct_changes.min() * 100)
            std_pct = float(pct_changes.std() * 100) if len(pct_changes) > 1 else 0.0

            mean_abs = abs(avg_pct)
            # Volatile when standard deviation exceeds half the mean absolute change.
            if std_pct > max(mean_abs * 0.5, 5.0) and mean_abs > 1.0:
                pattern = "volatile"
            elif avg_pct > 2.0:
                # Rising: check if growth rate is itself increasing (acceleration).
                mid = len(pct_changes) // 2
                if mid > 0:
                    first_avg = float(pct_changes.iloc[:mid].mean())
                    second_avg = float(pct_changes.iloc[mid:].mean())
                    pattern = "accelerating" if second_avg >= first_avg else "decelerating"
                else:
                    pattern = "accelerating"
            elif avg_pct < -2.0:
                # Falling: "decelerating" means decline is getting worse.
                mid = len(pct_changes) // 2
                if mid > 0:
                    first_avg = float(pct_changes.iloc[:mid].mean())
                    second_avg = float(pct_changes.iloc[mid:].mean())
                    pattern = "decelerating" if second_avg <= first_avg else "accelerating"
                else:
                    pattern = "decelerating"
            else:
                pattern = "stable"

            patterns.append(
                GrowthPattern(
                    column=col,
                    pattern=pattern,
                    avg_period_change_pct=_safe_float(avg_pct),
                    max_period_change_pct=_safe_float(max_pct),
                    min_period_change_pct=_safe_float(min_pct),
                )
            )
        return patterns


# ---------------------------------------------------------------------------
# Orchestration service
# ---------------------------------------------------------------------------


class InsightGenerationService:
    """Coordinate statistical analysis, LLM reasoning, and response caching.

    The service is the only public API for generating insights.  Callers do
    not need to know about the agent or engine internals.
    """

    def __init__(
        self,
        insight_agent: Any,  # InsightAgent — avoids circular import at module level
        cache_ttl: float = 300.0,
        cache_max_entries: int = 50,
        max_table_rows: int = 1000,
        top_n: int = 3,
        correlation_threshold: float = 0.5,
    ) -> None:
        self._agent = insight_agent
        self._engine = InsightStatEngine(
            top_n=top_n,
            correlation_threshold=correlation_threshold,
            max_rows=max_table_rows,
        )
        self._cache: TTLCache[str, InsightResponse] = TTLCache(
            ttl_seconds=cache_ttl,
            max_entries=cache_max_entries,
        )

    async def generate(
        self,
        dataset_id: str,
        question: str,
        table_data: list[dict[str, Any]],
    ) -> InsightResponse:
        """Generate AI insights for a query result.

        Steps:
            1. Return cached response if available (cache key = sha256 of inputs).
            2. Run deterministic statistical analysis (no LLM).
            3. Pass findings to LLM agent for natural-language reasoning.
            4. Cache and return the result.

        Never raises — all exceptions are caught and an empty response returned.
        """
        if not table_data:
            return _empty_response(
                "No tabular data available to generate insights. "
                "Run a query that returns rows first."
            )

        cache_key = _build_cache_key(dataset_id, question, table_data)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("InsightGenerationService: cache hit for key %.8s", cache_key)
            return cached.model_copy(update={"cache_hit": True})

        start = time.perf_counter()

        try:
            findings = self._engine.analyze(table_data)
            response = await self._agent.generate(findings=findings, question=question)
        except Exception as exc:
            logger.error("InsightGenerationService: generation failed: %s", exc)
            return _empty_response(f"Insight generation failed: {exc}")

        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)
        result = response.model_copy(
            update={"cache_hit": False, "generation_time_ms": elapsed_ms}
        )

        self._cache.put(cache_key, result)
        logger.debug(
            "InsightGenerationService: generated in %.1f ms for dataset %s",
            elapsed_ms,
            dataset_id,
        )
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_cache_key(
    dataset_id: str, question: str, table_data: list[dict[str, Any]]
) -> str:
    """Deterministic SHA-256 key from (dataset_id, question, table fingerprint)."""
    try:
        table_str = json.dumps(table_data, sort_keys=True, default=str)
    except Exception:
        table_str = repr(table_data)
    raw = f"{dataset_id}\x00{question.strip().lower()}\x00{table_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_float(val: Any) -> Optional[float]:
    """Return a JSON-safe float, or None for NaN/Inf/None."""
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return round(f, 6)
    except (TypeError, ValueError):
        return None


def _empty_response(message: str) -> InsightResponse:
    return InsightResponse(
        summary=message,
        key_insights=[],
        trends=[],
        top_performers=[],
        underperformers=[],
        recommendations=[],
    )
