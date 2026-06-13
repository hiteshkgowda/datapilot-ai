"""Anomaly Detection Engine.

Four detection methods:

1. ZScoreDetector          — per-column, numpy, always available.
2. IQRDetector             — per-column, numpy, always available.
3. IsolationForestDetector — multivariate; scikit-learn preferred,
                             falls back to MahalanobisDetector (numpy) when
                             sklearn is not installed.
4. SeasonalAnomalyDetector — per-column; uses STL decomposition (statsmodels)
                             to isolate residuals before z-scoring; falls back
                             to rolling-MAD modified z-score when statsmodels is
                             unavailable.

All four produce AnomalyPoint objects (from app.schemas.anomaly).
AnomalyDetectionEngine orchestrates all four and returns ColumnAnomaly objects.
AnomalyChartBuilder builds a Plotly figure JSON highlighting anomalies.

Anti-hallucination guarantee: every possible_reason string is generated
deterministically from statistical findings — no LLM involvement anywhere.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from app.schemas.anomaly import AnomalyPoint, ColumnAnomaly

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy imports
# ---------------------------------------------------------------------------

try:
    from sklearn.ensemble import IsolationForest as _SkIsoForest

    _SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SKLEARN_AVAILABLE = False
    logger.info("scikit-learn not installed — IsolationForest will use Mahalanobis fallback.")

try:
    from statsmodels.tsa.seasonal import STL as _STL

    _STATSMODELS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _STATSMODELS_AVAILABLE = False
    logger.info("statsmodels not installed — seasonal detector will use rolling-MAD fallback.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum rows needed for each method to be meaningful.
_MIN_ROWS_ZSCORE = 3
_MIN_ROWS_IQR = 4
_MIN_ROWS_ISO = 20
_MIN_ROWS_SEASONAL = 8

# ISO score re-scaling: the raw sklearn score_samples output is in (-inf, 0].
# Empirically most inlier scores cluster around -0.1 .. -0.5.
# We re-scale so that a "typical outlier" lands near z=3 for severity parity.
_ISO_SCALE_FACTOR = 12.0

# Severity thresholds (applies to normalised score comparable to |z|).
_SEVERITY: tuple[tuple[float, str], ...] = (
    (6.0, "critical"),
    (4.0, "high"),
    (3.0, "medium"),
    (0.0, "low"),
)

# Plotly colours keyed by severity.
_SEV_COLOUR: dict[str, str] = {
    "critical": "#ef4444",
    "high": "#f97316",
    "medium": "#f59e0b",
    "low": "#facc15",
}
_NORMAL_COLOUR = "#6366f1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _severity_from_score(score: float) -> str:
    """Return severity label for a normalised anomaly score."""
    for threshold, label in _SEVERITY:
        if score >= threshold:
            return label
    return "low"


def _numeric_series(df: pd.DataFrame, col: str) -> "pd.Series[Any]":
    """Return a float series with NaNs for unparseable values."""
    return pd.to_numeric(df[col], errors="coerce")


def _col_stats(series: "pd.Series[Any]") -> dict[str, float]:
    clean = series.dropna()
    if clean.empty:
        return {"mean": 0.0, "std": 0.0, "q1": 0.0, "q3": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": float(clean.mean()),
        "std": float(clean.std(ddof=1)) if len(clean) > 1 else 0.0,
        "q1": float(np.percentile(clean, 25)),
        "q3": float(np.percentile(clean, 75)),
        "min": float(clean.min()),
        "max": float(clean.max()),
    }


def _merge_points(points_by_method: list[list[AnomalyPoint]]) -> list[AnomalyPoint]:
    """Merge anomaly point lists from multiple methods.

    For the same row_index, keep the point with the worst severity (highest score).
    Preserves all unique indices from all methods.
    """
    best: dict[int, AnomalyPoint] = {}
    for method_points in points_by_method:
        for pt in method_points:
            existing = best.get(pt.row_index)
            if existing is None or pt.score > existing.score:
                best[pt.row_index] = pt
    return sorted(best.values(), key=lambda p: p.row_index)


def _auto_detect_columns(df: pd.DataFrame) -> list[str]:
    """Return numeric columns, excluding obvious id/index columns."""
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    return [c for c in numeric if not _is_id_col(c)]


def _is_id_col(col: str) -> bool:
    lower = col.lower()
    return any(kw in lower for kw in ("_id", " id", "index", "idx", "key", "code", "num"))


def _auto_detect_period(series: "pd.Series[Any]") -> int:
    """Guess a seasonal period from series length.

    Uses powers-of-2 heuristic anchored to common business periods.
    """
    n = len(series.dropna())
    if n >= 104:
        return 52  # weekly data → annual seasonality
    if n >= 24:
        return 12  # monthly data → annual
    if n >= 14:
        return 7   # daily data → weekly
    if n >= 8:
        return 4   # quarterly
    return max(2, n // 2)


# ---------------------------------------------------------------------------
# Z-Score detector
# ---------------------------------------------------------------------------


class ZScoreDetector:
    """Flag per-column points where |z-score| exceeds the threshold."""

    def detect(
        self,
        df: pd.DataFrame,
        col: str,
        threshold: float = 3.0,
        time_col: Optional[str] = None,
    ) -> list[AnomalyPoint]:
        series = _numeric_series(df, col)
        clean = series.dropna()
        if len(clean) < _MIN_ROWS_ZSCORE:
            return []
        mean = float(clean.mean())
        std = float(clean.std(ddof=1))
        if std < 1e-9:
            return []

        points: list[AnomalyPoint] = []
        for idx in clean.index:
            v = float(clean[idx])
            z = abs((v - mean) / std)
            if z >= threshold:
                label = _label(df, idx, time_col)
                points.append(
                    AnomalyPoint(
                        row_index=int(idx),
                        value=round(v, 6),
                        score=round(z, 4),
                        severity=_severity_from_score(z),
                        method="zscore",
                        label=label,
                    )
                )
        return points


# ---------------------------------------------------------------------------
# IQR detector
# ---------------------------------------------------------------------------


class IQRDetector:
    """Flag per-column points outside Q1 − k·IQR  …  Q3 + k·IQR."""

    def detect(
        self,
        df: pd.DataFrame,
        col: str,
        multiplier: float = 1.5,
        time_col: Optional[str] = None,
    ) -> list[AnomalyPoint]:
        series = _numeric_series(df, col)
        clean = series.dropna()
        if len(clean) < _MIN_ROWS_IQR:
            return []

        q1 = float(np.percentile(clean, 25))
        q3 = float(np.percentile(clean, 75))
        iqr = q3 - q1
        lower = q1 - multiplier * iqr
        upper = q3 + multiplier * iqr

        points: list[AnomalyPoint] = []
        for idx in clean.index:
            v = float(clean[idx])
            if v < lower or v > upper:
                if iqr > 1e-9:
                    # Express score as number-of-IQRs beyond the fence.
                    score = max((lower - v) / iqr, (v - upper) / iqr, 0.0)
                else:
                    # Zero-IQR column: fall back to absolute deviation from median.
                    score = abs(v - float(np.median(clean)))
                label = _label(df, idx, time_col)
                points.append(
                    AnomalyPoint(
                        row_index=int(idx),
                        value=round(v, 6),
                        score=round(score, 4),
                        severity=_severity_from_score(score),
                        method="iqr",
                        label=label,
                    )
                )
        return points


# ---------------------------------------------------------------------------
# Isolation Forest detector (multivariate)
# ---------------------------------------------------------------------------


class IsolationForestDetector:
    """Multivariate anomaly detection using Isolation Forest.

    Uses scikit-learn's IsolationForest when available; falls back to
    Mahalanobis distance scoring (numpy-only) when sklearn is absent.
    """

    def detect(
        self,
        df: pd.DataFrame,
        columns: list[str],
        contamination: float = 0.05,
        time_col: Optional[str] = None,
    ) -> dict[str, list[AnomalyPoint]]:
        """Return {column → anomaly points} for anomalous rows."""
        if not columns:
            return {}

        # Build a clean numeric matrix (rows with any NaN are excluded).
        numeric_df = pd.DataFrame(
            {c: _numeric_series(df, c) for c in columns}
        ).dropna()

        if len(numeric_df) < _MIN_ROWS_ISO:
            return {}

        X = numeric_df.to_numpy(dtype=float)

        if _SKLEARN_AVAILABLE:
            raw_scores = self._sklearn_scores(X, contamination)
        else:
            raw_scores = self._mahalanobis_scores(X)

        # Re-scale to a z-score-like magnitude.
        scores_norm = self._normalise_scores(raw_scores)

        # Threshold: contamination-th percentile of normalised scores.
        threshold = float(np.percentile(scores_norm, (1.0 - contamination) * 100))

        result: dict[str, list[AnomalyPoint]] = {c: [] for c in columns}
        for i, orig_idx in enumerate(numeric_df.index):
            score = scores_norm[i]
            if score < threshold:
                continue
            row_vals = {c: float(numeric_df.at[orig_idx, c]) for c in columns}
            # Attribute anomaly to the column with the largest z-deviation.
            col_z = self._per_col_z(numeric_df, orig_idx, columns)
            primary_col = max(col_z, key=lambda c: col_z[c])
            label = _label(df, orig_idx, time_col)
            result[primary_col].append(
                AnomalyPoint(
                    row_index=int(orig_idx),
                    value=round(row_vals[primary_col], 6),
                    score=round(score, 4),
                    severity=_severity_from_score(score),
                    method="isolation_forest",
                    label=label,
                )
            )
            # Secondary columns with also-extreme values.
            for col in columns:
                if col == primary_col:
                    continue
                if col_z.get(col, 0.0) >= 2.0:
                    result[col].append(
                        AnomalyPoint(
                            row_index=int(orig_idx),
                            value=round(row_vals[col], 6),
                            score=round(score * 0.7, 4),
                            severity=_severity_from_score(score * 0.7),
                            method="isolation_forest",
                            label=label,
                        )
                    )

        return {c: pts for c, pts in result.items() if pts}

    @staticmethod
    def _sklearn_scores(X: np.ndarray, contamination: float) -> np.ndarray:
        forest = _SkIsoForest(contamination=contamination, random_state=42, n_jobs=1)
        forest.fit(X)
        # score_samples returns values in (-inf, 0]; negate so higher = more anomalous.
        return -forest.score_samples(X)  # type: ignore[union-attr]

    @staticmethod
    def _mahalanobis_scores(X: np.ndarray) -> np.ndarray:
        """Numpy-only Mahalanobis distance from the centroid."""
        mean = X.mean(axis=0)
        diff = X - mean
        if X.shape[1] == 1:
            std = X.std(axis=0)
            std = np.where(std < 1e-9, 1.0, std)
            return np.abs(diff[:, 0]) / std[0]
        cov = np.cov(X.T)
        try:
            inv_cov = np.linalg.pinv(cov)
            scores = np.sqrt(np.einsum("ij,jk,ik->i", diff, inv_cov, diff))
        except np.linalg.LinAlgError:
            std = X.std(axis=0)
            std = np.where(std < 1e-9, 1.0, std)
            scores = np.sqrt(((diff / std) ** 2).sum(axis=1))
        return scores

    @staticmethod
    def _normalise_scores(raw: np.ndarray) -> np.ndarray:
        """Re-scale raw scores to a z-score-comparable range."""
        r_min, r_max = float(raw.min()), float(raw.max())
        if r_max - r_min < 1e-9:
            return np.zeros_like(raw)
        normalised = (raw - r_min) / (r_max - r_min)  # [0, 1]
        return normalised * _ISO_SCALE_FACTOR

    @staticmethod
    def _per_col_z(
        numeric_df: pd.DataFrame,
        idx: Any,
        columns: list[str],
    ) -> dict[str, float]:
        result = {}
        for c in columns:
            col_series = numeric_df[c].dropna()
            std = float(col_series.std(ddof=1)) if len(col_series) > 1 else 1.0
            if std < 1e-9:
                std = 1.0
            result[c] = abs((float(numeric_df.at[idx, c]) - float(col_series.mean())) / std)
        return result


# ---------------------------------------------------------------------------
# Seasonal anomaly detector
# ---------------------------------------------------------------------------


class SeasonalAnomalyDetector:
    """Detect anomalies after removing trend + seasonal components.

    STL (statsmodels) is used when available; rolling MAD z-score otherwise.
    """

    def detect(
        self,
        df: pd.DataFrame,
        col: str,
        period: Optional[int] = None,
        threshold: float = 3.0,
        time_col: Optional[str] = None,
    ) -> list[AnomalyPoint]:
        series = _numeric_series(df, col).dropna()
        if len(series) < _MIN_ROWS_SEASONAL:
            return []

        if period is None:
            period = _auto_detect_period(series)

        if _STATSMODELS_AVAILABLE and len(series) >= 2 * period:
            return self._stl_detect(df, series, col, period, threshold, time_col)
        return self._rolling_mad_detect(df, series, col, threshold, time_col)

    @staticmethod
    def _stl_detect(
        df: pd.DataFrame,
        series: "pd.Series[Any]",
        col: str,
        period: int,
        threshold: float,
        time_col: Optional[str],
    ) -> list[AnomalyPoint]:
        try:
            stl_result = _STL(series.reset_index(drop=True), period=period, robust=True).fit()
            residuals: "pd.Series[Any]" = pd.Series(stl_result.resid)
        except Exception as exc:
            logger.debug("STL failed for column %r: %s — using rolling MAD.", col, exc)
            return SeasonalAnomalyDetector._rolling_mad_detect(
                df, series, col, threshold, time_col
            )

        mean_r = float(residuals.mean())
        std_r = float(residuals.std(ddof=1))
        if std_r < 1e-9:
            return []

        orig_indices = series.index.tolist()
        points: list[AnomalyPoint] = []
        for i, resid in enumerate(residuals):
            z = abs((float(resid) - mean_r) / std_r)
            if z >= threshold:
                orig_idx = orig_indices[i] if i < len(orig_indices) else i
                label = _label(df, orig_idx, time_col)
                points.append(
                    AnomalyPoint(
                        row_index=int(orig_idx),
                        value=round(float(series.iloc[i]), 6),
                        score=round(z, 4),
                        severity=_severity_from_score(z),
                        method="seasonal",
                        label=label,
                    )
                )
        return points

    @staticmethod
    def _rolling_mad_detect(
        df: pd.DataFrame,
        series: "pd.Series[Any]",
        col: str,
        threshold: float,
        time_col: Optional[str],
    ) -> list[AnomalyPoint]:
        window = max(3, min(10, len(series) // 4))
        reset = series.reset_index(drop=True)
        rolling_med = reset.rolling(window=window, center=True, min_periods=1).median()
        diff = (reset - rolling_med).abs()
        mad = diff.rolling(window=window, center=True, min_periods=1).median().clip(lower=1e-9)
        # Modified z-score: 0.6745 * |x - median| / MAD
        mod_z = 0.6745 * diff / mad

        orig_indices = series.index.tolist()
        points: list[AnomalyPoint] = []
        for i in range(len(reset)):
            z = float(mod_z.iloc[i])
            if z >= threshold:
                orig_idx = orig_indices[i] if i < len(orig_indices) else i
                label = _label(df, orig_idx, time_col)
                points.append(
                    AnomalyPoint(
                        row_index=int(orig_idx),
                        value=round(float(reset.iloc[i]), 6),
                        score=round(z, 4),
                        severity=_severity_from_score(z),
                        method="seasonal",
                        label=label,
                    )
                )
        return points


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


@dataclass
class _ColResult:
    """Internal per-column aggregation before packaging into ColumnAnomaly."""

    column: str
    points: list[AnomalyPoint] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    stats: dict[str, float] = field(default_factory=dict)


class AnomalyDetectionEngine:
    """Orchestrate all four detectors and produce ColumnAnomaly results.

    Pure CPU-bound; safe to call from a thread pool.
    """

    def __init__(
        self,
        zscore_threshold: float = 3.0,
        iqr_multiplier: float = 1.5,
        contamination: float = 0.05,
        seasonal_period: Optional[int] = None,
        merge_methods: bool = True,
    ) -> None:
        self._z_threshold = zscore_threshold
        self._iqr_mult = iqr_multiplier
        self._contamination = contamination
        self._season_period = seasonal_period
        self._merge = merge_methods

        self._zscore = ZScoreDetector()
        self._iqr = IQRDetector()
        self._iso = IsolationForestDetector()
        self._seasonal = SeasonalAnomalyDetector()

    def analyze(
        self,
        df: pd.DataFrame,
        columns: Optional[list[str]],
        methods: list[str],
        time_col: Optional[str] = None,
    ) -> tuple[list[ColumnAnomaly], list[str]]:
        """Run all requested detectors; return (column_anomalies, possible_reasons)."""
        if df.empty:
            return [], ["Dataset is empty — no anomaly analysis possible."]

        target_cols = columns or _auto_detect_columns(df)
        target_cols = [c for c in target_cols if c in df.columns]
        if not target_cols:
            return [], ["No numeric columns found for anomaly analysis."]

        methods_used: set[str] = set()
        col_results: dict[str, _ColResult] = {
            c: _ColResult(column=c, stats=_col_stats(_numeric_series(df, c)))
            for c in target_cols
        }

        # ── Z-Score ──────────────────────────────────────────────────────────
        if "zscore" in methods:
            for col in target_cols:
                pts = self._zscore.detect(df, col, self._z_threshold, time_col)
                if pts:
                    col_results[col].points.append(pts)
                    col_results[col].methods.append("zscore")
                    methods_used.add("zscore")

        # ── IQR ──────────────────────────────────────────────────────────────
        if "iqr" in methods:
            for col in target_cols:
                pts = self._iqr.detect(df, col, self._iqr_mult, time_col)
                if pts:
                    col_results[col].points.append(pts)
                    if "iqr" not in col_results[col].methods:
                        col_results[col].methods.append("iqr")
                    methods_used.add("iqr")

        # ── Isolation Forest (multivariate) ───────────────────────────────────
        if "isolation_forest" in methods:
            iso_results = self._iso.detect(df, target_cols, self._contamination, time_col)
            for col, pts in iso_results.items():
                if pts and col in col_results:
                    col_results[col].points.append(pts)
                    if "isolation_forest" not in col_results[col].methods:
                        col_results[col].methods.append("isolation_forest")
                    methods_used.add("isolation_forest")

        # ── Seasonal ──────────────────────────────────────────────────────────
        if "seasonal" in methods:
            for col in target_cols:
                pts = self._seasonal.detect(df, col, self._season_period, self._z_threshold, time_col)
                if pts:
                    col_results[col].points.append(pts)
                    if "seasonal" not in col_results[col].methods:
                        col_results[col].methods.append("seasonal")
                    methods_used.add("seasonal")

        # ── Merge and package ─────────────────────────────────────────────────
        result: list[ColumnAnomaly] = []
        for col, cr in col_results.items():
            if not cr.points:
                continue
            merged = _merge_points(cr.points) if self._merge else [p for pts in cr.points for p in pts]
            result.append(
                ColumnAnomaly(
                    column=col,
                    anomaly_count=len(merged),
                    anomaly_points=merged,
                    methods=cr.methods,
                    mean=round(cr.stats.get("mean", 0.0), 6),
                    std=round(cr.stats.get("std", 0.0), 6),
                    q1=round(cr.stats.get("q1", 0.0), 6),
                    q3=round(cr.stats.get("q3", 0.0), 6),
                    min_value=round(cr.stats.get("min", 0.0), 6),
                    max_value=round(cr.stats.get("max", 0.0), 6),
                )
            )

        result.sort(key=lambda c: c.anomaly_count, reverse=True)
        reasons = _infer_reasons(result, df)
        return result, reasons


# ---------------------------------------------------------------------------
# Rule-based reason inference
# ---------------------------------------------------------------------------


def _infer_reasons(
    findings: list[ColumnAnomaly],
    df: pd.DataFrame,
) -> list[str]:
    """Generate human-readable explanations from statistical findings only.

    Deterministic; no LLM involvement.  Deduplicates via insertion-ordered dict.
    """
    reasons: dict[str, None] = {}

    for ca in findings:
        pts = ca.anomaly_points
        if not pts:
            continue

        spikes = [p for p in pts if p.value > ca.mean]
        drops = [p for p in pts if p.value < ca.mean]
        criticals = [p for p in pts if p.severity == "critical"]
        highs = [p for p in pts if p.severity == "high"]

        # Consecutive runs → regime change or data quality
        consec = _consecutive_runs([p.row_index for p in pts])
        if consec:
            run = consec[0]
            reasons[
                f"'{ca.column}': {len(run)} consecutive anomalous values at rows "
                f"{run[0]}–{run[-1]} — possible regime change or batch data quality issue."
            ] = None

        # Predominantly positive spikes
        if spikes and len(spikes) > len(drops):
            reasons[
                f"'{ca.column}': {len(spikes)} positive spike(s) detected "
                f"(values up to {ca.max_value:,.2f} vs mean {ca.mean:,.2f}). "
                "Possible promotional event, data entry error, or seasonal peak."
            ] = None

        # Predominantly negative drops
        if drops and len(drops) > len(spikes):
            reasons[
                f"'{ca.column}': {len(drops)} negative drop(s) detected "
                f"(values as low as {ca.min_value:,.2f} vs mean {ca.mean:,.2f}). "
                "Possible revenue loss, measurement gap, or operational disruption."
            ] = None

        # Critical points always get their own reason.
        if criticals:
            worst = max(criticals, key=lambda p: p.score)
            reasons[
                f"'{ca.column}': {len(criticals)} CRITICAL anomaly/anomalies "
                f"(score ≥ 6σ). Worst: value={worst.value:,.4g} at row {worst.row_index}. "
                "Requires immediate investigation."
            ] = None
        elif highs:
            worst = max(highs, key=lambda p: p.score)
            reasons[
                f"'{ca.column}': {len(highs)} high-severity anomaly/anomalies "
                f"(score ≥ 4σ). Worst: value={worst.value:,.4g} at row {worst.row_index}."
            ] = None

    # Multiple columns affected → systemic signal.
    if len(findings) > 2:
        cols = ", ".join(f"'{c.column}'" for c in findings[:3])
        reasons[
            f"Anomalies detected across {len(findings)} metrics simultaneously "
            f"({cols}{', …' if len(findings) > 3 else ''}). "
            "Possible systemic data quality issue or significant business event affecting multiple KPIs."
        ] = None

    if not reasons:
        reasons["No statistically significant anomalies detected under current thresholds."] = None

    return list(reasons.keys())


def _consecutive_runs(indices: list[int]) -> list[list[int]]:
    """Group sorted indices into consecutive runs of length ≥ 2."""
    if not indices:
        return []
    sorted_idx = sorted(set(indices))
    runs: list[list[int]] = []
    run: list[int] = [sorted_idx[0]]
    for x in sorted_idx[1:]:
        if x == run[-1] + 1:
            run.append(x)
        else:
            if len(run) >= 2:
                runs.append(run)
            run = [x]
    if len(run) >= 2:
        runs.append(run)
    return runs


# ---------------------------------------------------------------------------
# Chart builder
# ---------------------------------------------------------------------------


class AnomalyChartBuilder:
    """Build a Plotly figure JSON highlighting anomalies by severity."""

    _MAX_SUBPLOTS = 3

    def build(
        self,
        df: pd.DataFrame,
        col_anomalies: list[ColumnAnomaly],
        time_col: Optional[str] = None,
    ) -> Optional[dict]:
        """Return Plotly figure JSON or None if nothing to plot."""
        display = col_anomalies[: self._MAX_SUBPLOTS]
        if not display:
            return None

        n = len(display)
        titles = [f"{c.column}  ({c.anomaly_count} anomaly/anomalies)" for c in display]
        fig = make_subplots(
            rows=n,
            cols=1,
            subplot_titles=titles,
            vertical_spacing=max(0.06, 0.24 / n),
        )

        # Resolve x-axis values.
        if time_col and time_col in df.columns:
            x_all = df[time_col].astype(str).tolist()
        else:
            x_all = list(range(len(df)))

        shown_legend: set[str] = set()

        for row_i, ca in enumerate(display, start=1):
            col = ca.column
            if col not in df.columns:
                continue

            y_all = pd.to_numeric(df[col], errors="coerce").tolist()
            anomaly_idx_set = {p.row_index for p in ca.anomaly_points}

            # ── Normal values ────────────────────────────────────────────────
            x_norm = [x_all[j] for j in range(len(df)) if j not in anomaly_idx_set]
            y_norm = [y_all[j] for j in range(len(df)) if j not in anomaly_idx_set]
            show_norm = "normal" not in shown_legend
            if show_norm:
                shown_legend.add("normal")

            fig.add_trace(
                go.Scatter(
                    x=x_norm,
                    y=y_norm,
                    mode="lines+markers",
                    name="Normal",
                    marker=dict(size=4, color=_NORMAL_COLOUR, opacity=0.7),
                    line=dict(color=_NORMAL_COLOUR, width=1.5),
                    showlegend=show_norm,
                    legendgroup="normal",
                ),
                row=row_i,
                col=1,
            )

            # ── Anomaly points grouped by severity ───────────────────────────
            for sev, colour in _SEV_COLOUR.items():
                sev_pts = [p for p in ca.anomaly_points if p.severity == sev]
                if not sev_pts:
                    continue
                legend_key = f"anomaly_{sev}"
                show_sev = legend_key not in shown_legend
                if show_sev:
                    shown_legend.add(legend_key)

                fig.add_trace(
                    go.Scatter(
                        x=[x_all[p.row_index] if p.row_index < len(x_all) else p.row_index for p in sev_pts],
                        y=[p.value for p in sev_pts],
                        mode="markers",
                        name=f"Anomaly ({sev})",
                        marker=dict(
                            size=12,
                            color=colour,
                            symbol="circle",
                            line=dict(color="white", width=1.5),
                        ),
                        showlegend=show_sev,
                        legendgroup=legend_key,
                        text=[
                            f"Score: {p.score:.2f}<br>Method: {p.method}<br>"
                            f"Severity: {p.severity}<br>Value: {p.value:,.4g}"
                            for p in sev_pts
                        ],
                        hovertemplate="%{text}<extra></extra>",
                    ),
                    row=row_i,
                    col=1,
                )

        fig.update_layout(
            title_text="Anomaly Detection Results",
            title_font_size=15,
            template="plotly_white",
            height=max(300, 300 * n),
            margin=dict(l=50, r=20, t=60, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        )

        return json.loads(pio.to_json(fig))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _label(df: pd.DataFrame, idx: Any, time_col: Optional[str]) -> Optional[str]:
    """Return a human-readable label for a row, or None."""
    if time_col is None or time_col not in df.columns:
        return None
    try:
        val = df[time_col].iloc[int(idx)]
        return str(val) if pd.notna(val) else None
    except (IndexError, TypeError):
        return None


def _overall_severity(col_anomalies: list[ColumnAnomaly]) -> str:
    """Derive overall severity from the worst individual point."""
    if not col_anomalies:
        return "none"
    worst_order = {"critical": 4, "high": 3, "medium": 2, "low": 1, "none": 0}
    worst = "none"
    total = sum(c.anomaly_count for c in col_anomalies)
    for ca in col_anomalies:
        for pt in ca.anomaly_points:
            if worst_order.get(pt.severity, 0) > worst_order.get(worst, 0):
                worst = pt.severity
    # Escalate by volume: many low-severity anomalies → medium overall.
    if worst == "low" and total >= 10:
        worst = "medium"
    if worst == "medium" and total >= 20:
        worst = "high"
    return worst
