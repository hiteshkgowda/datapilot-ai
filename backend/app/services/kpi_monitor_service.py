"""KPI Monitoring Service.

Profiles numeric columns in a DataFrame as KPIs, builds trend charts,
detects threshold-based alerts, and produces prioritised recommendations.

All analysis is deterministic (no LLM). Results are cached by SHA-256
of the dataset_id with a configurable TTL.
"""

from __future__ import annotations

import math
import time
from typing import Any, Literal, Optional

import pandas as pd

from app.core.cache import TTLCache
from app.core.math_utils import dataset_cache_key
from app.schemas.kpi_monitor import (
    KPIAlert,
    KPIMonitorResponse,
    KPIRecommendation,
    KPIStat,
)

# ── Config ────────────────────────────────────────────────────────────────────
_WARN_Z = 2.0         # z-score threshold → warning alert
_CRIT_Z = 3.0         # z-score threshold → critical alert
_SPARKLINE_POINTS = 30
_TREND_WINDOW = 0.25  # compare last 25% vs first 75% for trend
_MIN_ROWS = 5         # minimum non-null rows to compute a KPI
_MAX_ALERTS = 60      # cap total alerts

_TIME_COLUMN_NAMES = frozenset({
    "date", "time", "datetime", "timestamp", "period",
    "year", "month", "week", "day", "quarter",
})


# ── Utilities ─────────────────────────────────────────────────────────────────

def _detect_time_column(df: pd.DataFrame) -> Optional[str]:
    """Return the first usable time/date column, or None."""
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col
    for col in df.columns:
        name = col.lower().strip()
        if name in _TIME_COLUMN_NAMES or any(t in name for t in _TIME_COLUMN_NAMES):
            try:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().mean() > 0.8:
                    return col
            except Exception:
                pass
    return None


def _format_value(v: float) -> str:
    if math.isnan(v) or math.isinf(v):
        return "N/A"
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.1f}K"
    if abs(v) >= 10:
        return f"{v:,.1f}"
    return f"{v:.3g}"


def _downsample(series: pd.Series, n: int) -> list[float]:
    """Evenly downsample a series to at most n non-NaN points."""
    clean = series.dropna().reset_index(drop=True)
    if len(clean) <= n:
        return [float(v) for v in clean]
    step = len(clean) / n
    indices = [int(i * step) for i in range(n)]
    return [float(clean.iloc[i]) for i in indices]


def _build_kpi_chart(
    series: pd.Series,
    col: str,
    time_labels: Optional[pd.Series],
    mean: float,
    std: float,
) -> dict[str, Any]:
    """Plotly line chart: data + mean line + ±2σ band + critical alert markers."""
    non_null = series.dropna()
    x_vals: list[Any]
    if time_labels is not None:
        x_vals = [str(v) for v in time_labels[series.notna()].tolist()]
    else:
        x_vals = list(non_null.index.tolist())

    y_vals = non_null.tolist()
    n = len(y_vals)

    # Critical alert mask
    alert_mask = [(abs(v - mean) / std > _CRIT_Z if std > 0 else False) for v in y_vals]
    alert_x = [x for x, flag in zip(x_vals, alert_mask) if flag]
    alert_y = [y for y, flag in zip(y_vals, alert_mask) if flag]

    upper = mean + 2 * std
    lower = mean - 2 * std

    traces: list[dict[str, Any]] = [
        # ±2σ band
        {
            "type": "scatter",
            "x": x_vals + x_vals[::-1],
            "y": [upper] * n + [lower] * n,
            "fill": "toself",
            "fillcolor": "rgba(99,102,241,0.06)",
            "line": {"width": 0},
            "name": "±2σ band",
            "hoverinfo": "skip",
            "showlegend": False,
        },
        # Mean line
        {
            "type": "scatter",
            "x": x_vals,
            "y": [mean] * n,
            "mode": "lines",
            "line": {"color": "rgba(99,102,241,0.5)", "width": 1.5, "dash": "dash"},
            "name": f"Mean ({_format_value(mean)})",
            "hovertemplate": f"Mean: {_format_value(mean)}<extra></extra>",
        },
        # Main data line
        {
            "type": "scatter",
            "x": x_vals,
            "y": y_vals,
            "mode": "lines+markers",
            "line": {"color": "#6366f1", "width": 2},
            "marker": {"size": 4, "color": "#6366f1"},
            "name": col,
            "hovertemplate": "%{x}: %{y:.4g}<extra></extra>",
        },
    ]

    if alert_x:
        traces.append({
            "type": "scatter",
            "x": alert_x,
            "y": alert_y,
            "mode": "markers",
            "marker": {"size": 8, "color": "#ef4444", "symbol": "circle-open", "line": {"width": 2}},
            "name": "Critical alerts",
            "hovertemplate": "%{x}: %{y:.4g} ⚠<extra></extra>",
        })

    return {
        "data": traces,
        "layout": {
            "showlegend": True,
            "legend": {"orientation": "h", "y": -0.2},
            "xaxis": {"showgrid": False},
            "yaxis": {"title": col},
            "margin": {"t": 20, "r": 12, "b": 40, "l": 52},
            "height": 240,
        },
    }


