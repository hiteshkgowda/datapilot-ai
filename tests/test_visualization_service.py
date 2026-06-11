"""Unit tests for the visualization service.

These tests verify deterministic chart generation using a *mocked* analytics
layer, so they require neither Ollama nor a real dataset on disk.
"""

from __future__ import annotations

import asyncio

from app.schemas.chart import ChartType
from app.schemas.query import Operation, QueryPlan
from app.services.analytics_service import AnalysisResult, ExecutionResult
from app.services.visualization_service import VisualizationService


class FakeAnalytics:
    """An analytics stub returning a preset AnalysisResult."""

    def __init__(self, analysis: AnalysisResult) -> None:
        self._analysis = analysis

    async def analyze(self, dataset_id: str, question: str) -> AnalysisResult:
        return self._analysis


def _run(plan: QueryPlan, result: ExecutionResult):
    analysis = AnalysisResult(
        plan=plan, result=result, execution_time_ms=1.0, total_time_ms=2.0
    )
    service = VisualizationService(FakeAnalytics(analysis))
    return asyncio.run(service.create_chart("dataset-1", "?"))


def _grouped_result(rows, key="region", value="sales") -> ExecutionResult:
    table = [{key: k, value: v} for k, v in rows]
    return ExecutionResult(
        answer="ans", table=table, x_field=key, y_field=value
    )


# --------------------------------------------------------------------------- #
# Chart types
# --------------------------------------------------------------------------- #
def test_groupby_sum_bar():
    plan = QueryPlan(
        operation=Operation.GROUPBY_SUM,
        column="sales",
        group_by="region",
        chart_type=ChartType.BAR,
    )
    resp = _run(plan, _grouped_result([("North", 130), ("South", 50)]))
    assert resp.chart_type == ChartType.BAR
    assert resp.chart_spec["data"][0]["type"] == "bar"
    assert resp.table_data  # table always returned


def test_groupby_count_pie():
    plan = QueryPlan(
        operation=Operation.GROUPBY_COUNT,
        group_by="region",
        chart_type=ChartType.PIE,
    )
    resp = _run(
        plan, _grouped_result([("North", 2), ("South", 1)], value="count")
    )
    assert resp.chart_type == ChartType.PIE
    assert resp.chart_spec["data"][0]["type"] == "pie"


def test_line_sorts_x():
    plan = QueryPlan(
        operation=Operation.GROUPBY_SUM,
        column="sales",
        group_by="month",
        chart_type=ChartType.LINE,
    )
    # Provide x out of order; the line must be sorted ascending by x.
    resp = _run(
        plan,
        _grouped_result([("Mar", 3), ("Jan", 1), ("Feb", 2)], key="month"),
    )
    assert resp.chart_type == ChartType.LINE
    trace = resp.chart_spec["data"][0]
    assert trace["type"] == "scatter" and "lines" in trace["mode"]
    assert list(trace["x"]) == ["Feb", "Jan", "Mar"]  # sorted


def test_xy_select_forces_scatter():
    plan = QueryPlan(
        operation=Operation.XY_SELECT,
        x_column="sales",
        y_column="qty",
        chart_type=ChartType.BAR,  # advisory; must be overridden
    )
    result = ExecutionResult(
        answer="ans",
        table=[{"sales": 1, "qty": 10}, {"sales": 2, "qty": 20}],
        x_field="sales",
        y_field="qty",
    )
    resp = _run(plan, result)
    assert resp.chart_type == ChartType.SCATTER
    trace = resp.chart_spec["data"][0]
    assert trace["type"] == "scatter" and trace["mode"] == "markers"


# --------------------------------------------------------------------------- #
# Fallback rules
# --------------------------------------------------------------------------- #
def test_pie_falls_back_to_bar_when_too_many_slices():
    plan = QueryPlan(
        operation=Operation.GROUPBY_SUM,
        column="sales",
        group_by="region",
        chart_type=ChartType.PIE,
    )
    rows = [(f"cat{i}", i) for i in range(20)]  # 20 > default max of 12
    resp = _run(plan, _grouped_result(rows))
    assert resp.chart_type == ChartType.BAR


def test_missing_recommendation_defaults_to_bar():
    plan = QueryPlan(
        operation=Operation.GROUPBY_SUM, column="sales", group_by="region"
    )  # chart_type is None
    resp = _run(plan, _grouped_result([("North", 130), ("South", 50)]))
    assert resp.chart_type == ChartType.BAR


# --------------------------------------------------------------------------- #
# Non-chartable (scalar) results
# --------------------------------------------------------------------------- #
def test_scalar_result_has_no_chart():
    plan = QueryPlan(operation=Operation.ROW_COUNT)
    result = ExecutionResult(
        answer="The dataset has 4 row(s).",
        table=[{"metric": "row_count", "value": 4}],
        x_field=None,
        y_field=None,
    )
    resp = _run(plan, result)
    assert resp.chart_type is None
    assert resp.chart_spec is None
    assert resp.table_data == [{"metric": "row_count", "value": 4}]
