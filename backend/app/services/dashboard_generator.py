"""AI Executive Dashboard Generator.

Architecture
------------
Four deterministic engines + one optional LLM call for naming/recommendations.

KPISelectionEngine         — pure pandas/numpy; no LLM; picks headline metrics
ChartRecommendationEngine  — pure pandas + Plotly; no LLM; builds chart specs
LayoutRecommendationEngine — pure logic; arranges KPIs and charts in a grid
DashboardScoringEngine     — pure logic; 0–100 quality score

DashboardGeneratorService  — orchestrates the four engines, calls LLM once for
                             dashboard name + recommendation text (with fallback),
                             and manages a TTL response cache.

Security
--------
- No eval(), no exec(), no raw LLM-generated SQL anywhere.
- All Plotly chart_spec values are built server-side from validated column names
  sourced from DatasetMetadata. Nothing from the LLM reaches a chart spec.
- LLM output is used only for two string fields: dashboard_name (str) and
  recommendations (list[str]). Both have deterministic fallbacks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from starlette.concurrency import run_in_threadpool

from app.core.cache import TTLCache
from app.core.config import Settings
from app.schemas.dashboard import (
    ChartPanel,
    DashboardConfig,
    GenerateDashboardRequest,
    KPIMetric,
    LayoutCell,
    LayoutConfig,
)
from app.services.dataset_service import DatasetService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword scoring tables for KPI selection
# ---------------------------------------------------------------------------

_HIGH_KW: frozenset[str] = frozenset(
    {
        "revenue", "sales", "profit", "income", "earnings", "arr", "mrr", "gmv",
        "gross", "net", "margin", "booking", "billings", "pipeline", "deals",
    }
)
_MED_KW: frozenset[str] = frozenset(
    {
        "users", "customers", "orders", "count", "total", "amount", "rate",
        "conversion", "retention", "churn", "growth", "cost", "spend", "volume",
        "quantity", "units", "transactions", "sessions", "visits", "clicks",
        "impressions", "cac", "ltv", "arpu", "nps", "score", "value",
    }
)

# Columns whose names match these are likely to be IDs/keys, not metrics.
_EXCLUDE_KW: frozenset[str] = frozenset({"id", "key", "index", "row", "seq", "num"})

_MAX_CHART_ROWS_BAR = 50       # cap categories for bar charts
_MAX_CHART_ROWS_SCATTER = 500  # cap points for scatter charts
_MAX_CHART_ROWS_LINE = 500     # cap points for line charts
_MAX_PIE_SLICES = 12
_SAMPLE_ROWS = 5_000           # max rows fed to engines


# ---------------------------------------------------------------------------
# KPI Selection Engine
# ---------------------------------------------------------------------------


class KPISelectionEngine:
    """Deterministic engine: picks the most business-relevant numeric columns.

    All scoring is based on column *names* and basic statistics.
    No LLM call, no eval.
    """

    def select(
        self, df: pd.DataFrame, max_kpis: int = 6
    ) -> list[KPIMetric]:
        """Return up to ``max_kpis`` KPI metrics ranked by relevance score."""
        if df.empty:
            return []

        df = df.head(_SAMPLE_ROWS)

        # Coerce object columns that look numeric.
        for col in df.select_dtypes(include=["object", "string"]).columns:
            coerced = pd.to_numeric(df[col], errors="coerce")
            if coerced.notna().any():
                df = df.copy()
                df[col] = coerced

        numeric_cols = [
            c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
        ]
        if not numeric_cols:
            return []

        scored: list[tuple[float, str]] = []
        for col in numeric_cols:
            scored.append((_score_column(df, col), col))

        scored.sort(key=lambda t: t[0], reverse=True)
        selected = [col for _, col in scored[:max_kpis] if _ > -999]

        kpis: list[KPIMetric] = []
        for idx, col in enumerate(selected):
            metric = _build_kpi(df, col, idx)
            if metric is not None:
                kpis.append(metric)

        return kpis[:max_kpis]


def _score_column(df: pd.DataFrame, col: str) -> float:
    """Score a numeric column 0–4 by keyword match + variance + null penalty."""
    name_lower = col.lower()

    # Hard exclude: ID / key / index columns.
    if any(kw in name_lower for kw in _EXCLUDE_KW):
        return -999.0

    # Keyword score.
    if any(kw in name_lower for kw in _HIGH_KW):
        kw_score = 2.0
    elif any(kw in name_lower for kw in _MED_KW):
        kw_score = 1.0
    else:
        kw_score = 0.0

    # Variance score: exclude near-constant columns (std/mean < 1%).
    series = df[col].dropna()
    if series.empty:
        return -999.0
    mean_abs = abs(float(series.mean()))
    std_val = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    cv = std_val / mean_abs if mean_abs > 0 else 0.0
    variance_score = 1.0 if cv > 0.01 else 0.0

    # Null penalty.
    null_ratio = float(df[col].isna().sum()) / max(len(df), 1)
    null_penalty = -1.0 if null_ratio > 0.30 else 0.0

    return kw_score + variance_score + null_penalty


def _build_kpi(df: pd.DataFrame, col: str, idx: int) -> Optional[KPIMetric]:
    """Build a KPIMetric for one column; returns None if data is insufficient."""
    series = df[col].dropna()
    if series.empty:
        return None

    name_lower = col.lower()
    use_sum = any(kw in name_lower for kw in _HIGH_KW | {"count", "total", "amount", "volume", "units", "orders"})
    agg = "sum" if use_sum else "mean"
    value = float(series.sum()) if agg == "sum" else float(series.mean())

    if not np.isfinite(value):
        return None

    # Change % — compare first 50% of rows vs last 50%.
    change_pct: Optional[float] = None
    trend = "flat"
    if len(series) >= 4:
        mid = len(series) // 2
        first_half = float(series.iloc[:mid].mean())
        second_half = float(series.iloc[mid:].mean())
        if first_half != 0 and np.isfinite(first_half) and np.isfinite(second_half):
            change_pct = round((second_half - first_half) / abs(first_half) * 100.0, 2)
            if change_pct > 1.0:
                trend = "up"
            elif change_pct < -1.0:
                trend = "down"

    label = col.replace("_", " ").title()

    return KPIMetric(
        id=f"kpi_{idx}",
        label=label,
        column=col,
        aggregation=agg,
        value=round(value, 4),
        formatted_value=_format_value(value, col),
        change_pct=change_pct,
        trend=trend,
    )


def _format_value(value: float, col_name: str) -> str:
    """Format a numeric value as a human-readable string."""
    name_lower = col_name.lower()
    is_pct = any(k in name_lower for k in ("pct", "rate", "ratio", "percent", "percentage"))
    is_currency = any(
        k in name_lower
        for k in ("revenue", "sales", "profit", "cost", "spend", "price",
                  "income", "earnings", "arr", "mrr", "gmv", "billing", "amount")
    )

    if is_pct:
        return f"{value:.1f}%"

    prefix = "$" if is_currency else ""
    abs_val = abs(value)
    if abs_val >= 1e9:
        return f"{prefix}{value / 1e9:.2f}B"
    elif abs_val >= 1e6:
        return f"{prefix}{value / 1e6:.2f}M"
    elif abs_val >= 1e3:
        return f"{prefix}{value / 1e3:.1f}K"
    else:
        return f"{prefix}{value:,.2f}"


# ---------------------------------------------------------------------------
# Chart Recommendation Engine
# ---------------------------------------------------------------------------


class ChartRecommendationEngine:
    """Deterministic engine: picks chart type and builds Plotly figure JSON.

    Decision rules (precedence order):
      1. datetime column + numeric column → line chart
      2. low-cardinality string column (≤ _MAX_PIE_SLICES unique) + numeric → bar
      3. two numeric columns → scatter
      4. fallback → bar with row index on x-axis

    Plotly specs are built entirely server-side using go.Figure.
    Nothing from the LLM ever reaches a chart spec.
    """

    def recommend(
        self, df: pd.DataFrame, kpis: list[KPIMetric], max_charts: int = 6
    ) -> list[ChartPanel]:
        """Return up to ``max_charts`` chart panels with Plotly specs."""
        if df.empty or not kpis:
            return []

        df = df.head(_SAMPLE_ROWS)

        datetime_cols = _detect_datetime_cols(df)
        string_cols = [
            c for c in df.columns
            if df[c].dtype == object and c not in [k.column for k in kpis]
        ]
        low_card_cols = [
            c for c in string_cols
            if df[c].nunique() <= _MAX_PIE_SLICES
        ]
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

        panels: list[ChartPanel] = []
        seen_xy: set[tuple[str, str]] = set()

        for kpi_idx, kpi in enumerate(kpis):
            if len(panels) >= max_charts:
                break

            y_col = kpi.column
            panel = self._pick_chart(
                df, y_col, kpi_idx, datetime_cols, low_card_cols, numeric_cols, seen_xy
            )
            if panel is not None:
                panels.append(panel)

        return panels

    def _pick_chart(
        self,
        df: pd.DataFrame,
        y_col: str,
        idx: int,
        datetime_cols: list[str],
        low_card_cols: list[str],
        numeric_cols: list[str],
        seen_xy: set[tuple[str, str]],
    ) -> Optional[ChartPanel]:
        # Rule 1: time series
        if datetime_cols:
            x_col = datetime_cols[0]
            key = (x_col, y_col)
            if key not in seen_xy:
                seen_xy.add(key)
                spec = _build_figure(df, "line", x_col, y_col)
                if spec:
                    return ChartPanel(
                        id=f"chart_{idx}",
                        title=f"{y_col.replace('_', ' ').title()} Over Time",
                        chart_type="line",
                        x_field=x_col,
                        y_field=y_col,
                        chart_spec=spec,
                        width="half",
                    )

        # Rule 2: categorical breakdown
        if low_card_cols:
            x_col = low_card_cols[0]
            key = (x_col, y_col)
            if key not in seen_xy:
                seen_xy.add(key)
                spec = _build_figure(df, "bar", x_col, y_col)
                if spec:
                    return ChartPanel(
                        id=f"chart_{idx}",
                        title=f"{y_col.replace('_', ' ').title()} by {x_col.replace('_', ' ').title()}",
                        chart_type="bar",
                        x_field=x_col,
                        y_field=y_col,
                        chart_spec=spec,
                        width="half",
                    )

        # Rule 3: scatter against another numeric
        other_numerics = [c for c in numeric_cols if c != y_col]
        if other_numerics:
            x_col = other_numerics[0]
            key = (x_col, y_col)
            if key not in seen_xy:
                seen_xy.add(key)
                spec = _build_figure(df, "scatter", x_col, y_col)
                if spec:
                    return ChartPanel(
                        id=f"chart_{idx}",
                        title=f"{y_col.replace('_', ' ').title()} vs {x_col.replace('_', ' ').title()}",
                        chart_type="scatter",
                        x_field=x_col,
                        y_field=y_col,
                        chart_spec=spec,
                        width="half",
                    )

        # Rule 4: fallback bar with row index
        x_col = "__row__"
        key = (x_col, y_col)
        if key not in seen_xy:
            seen_xy.add(key)
            spec = _build_figure(df, "bar", None, y_col)
            if spec:
                return ChartPanel(
                    id=f"chart_{idx}",
                    title=y_col.replace("_", " ").title(),
                    chart_type="bar",
                    x_field="row",
                    y_field=y_col,
                    chart_spec=spec,
                    width="half",
                )

        return None


def _detect_datetime_cols(df: pd.DataFrame) -> list[str]:
    """Return column names that are datetime-typed or parseable as dates."""
    dt_cols: list[str] = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            dt_cols.append(col)
            continue
        if df[col].dtype == object:
            name_lower = col.lower()
            if any(k in name_lower for k in ("date", "time", "month", "year", "period", "week", "day", "quarter")):
                try:
                    parsed = pd.to_datetime(df[col], errors="coerce")
                    if parsed.notna().sum() / max(len(df), 1) > 0.7:
                        dt_cols.append(col)
                except Exception:
                    pass
    return dt_cols


def _build_figure(
    df: pd.DataFrame,
    chart_type: str,
    x_col: Optional[str],
    y_col: str,
) -> Optional[dict[str, Any]]:
    """Build a Plotly figure and return it as a JSON-safe dict.

    Returns None if the data is insufficient to render the chart.
    No eval(), no exec().  All data values come from the pandas DataFrame.
    """
    try:
        y_series = pd.to_numeric(df[y_col], errors="coerce").dropna()
        if y_series.empty:
            return None

        if chart_type == "line":
            assert x_col is not None
            frame = df[[x_col, y_col]].dropna().head(_MAX_CHART_ROWS_LINE)
            try:
                frame = frame.sort_values(by=x_col)
            except Exception:
                pass
            fig = go.Figure(
                go.Scatter(
                    x=frame[x_col].astype(str),
                    y=pd.to_numeric(frame[y_col], errors="coerce"),
                    mode="lines+markers",
                )
            )
            fig.update_layout(
                title=f"{y_col.replace('_', ' ').title()} Over Time",
                xaxis_title=x_col,
                yaxis_title=y_col,
                template="plotly_white",
                margin={"l": 40, "r": 20, "t": 50, "b": 40},
            )

        elif chart_type == "scatter":
            assert x_col is not None
            frame = df[[x_col, y_col]].dropna().head(_MAX_CHART_ROWS_SCATTER)
            fig = go.Figure(
                go.Scatter(
                    x=pd.to_numeric(frame[x_col], errors="coerce"),
                    y=pd.to_numeric(frame[y_col], errors="coerce"),
                    mode="markers",
                )
            )
            fig.update_layout(
                title=f"{y_col.replace('_', ' ').title()} vs {x_col.replace('_', ' ').title()}",
                xaxis_title=x_col,
                yaxis_title=y_col,
                template="plotly_white",
                margin={"l": 40, "r": 20, "t": 50, "b": 40},
            )

        else:
            # bar (with x_col or row index)
            if x_col and x_col in df.columns:
                frame = (
                    df[[x_col, y_col]]
                    .dropna()
                    .groupby(x_col, sort=False)[y_col]
                    .sum()
                    .reset_index()
                    .head(_MAX_CHART_ROWS_BAR)
                )
                x_vals = frame[x_col].astype(str)
                y_vals = pd.to_numeric(frame[y_col], errors="coerce")
                x_title = x_col
            else:
                # row index fallback
                sub = df[[y_col]].head(_MAX_CHART_ROWS_BAR).copy()
                sub[y_col] = pd.to_numeric(sub[y_col], errors="coerce")
                sub = sub.dropna()
                x_vals = pd.Series(range(len(sub)), dtype=int).astype(str)
                y_vals = sub[y_col]
                x_title = "row"

            fig = go.Figure(go.Bar(x=x_vals, y=y_vals))
            fig.update_layout(
                title=y_col.replace("_", " ").title(),
                xaxis_title=x_title,
                yaxis_title=y_col,
                template="plotly_white",
                margin={"l": 40, "r": 20, "t": 50, "b": 40},
            )

        return json.loads(pio.to_json(fig))

    except Exception as exc:
        logger.warning("_build_figure: could not build %s chart for '%s': %s", chart_type, y_col, exc)
        return None


# ---------------------------------------------------------------------------
# Layout Recommendation Engine
# ---------------------------------------------------------------------------


class LayoutRecommendationEngine:
    """Deterministic engine: packs KPIs and charts into a grid layout.

    KPI row:  all KPIs side-by-side in a 4-column grid at the top.
    Charts:   packed into rows of two (half-width each).
              Odd chart out → full-width on its own row.
    """

    def arrange(
        self, kpis: list[KPIMetric], charts: list[ChartPanel]
    ) -> LayoutConfig:
        kpi_row = [kpi.id for kpi in kpis]

        rows: list[list[LayoutCell]] = []
        remaining = list(charts)
        while remaining:
            if len(remaining) == 1:
                rows.append([LayoutCell(id=remaining[0].id, width="full")])
                remaining = []
            else:
                pair = remaining[:2]
                rows.append([LayoutCell(id=c.id, width="half") for c in pair])
                remaining = remaining[2:]

        return LayoutConfig(kpi_row=kpi_row, rows=rows)


# ---------------------------------------------------------------------------
# Dashboard Scoring Engine
# ---------------------------------------------------------------------------


class DashboardScoringEngine:
    """Deterministic engine: produces a 0–100 quality score.

    Four equal-weight categories (max 25 pts each):
      1. KPI breadth  — how many distinct KPI metrics were found
      2. Chart variety — how many charts could be generated
      3. Column coverage — fraction of numeric columns surfaced as KPIs
      4. Data quality  — row count + null-ratio
    """

    def score(
        self,
        kpis: list[KPIMetric],
        charts: list[ChartPanel],
        df: pd.DataFrame,
    ) -> int:
        # 1. KPI breadth (5 pts per KPI, max 25)
        kpi_score = min(len(kpis), 5) * 5

        # 2. Chart variety (5 pts per chart, max 25)
        chart_score = min(len(charts), 5) * 5

        # 3. Column coverage
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if numeric_cols:
            coverage = len(kpis) / len(numeric_cols)
            coverage_score = int(min(coverage, 1.0) * 25)
        else:
            coverage_score = 0

        # 4. Data quality
        n_rows = len(df)
        row_pts = 15 if n_rows >= 100 else (10 if n_rows >= 20 else 5)
        if not df.empty:
            mean_null_ratio = float(df.isnull().mean().mean())
        else:
            mean_null_ratio = 1.0
        null_pts = 10 if mean_null_ratio < 0.05 else (5 if mean_null_ratio < 0.20 else 0)
        data_score = row_pts + null_pts

        return min(kpi_score + chart_score + coverage_score + data_score, 100)


# ---------------------------------------------------------------------------
# Orchestration service
# ---------------------------------------------------------------------------


class DashboardGeneratorService:
    """Coordinate the four deterministic engines + optional LLM for name/recs.

    The service is the only public API for generating dashboards.
    Uses ``set_client()`` to receive the shared lifespan-managed httpx client.
    """

    def __init__(
        self,
        dataset_service: DatasetService,
        settings: Settings,
        cache_ttl: float = 300.0,
        cache_max_entries: int = 30,
    ) -> None:
        self._datasets = dataset_service
        self._settings = settings
        self._kpi_engine = KPISelectionEngine()
        self._chart_engine = ChartRecommendationEngine()
        self._layout_engine = LayoutRecommendationEngine()
        self._score_engine = DashboardScoringEngine()
        self._cache: TTLCache[str, DashboardConfig] = TTLCache(
            ttl_seconds=cache_ttl,
            max_entries=cache_max_entries,
        )
        self._client: Any = None  # httpx.AsyncClient injected by lifespan

    def set_client(self, client: Any) -> None:
        """Attach the shared HTTP client.  Called once from the app lifespan."""
        self._client = client

    async def generate(
        self,
        request: "GenerateDashboardRequest",
        owner_sub: str,
    ) -> DashboardConfig:
        """Generate a complete dashboard config from a dataset and a prompt.

        Steps:
            1. Check TTL cache.
            2. Load dataset (DatasetService.load_dataframe).
            3. Run 4 deterministic engines (KPI → chart → layout → score).
            4. (Optional) LLM call for dashboard name + recommendations.
            5. Cache and return DashboardConfig.

        Never raises on LLM failure — deterministic fallback always available.
        """
        cache_key = _build_cache_key(request.dataset_id, request.prompt, owner_sub)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("DashboardGeneratorService: cache hit %.8s", cache_key)
            return cached.model_copy(update={"cache_hit": True})

        start = time.perf_counter()

        df, meta = await run_in_threadpool(
            self._datasets.load_dataframe, request.dataset_id
        )
        # Safety cap: engines process at most SAMPLE_ROWS rows.
        if len(df) > _SAMPLE_ROWS:
            df = df.head(_SAMPLE_ROWS)

        # Deterministic engines.
        kpis = await run_in_threadpool(
            self._kpi_engine.select, df, request.max_kpis
        )
        charts = await run_in_threadpool(
            self._chart_engine.recommend, df, kpis, request.max_charts
        )
        layout = await run_in_threadpool(self._layout_engine.arrange, kpis, charts)
        score = await run_in_threadpool(self._score_engine.score, kpis, charts, df)

        # Optional LLM: dashboard name + recommendations.
        dashboard_name, recommendations = await self._generate_name_and_recs(
            request.prompt,
            meta.filename,
            kpis,
        )

        elapsed_ms = round((time.perf_counter() - start) * 1000, 3)

        config = DashboardConfig(
            dashboard_name=dashboard_name,
            dataset_id=request.dataset_id,
            owner_sub=owner_sub,
            kpis=kpis,
            charts=charts,
            layout=layout,
            recommendations=recommendations,
            score=score,
            generation_time_ms=elapsed_ms,
            cache_hit=False,
        )

        self._cache.put(cache_key, config)
        logger.info(
            "DashboardGeneratorService: generated '%s' in %.1f ms "
            "(kpis=%d, charts=%d, score=%d) for dataset %s",
            dashboard_name,
            elapsed_ms,
            len(kpis),
            len(charts),
            score,
            request.dataset_id,
        )
        return config

    # ------------------------------------------------------------------ #
    # LLM helpers
    # ------------------------------------------------------------------ #

    async def _generate_name_and_recs(
        self,
        prompt: str,
        dataset_filename: str,
        kpis: list[KPIMetric],
    ) -> tuple[str, list[str]]:
        """Try LLM for dashboard name + recommendations; fall back if any error."""
        if self._client is None or not kpis:
            return _fallback_name(prompt, dataset_filename), _fallback_recs(kpis)

        try:
            if self._settings.groq_api_key:
                return await self._call_groq(prompt, dataset_filename, kpis)
            else:
                return await self._call_ollama(prompt, dataset_filename, kpis)
        except Exception as exc:
            logger.warning(
                "DashboardGeneratorService: LLM call failed (%s) — using fallback.", exc
            )
            return _fallback_name(prompt, dataset_filename), _fallback_recs(kpis)

    async def _call_groq(
        self,
        prompt: str,
        filename: str,
        kpis: list[KPIMetric],
    ) -> tuple[str, list[str]]:
        kpi_summary = ", ".join(
            f"{k.label} = {k.formatted_value} ({k.trend})" for k in kpis[:6]
        )
        user_msg = (
            f"Dataset: {filename}\n"
            f"User request: {prompt}\n"
            f"Top KPIs: {kpi_summary}\n\n"
            'Return ONLY valid JSON: {"name": "...", "recommendations": ["...", "..."]}'
        )
        system_msg = (
            "You are a BI dashboard naming assistant. "
            "Return ONLY a JSON object with two keys: "
            '"name" (a concise dashboard title, max 8 words) and '
            '"recommendations" (a list of 2-4 short actionable insight strings, '
            "each grounded in the KPI data provided). "
            "No markdown. No explanation."
        )
        payload: dict[str, Any] = {
            "model": self._settings.groq_model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 256,
        }
        resp = await self._client.post(
            f"{self._settings.groq_base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self._settings.groq_api_key}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        raw = str(resp.json()["choices"][0]["message"]["content"])
        return _parse_llm_output(raw, prompt, filename, kpis)

    async def _call_ollama(
        self,
        prompt: str,
        filename: str,
        kpis: list[KPIMetric],
    ) -> tuple[str, list[str]]:
        kpi_summary = ", ".join(
            f"{k.label} = {k.formatted_value} ({k.trend})" for k in kpis[:6]
        )
        user_msg = (
            f"Dataset: {filename}\n"
            f"User request: {prompt}\n"
            f"Top KPIs: {kpi_summary}\n\n"
            'Return ONLY valid JSON: {"name": "...", "recommendations": ["...", "..."]}'
        )
        payload: dict[str, Any] = {
            "model": self._settings.ollama_model,
            "messages": [
                {"role": "system", "content": "You are a BI dashboard naming assistant. Return ONLY valid JSON with keys 'name' and 'recommendations'."},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
        resp = await self._client.post(
            f"{self._settings.ollama_base_url}/api/chat",
            json=payload,
        )
        resp.raise_for_status()
        raw = str(resp.json()["message"]["content"])
        return _parse_llm_output(raw, prompt, filename, kpis)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_llm_output(
    raw: str,
    prompt: str,
    filename: str,
    kpis: list[KPIMetric],
) -> tuple[str, list[str]]:
    """Parse LLM JSON; fall back on any error."""
    try:
        data: dict[str, Any] = json.loads(raw)
        name = str(data.get("name", "")).strip()
        recs_raw = data.get("recommendations", [])
        recs = [str(r).strip() for r in recs_raw if r] if isinstance(recs_raw, list) else []
        if not name:
            name = _fallback_name(prompt, filename)
        if not recs:
            recs = _fallback_recs(kpis)
        return name, recs
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning("DashboardGeneratorService: LLM JSON parse failed: %s", exc)
        return _fallback_name(prompt, filename), _fallback_recs(kpis)


def _fallback_name(prompt: str, filename: str) -> str:
    """Deterministic dashboard name from prompt + filename."""
    clean = prompt.strip().rstrip("?!.")
    base = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()
    if clean.lower().startswith("create"):
        return f"{clean[6:].strip().title()} — {base}" if len(clean) > 6 else f"Executive Dashboard — {base}"
    return f"{clean.title()} — {base}"


def _fallback_recs(kpis: list[KPIMetric]) -> list[str]:
    """Build simple trend-based recommendation strings from KPI data."""
    recs: list[str] = []
    for kpi in kpis[:4]:
        if kpi.trend == "up" and kpi.change_pct is not None:
            recs.append(
                f"{kpi.label} is up {kpi.change_pct:.1f}% — investigate drivers of growth."
            )
        elif kpi.trend == "down" and kpi.change_pct is not None:
            recs.append(
                f"{kpi.label} is down {abs(kpi.change_pct):.1f}% — review recent changes."
            )
        elif kpi.trend == "flat":
            recs.append(f"{kpi.label} is stable at {kpi.formatted_value}.")
    return recs if recs else [f"Monitor {kpis[0].label} — currently {kpis[0].formatted_value}."] if kpis else []


def _build_cache_key(dataset_id: str, prompt: str, owner_sub: str) -> str:
    raw = f"{dataset_id}\x00{prompt.strip().lower()}\x00{owner_sub}"
    return hashlib.sha256(raw.encode()).hexdigest()