def _analyse_kpi(
    col: str,
    series: pd.Series,
    time_labels: Optional[pd.Series],
    row_count: int,
) -> tuple[KPIStat, list[KPIAlert]]:
    """Compute all metrics for one numeric column."""
    non_null = series.dropna()
    n = len(non_null)

    if n < _MIN_ROWS:
        stub = KPIStat(
            column=col,
            label=col.replace("_", " ").title(),
            current_value=float(non_null.iloc[-1]) if n > 0 else 0.0,
            formatted_value="N/A",
            mean=0.0, std=0.0,
            min_value=0.0, max_value=0.0,
            p25=0.0, p75=0.0,
            change_pct=None,
            trend="flat",
            health="unknown",
            alert_count=0,
            sparkline=[],
            chart_spec=None,
        )
        return stub, []

    arr = non_null.astype(float)
    mean = float(arr.mean())
    std = float(arr.std()) if n > 1 else 0.0
    col_min = float(arr.min())
    col_max = float(arr.max())
    p25 = float(arr.quantile(0.25))
    p75 = float(arr.quantile(0.75))
    current_value = float(arr.iloc[-1])

    # Trend: compare last 25% vs rest
    split = max(1, int(n * _TREND_WINDOW))
    recent_mean = float(arr.iloc[-split:].mean())
    prior_mean = float(arr.iloc[:-split].mean()) if n - split > 0 else mean
    change_pct: Optional[float] = None
    if abs(prior_mean) > 1e-9:
        change_pct = round((recent_mean - prior_mean) / abs(prior_mean) * 100, 2)
    trend: Literal["up", "down", "flat"] = (
        "up" if (change_pct or 0) > 3 else "down" if (change_pct or 0) < -3 else "flat"
    )

    # Alerts via z-score
    alerts: list[KPIAlert] = []
    if std > 0:
        z_scores = ((arr - mean) / std).abs()
        alert_idx = non_null.index[z_scores >= _WARN_Z].tolist()
        for idx in alert_idx:
            val = float(series.iloc[idx]) if idx < len(series) else float(non_null.loc[idx])
            z = float(abs((val - mean) / std))
            sev: Literal["critical", "high", "medium", "low"] = (
                "critical" if z >= _CRIT_Z else "high" if z >= 2.5 else "medium"
            )
            label_val: Optional[str] = None
            if time_labels is not None and idx < len(time_labels):
                label_val = str(time_labels.iloc[idx])
            alerts.append(KPIAlert(
                severity=sev,
                kpi_name=col,
                message=f"{col} = {_format_value(val)} ({z:.1f}σ from mean)",
                value=val,
                threshold=mean + (_WARN_Z if val > mean else -_WARN_Z) * std,
                row_index=int(idx),
                label=label_val,
            ))

    # Health
    crit_count = sum(1 for a in alerts if a.severity == "critical")
    health: Literal["healthy", "warning", "critical", "unknown"] = (
        "critical" if crit_count > 0 else
        "warning" if len(alerts) > 0 else
        "healthy"
    )

    sparkline = _downsample(series, _SPARKLINE_POINTS)
    chart_spec = _build_kpi_chart(series, col, time_labels, mean, std)

    stat = KPIStat(
        column=col,
        label=col.replace("_", " ").title(),
        current_value=current_value,
        formatted_value=_format_value(current_value),
        mean=round(mean, 4),
        std=round(std, 4),
        min_value=round(col_min, 4),
        max_value=round(col_max, 4),
        p25=round(p25, 4),
        p75=round(p75, 4),
        change_pct=change_pct,
        trend=trend,
        health=health,
        alert_count=len(alerts),
        sparkline=sparkline,
        chart_spec=chart_spec,
    )
    return stat, alerts


