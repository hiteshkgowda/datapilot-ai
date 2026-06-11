"""Visualization service: deterministic Plotly chart generation.

The LLM only contributes an advisory ``chart_type`` on the query plan. This
service decides the *actual* chart type (with compatibility checks and
fallbacks) and builds the figure as pure JSON via Plotly's graph objects.

The figure is a deterministic function of the already-validated, already-
computed analytics result — there is no ``eval``, no ``exec``, and nothing the
model authored ever reaches Plotly.
"""

from __future__ import annotations

import json
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from starlette.concurrency import run_in_threadpool

from app.schemas.chart import ChartRecommendation, ChartResponse, ChartType
from app.schemas.query import Operation, QueryPlan
from app.services.analytics_service import AnalyticsService, ExecutionResult

# Above this many categories a pie chart becomes unreadable; fall back to bar.
_MAX_PIE_SLICES = 12


class VisualizationService:
    """Turn a natural-language question into an answer, a table and a chart."""

    def __init__(
        self, analytics: AnalyticsService, max_pie_slices: int = _MAX_PIE_SLICES
    ) -> None:
        self._analytics = analytics
        self._max_pie_slices = max_pie_slices

    async def create_chart(self, dataset_id: str, question: str) -> ChartResponse:
        """Run analytics, then deterministically build a chart if applicable."""
        analysis = await self._analytics.analyze(dataset_id, question)
        result = analysis.result

        recommendation = self._recommend(result, analysis.plan)
        chart_type: Optional[ChartType] = None
        chart_spec: Optional[dict] = None
        if recommendation is not None:
            chart_type = recommendation.chart_type
            chart_spec = await run_in_threadpool(
                self._build_figure, result, recommendation
            )

        return ChartResponse(
            answer=result.answer,
            table_data=result.table,
            chart_type=chart_type,
            chart_spec=chart_spec,
            execution_time_ms=analysis.execution_time_ms,
            total_time_ms=analysis.total_time_ms,
        )

    async def build_chart(
        self, result: ExecutionResult, plan: QueryPlan
    ) -> Optional[tuple[ChartType, dict]]:
        """Build a chart for an already-computed result (no LLM, no analyze).

        Returns ``(chart_type, chart_spec)`` or ``None`` if not chartable.
        Used by report generation to reuse the deterministic figure builder.
        """
        recommendation = self._recommend(result, plan)
        if recommendation is None:
            return None
        chart_spec = await run_in_threadpool(
            self._build_figure, result, recommendation
        )
        return recommendation.chart_type, chart_spec

    # ------------------------------------------------------------------ #
    # Chart-type resolution (deterministic)
    # ------------------------------------------------------------------ #
    def _recommend(
        self, result: ExecutionResult, plan: QueryPlan
    ) -> Optional[ChartRecommendation]:
        """Decide the final chart type, or ``None`` if the result isn't chartable."""
        # Scalar results (no axes) and empty results are not chartable.
        if result.x_field is None or result.y_field is None or not result.table:
            return None

        # A scatter selection is inherently x/y; force scatter regardless of
        # the model's recommendation.
        if plan.operation is Operation.XY_SELECT:
            return ChartRecommendation(
                chart_type=ChartType.SCATTER,
                x_field=result.x_field,
                y_field=result.y_field,
            )

        # Grouped results: honour the recommendation when usable, else default
        # to a bar chart.
        candidate = (
            plan.chart_type
            if plan.chart_type in set(ChartType)
            else ChartType.BAR
        )
        # A pie with too many slices is unreadable.
        if candidate is ChartType.PIE and len(result.table) > self._max_pie_slices:
            candidate = ChartType.BAR

        return ChartRecommendation(
            chart_type=candidate,
            x_field=result.x_field,
            y_field=result.y_field,
        )

    # ------------------------------------------------------------------ #
    # Figure building (pure; no LLM, no eval)
    # ------------------------------------------------------------------ #
    def _build_figure(
        self, result: ExecutionResult, recommendation: ChartRecommendation
    ) -> dict:
        """Build a Plotly figure and return it as a JSON-safe dict."""
        frame = pd.DataFrame(result.table)
        x_field, y_field = recommendation.x_field, recommendation.y_field
        chart_type = recommendation.chart_type

        if chart_type is ChartType.PIE:
            figure = go.Figure(
                go.Pie(labels=frame[x_field], values=frame[y_field])
            )
        elif chart_type is ChartType.LINE:
            ordered = frame.sort_values(by=x_field)
            figure = go.Figure(
                go.Scatter(
                    x=ordered[x_field],
                    y=ordered[y_field],
                    mode="lines+markers",
                )
            )
        elif chart_type is ChartType.SCATTER:
            figure = go.Figure(
                go.Scatter(x=frame[x_field], y=frame[y_field], mode="markers")
            )
        else:  # ChartType.BAR (and the default fallback)
            figure = go.Figure(go.Bar(x=frame[x_field], y=frame[y_field]))

        figure.update_layout(
            title=f"{y_field} by {x_field}",
            xaxis_title=x_field,
            yaxis_title=y_field,
            template="plotly_white",
            margin={"l": 40, "r": 20, "t": 50, "b": 40},
        )
        # pio.to_json handles numpy types and yields valid JSON; parse back to a
        # plain dict so it serializes cleanly through FastAPI.
        return json.loads(pio.to_json(figure))
