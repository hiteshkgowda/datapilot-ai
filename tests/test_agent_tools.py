"""Unit tests for all eight AgentTool adapters.

Each adapter is tested with a fake service that returns the minimum fields
the real service guarantees.  Tests verify:
  - correct argument mapping (no business logic added)
  - output dict keys and types
  - error propagation as AgentExecutionError where applicable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.agent_tools import (
    AnalyticsTool,
    CrudExecuteTool,
    CrudPreviewTool,
    DatasetPreviewTool,
    ForecastTool,
    ReportTool,
    SqlQueryTool,
    ToolRegistry,
    VisualizationTool,
    build_registry,
)


# ------------------------------------------------------------------ #
# Fake domain objects matching real service return types
# ------------------------------------------------------------------ #

@dataclass
class _ExecutionResult:
    answer: str = "42"

@dataclass
class _AnalysisResult:
    result: _ExecutionResult = field(default_factory=_ExecutionResult)
    execution_time_ms: float = 1.0
    total_time_ms: float = 2.0

@dataclass
class _ChartType:
    value: str = "bar"

@dataclass
class _ChartResponse:
    answer: str = "Here is the bar chart."
    chart_type: Optional[_ChartType] = field(default_factory=_ChartType)
    chart_spec: Optional[dict] = field(default_factory=dict)
    total_time_ms: float = 3.0

@dataclass
class _ForecastOperation:
    value: str = "forecast"

@dataclass
class _ForecastResponse:
    answer: str = "Revenue will grow."
    operation: _ForecastOperation = field(default_factory=_ForecastOperation)
    method_used: str = "Holt-Winters"
    data_points: int = 24
    horizon: int = 6
    chart_spec: Optional[dict] = field(default_factory=dict)

@dataclass
class _ReportMeta:
    report_id: str = "rpt-001"
    download_url: str = "/api/v1/reports/rpt-001/download"
    size_bytes: int = 12345

@dataclass
class _DatasetPreview:
    rows: int = 100
    columns: int = 5
    column_names: list = field(default_factory=lambda: ["id", "name", "value", "date", "status"])
    preview_rows: list = field(default_factory=lambda: [{"id": 1, "name": "A"}])

@dataclass
class _CrudOperation:
    value: str = "update"

@dataclass
class _CrudPreviewResponse:
    connection_id: str = "conn1"
    affected_row_count: int = 3
    requires_confirmation: bool = False
    confirmation_token: Optional[str] = None
    rollback_supported: bool = True
    warnings: list = field(default_factory=list)

    @property
    def plan(self):
        m = MagicMock()
        m.operation = _CrudOperation()
        m.table_name = "orders"
        m.model_dump.return_value = {"operation": "update", "table_name": "orders"}
        return m

@dataclass
class _CrudExecuteResponse:
    operation: _CrudOperation = field(default_factory=_CrudOperation)
    table_name: str = "orders"
    affected_rows: int = 3
    rollback_token: Optional[str] = "rb-abc"
    audit_id: str = "aud-001"

@dataclass
class _QueryResponse:
    answer: str = "Total: 500"
    total_time_ms: float = 5.0


# ------------------------------------------------------------------ #
# Shared state fixture
# ------------------------------------------------------------------ #

_STATE: dict[str, Any] = {
    "session_id": "s1",
    "dataset_id": "ds1",
    "connection_id": "conn1",
}


# ------------------------------------------------------------------ #
# 1. DatasetPreviewTool
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_dataset_preview_returns_summary():
    svc = MagicMock()
    svc.get_preview.return_value = _DatasetPreview()
    tool = DatasetPreviewTool(svc)
    out = await tool.execute({"dataset_id": "ds1", "limit": 5}, _STATE)
    assert "100 rows" in out["answer"]
    assert out["rows"] == 100
    assert out["columns"] == 5
    assert "id" in out["column_names"]
    svc.get_preview.assert_called_once_with("ds1", limit=5)


@pytest.mark.anyio
async def test_dataset_preview_default_limit():
    svc = MagicMock()
    svc.get_preview.return_value = _DatasetPreview()
    tool = DatasetPreviewTool(svc)
    await tool.execute({"dataset_id": "ds1"}, _STATE)
    svc.get_preview.assert_called_once_with("ds1", limit=10)


# ------------------------------------------------------------------ #
# 2. AnalyticsTool
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_analytics_returns_answer():
    svc = AsyncMock()
    svc.analyze.return_value = _AnalysisResult()
    tool = AnalyticsTool(svc)
    out = await tool.execute({"dataset_id": "ds1", "question": "sum of value?"}, _STATE)
    assert out["answer"] == "42"
    assert "execution_time_ms" in out
    svc.analyze.assert_awaited_once_with("ds1", "sum of value?")


@pytest.mark.anyio
async def test_analytics_propagates_error():
    svc = AsyncMock()
    svc.analyze.side_effect = RuntimeError("LLM down")
    tool = AnalyticsTool(svc)
    with pytest.raises(RuntimeError, match="LLM down"):
        await tool.execute({"dataset_id": "ds1", "question": "?"}, _STATE)


# ------------------------------------------------------------------ #
# 3. VisualizationTool
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_visualization_returns_chart_type():
    svc = AsyncMock()
    svc.create_chart.return_value = _ChartResponse()
    tool = VisualizationTool(svc)
    out = await tool.execute({"dataset_id": "ds1", "question": "show bar chart"}, _STATE)
    assert out["answer"] == "Here is the bar chart."
    assert out["chart_type"] == "bar"
    assert out["has_chart"] is True


@pytest.mark.anyio
async def test_visualization_no_chart():
    svc = AsyncMock()
    resp = _ChartResponse(chart_type=None, chart_spec=None)
    svc.create_chart.return_value = resp
    tool = VisualizationTool(svc)
    out = await tool.execute({"dataset_id": "ds1", "question": "count rows"}, _STATE)
    assert out["chart_type"] is None
    assert out["has_chart"] is False


# ------------------------------------------------------------------ #
# 4. ForecastTool
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_forecast_returns_summary():
    svc = AsyncMock()
    svc.create_forecast.return_value = _ForecastResponse()
    tool = ForecastTool(svc)
    out = await tool.execute({"dataset_id": "ds1", "question": "forecast next 6 months"}, _STATE)
    assert "Revenue will grow" in out["answer"]
    assert out["method_used"] == "Holt-Winters"
    assert out["horizon"] == 6
    svc.create_forecast.assert_awaited_once_with("ds1", "forecast next 6 months")


# ------------------------------------------------------------------ #
# 5. ReportTool
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_report_returns_download_url():
    svc = AsyncMock()
    svc.generate.return_value = _ReportMeta()
    tool = ReportTool(svc)
    out = await tool.execute({"dataset_id": "ds1"}, _STATE)
    assert out["report_id"] == "rpt-001"
    assert "/rpt-001/" in out["download_url"]
    assert out["size_bytes"] == 12345


@pytest.mark.anyio
async def test_report_passes_questions():
    svc = AsyncMock()
    svc.generate.return_value = _ReportMeta()
    tool = ReportTool(svc)
    await tool.execute({"dataset_id": "ds1", "questions": ["Q1", "Q2"]}, _STATE)
    call_args = svc.generate.call_args[0][0]
    assert call_args.questions == ["Q1", "Q2"]


# ------------------------------------------------------------------ #
# 6. CrudPreviewTool
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_crud_preview_returns_preview_fields():
    svc = AsyncMock()
    svc.preview.return_value = _CrudPreviewResponse()
    tool = CrudPreviewTool(svc)
    out = await tool.execute(
        {"connection_id": "conn1", "table_name": "orders", "question": "update row 1"},
        _STATE,
    )
    assert out["affected_row_count"] == 3
    assert out["requires_confirmation"] is False
    assert out["table_name"] == "orders"
    assert "plan" in out


@pytest.mark.anyio
async def test_crud_preview_uses_state_connection_id():
    svc = AsyncMock()
    svc.preview.return_value = _CrudPreviewResponse()
    tool = CrudPreviewTool(svc)
    await tool.execute({"question": "delete row 5"}, _STATE)
    call_args = svc.preview.call_args[0][0]
    assert call_args.connection_id == "conn1"  # from state


@pytest.mark.anyio
async def test_crud_preview_requires_approval_flag():
    tool = CrudPreviewTool(MagicMock())
    assert tool.requires_approval is True


# ------------------------------------------------------------------ #
# 7. CrudExecuteTool
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_crud_execute_returns_affected_rows():
    svc = AsyncMock()
    svc.execute.return_value = _CrudExecuteResponse()
    tool = CrudExecuteTool(svc)
    out = await tool.execute(
        {
            "connection_id": "conn1",
            "plan": {"operation": "update", "table_name": "orders"},
            "confirmation_token": "tok123",
        },
        _STATE,
    )
    assert out["affected_rows"] == 3
    assert out["rollback_token"] == "rb-abc"


@pytest.mark.anyio
async def test_crud_execute_bad_plan_raises():
    from app.core.exceptions import AgentExecutionError
    svc = AsyncMock()
    tool = CrudExecuteTool(svc)
    with pytest.raises(AgentExecutionError, match="Invalid CrudPlan"):
        await tool.execute(
            {"connection_id": "c1", "plan": {"bad_field": "??"}},
            _STATE,
        )


# ------------------------------------------------------------------ #
# 8. SqlQueryTool
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_sql_query_returns_answer():
    svc = AsyncMock()
    svc.answer_question.return_value = _QueryResponse()
    tool = SqlQueryTool(svc)
    out = await tool.execute({"dataset_id": "ds1", "question": "total revenue"}, _STATE)
    assert out["answer"] == "Total: 500"
    svc.answer_question.assert_awaited_once_with("ds1", "total revenue")


# ------------------------------------------------------------------ #
# ToolRegistry
# ------------------------------------------------------------------ #

def test_registry_get_known_tool():
    svc = MagicMock()
    registry = build_registry(
        dataset_service=svc,
        analytics_service=svc,
        visualization_service=svc,
        forecast_service=svc,
        report_service=svc,
        crud_service=svc,
    )
    tool = registry.get("analytics")
    assert tool.name == "analytics"


def test_registry_get_unknown_tool_raises():
    from app.core.exceptions import AgentPlanError
    svc = MagicMock()
    registry = build_registry(
        dataset_service=svc,
        analytics_service=svc,
        visualization_service=svc,
        forecast_service=svc,
        report_service=svc,
        crud_service=svc,
    )
    with pytest.raises(AgentPlanError, match="Unknown tool"):
        registry.get("nonexistent_tool")


def test_registry_schemas_include_all_tools():
    svc = MagicMock()
    registry = build_registry(
        dataset_service=svc,
        analytics_service=svc,
        visualization_service=svc,
        forecast_service=svc,
        report_service=svc,
        crud_service=svc,
    )
    schemas = registry.schemas()
    names = {s["name"] for s in schemas}
    assert names == {
        "dataset_preview", "analytics", "visualization", "forecast",
        "report", "crud_preview", "crud_execute", "sql_query",
    }


# anyio backend fixture — asyncio only (trio not installed)
@pytest.fixture(params=["asyncio"])
def anyio_backend():
    return "asyncio"
