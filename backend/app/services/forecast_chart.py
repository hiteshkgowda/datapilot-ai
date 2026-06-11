"""Deterministic Plotly figures for forecasting and anomaly detection.

Returns figure JSON (the same ``chart_spec`` shape as Phase 3) so the frontend
and the PDF report renderer can consume it unchanged.
"""

from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio


def _to_dict(figure: go.Figure) -> dict:
    return json.loads(pio.to_json(figure))


def forecast_figure(
    history: pd.Series,
    future_index: pd.DatetimeIndex,
    forecast: list[float],
    lower: list[float],
    upper: list[float],
    value_name: str,
) -> dict:
    """History (solid) + forecast (dashed) + shaded confidence band."""
    hist_x = [ts.isoformat() for ts in history.index]
    fut_x = [ts.isoformat() for ts in future_index]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(x=hist_x, y=list(history.values), mode="lines", name="history")
    )
    # Confidence band (upper then lower with fill).
    figure.add_trace(
        go.Scatter(
            x=fut_x, y=upper, mode="lines", line={"width": 0},
            showlegend=False, hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=fut_x, y=lower, mode="lines", line={"width": 0},
            fill="tonexty", fillcolor="rgba(31,119,180,0.2)",
            name="confidence", hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=fut_x, y=forecast, mode="lines+markers",
            line={"dash": "dash"}, name="forecast",
        )
    )
    figure.update_layout(
        title=f"Forecast of {value_name}",
        xaxis_title="date",
        yaxis_title=value_name,
        template="plotly_white",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return _to_dict(figure)


def anomaly_figure(series: pd.Series, flags: list[bool], value_name: str) -> dict:
    """Series line with anomalous points marked in red."""
    x = [ts.isoformat() for ts in series.index]
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=x, y=list(series.values), mode="lines", name=value_name))
    anomaly_x = [x[i] for i, flag in enumerate(flags) if flag]
    anomaly_y = [series.values[i] for i, flag in enumerate(flags) if flag]
    if anomaly_x:
        figure.add_trace(
            go.Scatter(
                x=anomaly_x, y=anomaly_y, mode="markers", name="anomaly",
                marker={"color": "red", "size": 10, "symbol": "x"},
            )
        )
    figure.update_layout(
        title=f"Anomalies in {value_name}",
        xaxis_title="date",
        yaxis_title=value_name,
        template="plotly_white",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return _to_dict(figure)


def timeseries_figure(series: pd.Series, value_name: str) -> dict:
    """A plain aggregated time-series line."""
    x = [ts.isoformat() for ts in series.index]
    figure = go.Figure(go.Scatter(x=x, y=list(series.values), mode="lines+markers"))
    figure.update_layout(
        title=f"{value_name} over time",
        xaxis_title="date",
        yaxis_title=value_name,
        template="plotly_white",
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
    )
    return _to_dict(figure)