def _build_recommendations(kpis: list[KPIStat]) -> list[KPIRecommendation]:
    recs: list[KPIRecommendation] = []

    critical = [k for k in kpis if k.health == "critical"]
    warning = [k for k in kpis if k.health == "warning"]
    trending_down = [k for k in kpis if k.trend == "down" and k.health != "unknown"]
    high_std = [k for k in kpis if k.std > 0 and k.mean != 0 and k.std / abs(k.mean) > 0.5]

    for k in critical:
        recs.append(KPIRecommendation(
            priority="critical",
            kpi=k.column,
            issue=f"{k.label} has {k.alert_count} critical threshold breach(es)",
            action="Investigate immediately — values deviate >3σ from the historical mean.",
        ))

    for k in warning:
        recs.append(KPIRecommendation(
            priority="high",
            kpi=k.column,
            issue=f"{k.label} has {k.alert_count} anomalous value(s)",
            action="Review recent data — values exceed 2σ. Check for data entry errors or real events.",
        ))

    for k in trending_down:
        pct = abs(k.change_pct or 0)
        recs.append(KPIRecommendation(
            priority="medium",
            kpi=k.column,
            issue=f"{k.label} is trending down {pct:.1f}% vs historical baseline",
            action="Analyse contributing factors and assess if intervention is required.",
        ))

    for k in high_std:
        cv = k.std / abs(k.mean) * 100
        recs.append(KPIRecommendation(
            priority="low",
            kpi=k.column,
            issue=f"{k.label} has high variability (CV={cv:.0f}%)",
            action="Consider smoothing or aggregating this metric to reduce noise in reporting.",
        ))

    if not recs:
        recs.append(KPIRecommendation(
            priority="low",
            kpi="all",
            issue="All KPIs are within normal bounds",
            action="Continue monitoring. Set up automated alerts to be notified of future breaches.",
        ))

    # Cap and sort
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recs.sort(key=lambda r: priority_order[r.priority])
    return recs[:20]


class KPIMonitorService:
    """Deterministic, cache-backed KPI monitor."""

    def __init__(self, cache_ttl: int = 3600, cache_max_entries: int = 64) -> None:
        self._cache: TTLCache[str, KPIMonitorResponse] = TTLCache(
            ttl_seconds=cache_ttl, max_entries=cache_max_entries
        )

    def _cache_key(self, dataset_id: str) -> str:
        return dataset_cache_key(dataset_id)

    def monitor(self, df: pd.DataFrame, dataset_id: str, max_kpis: int = 12) -> KPIMonitorResponse:
        key = self._cache_key(dataset_id)
        cached = self._cache.get(key)
        if cached is not None:
            return KPIMonitorResponse(**{**cached.model_dump(), "cache_hit": True})

        t0 = time.perf_counter()
        row_count = len(df)

        time_col = _detect_time_column(df)
        time_labels: Optional[pd.Series] = None
        if time_col:
            try:
                time_labels = pd.to_datetime(df[time_col], errors="coerce").dt.strftime("%Y-%m-%d")
            except Exception:
                time_labels = df[time_col].astype(str)

        # Select numeric columns, excluding the time column
        numeric_cols = [
            c for c in df.select_dtypes(include="number").columns
            if c != time_col
        ][:max_kpis]

        all_kpis: list[KPIStat] = []
        all_alerts: list[KPIAlert] = []

        for col in numeric_cols:
            kpi, alerts = _analyse_kpi(col, df[col], time_labels, row_count)
            all_kpis.append(kpi)
            all_alerts.extend(alerts)

        # Sort alerts by severity then z (approximated by |value - mean| / std)
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_alerts.sort(key=lambda a: (sev_order[a.severity], a.row_index))
        all_alerts = all_alerts[:_MAX_ALERTS]

        healthy_count = sum(1 for k in all_kpis if k.health == "healthy")
        warning_count = sum(1 for k in all_kpis if k.health == "warning")
        critical_count = sum(1 for k in all_kpis if k.health == "critical")

        overall_health: Literal["healthy", "warning", "critical", "unknown"] = (
            "critical" if critical_count > 0 else
            "warning" if warning_count > 0 else
            "healthy" if healthy_count > 0 else
            "unknown"
        )

        recommendations = _build_recommendations(all_kpis)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        result = KPIMonitorResponse(
            dataset_id=dataset_id,
            overall_health=overall_health,
            healthy_count=healthy_count,
            warning_count=warning_count,
            critical_count=critical_count,
            kpis=all_kpis,
            alerts=all_alerts,
            recommendations=recommendations,
            time_column=time_col,
            row_count=row_count,
            analysis_time_ms=elapsed_ms,
            cache_hit=False,
        )
        self._cache.put(key, result)
        return result
