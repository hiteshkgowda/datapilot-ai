"""Deterministic forecasting and anomaly-detection models.

Prefers statsmodels (Holt-Winters, STL) when available and the series is long
enough, otherwise degrades through a numpy-only chain (linear OLS, naive,
rolling z-score). Every path is deterministic and records the method used.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

try:  # statsmodels is optional — a numpy fallback always exists.
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    from statsmodels.tsa.seasonal import STL

    STATSMODELS_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the platform
    STATSMODELS_AVAILABLE = False

_Z = 1.96  # ~95% interval


@dataclass(frozen=True)
class ForecastOutput:
    forecast: list[float]
    lower: list[float]
    upper: list[float]
    method_used: str
    fallback_used: bool


@dataclass(frozen=True)
class AnomalyOutput:
    flags: list[bool]
    method_used: str
    fallback_used: bool


def forecast_series(
    values: np.ndarray, horizon: int, seasonal_periods: int
) -> ForecastOutput:
    """Forecast ``horizon`` future points, degrading through a model chain."""
    series = np.asarray(values, dtype=float)
    n = series.size

    candidates: list[str] = []
    if STATSMODELS_AVAILABLE and seasonal_periods >= 2 and n >= 2 * seasonal_periods:
        candidates.append("holt_winters_seasonal")
    if STATSMODELS_AVAILABLE and n >= 4:
        candidates.append("holt_winters")
    if n >= 3:
        candidates.append("linear")
    candidates.append("naive")

    for method in candidates:
        try:
            forecast, fitted = _fit_forecast(method, series, horizon, seasonal_periods)
        except Exception:
            continue
        residuals = series - fitted
        sigma = float(np.std(residuals, ddof=1)) if n > 1 else 0.0
        margin = _Z * sigma
        fallback_used = method != candidates[0] or not STATSMODELS_AVAILABLE
        return ForecastOutput(
            forecast=[float(v) for v in forecast],
            lower=[float(v - margin) for v in forecast],
            upper=[float(v + margin) for v in forecast],
            method_used=method,
            fallback_used=fallback_used,
        )
    # Unreachable: "naive" never raises.
    raise RuntimeError("No forecast method succeeded.")


def detect_anomalies(
    values: np.ndarray, sensitivity: float, seasonal_periods: int
) -> AnomalyOutput:
    """Flag anomalous points using STL/MAD, or a rolling z-score fallback."""
    series = np.asarray(values, dtype=float)
    n = series.size

    residuals = None
    method = "rolling_zscore"
    fallback_used = True
    if STATSMODELS_AVAILABLE and seasonal_periods >= 2 and n >= 2 * seasonal_periods:
        try:
            stl = STL(series, period=seasonal_periods, robust=True).fit()
            residuals = np.asarray(stl.resid, dtype=float)
            method = "stl_mad"
            fallback_used = False
        except Exception:
            residuals = None

    if residuals is None:
        window = max(3, min(7, n // 2 if n // 2 >= 3 else 3))
        rolling_mean = (
            pd.Series(series).rolling(window, min_periods=1, center=True).mean()
        )
        residuals = series - rolling_mean.to_numpy()

    median = float(np.median(residuals))
    mad = float(np.median(np.abs(residuals - median)))
    scale = mad * 1.4826 if mad > 0 else (float(np.std(residuals)) or 1.0)
    scores = np.abs(residuals - median) / scale
    flags = scores > sensitivity
    return AnomalyOutput(
        flags=[bool(v) for v in flags],
        method_used=method,
        fallback_used=fallback_used,
    )


# --------------------------------------------------------------------------- #
# Per-method fits (return forecast + in-sample fitted values)
# --------------------------------------------------------------------------- #
def _fit_forecast(
    method: str, series: np.ndarray, horizon: int, seasonal_periods: int
) -> tuple[np.ndarray, np.ndarray]:
    if method == "holt_winters_seasonal":
        model = ExponentialSmoothing(
            series,
            trend="add",
            seasonal="add",
            seasonal_periods=seasonal_periods,
            initialization_method="estimated",
        ).fit()
        return np.asarray(model.forecast(horizon)), np.asarray(model.fittedvalues)

    if method == "holt_winters":
        model = ExponentialSmoothing(
            series, trend="add", seasonal=None, initialization_method="estimated"
        ).fit()
        return np.asarray(model.forecast(horizon)), np.asarray(model.fittedvalues)

    if method == "linear":
        x = np.arange(series.size)
        slope, intercept = np.polyfit(x, series, 1)
        fitted = slope * x + intercept
        future_x = np.arange(series.size, series.size + horizon)
        return slope * future_x + intercept, fitted

    if method == "naive":
        last = series[-1]
        forecast = np.full(horizon, last, dtype=float)
        # Naive in-sample fit: each point predicted by its predecessor.
        fitted = np.concatenate(([series[0]], series[:-1]))
        return forecast, fitted

    raise ValueError(f"Unknown method '{method}'.")
