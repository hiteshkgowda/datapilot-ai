"""Agent tool adapters for Phase 9.

Each adapter wraps exactly one existing service method.  No business logic
lives here — the adapters are pure translators from the agent's ``arguments``
dict to the service's typed API and back to a JSON-serialisable summary dict.

Tool registry
-------------
``TOOL_NAMES`` lists all valid tool names.  ``build_registry`` constructs a
``ToolRegistry`` instance from the set of services injected at startup.
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from app.core.exceptions import AgentExecutionError, ValidationError
from app.schemas.crud import CrudExecuteRequest, CrudPlan, CrudRequest
from app.schemas.report import ReportRequest


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class AgentTool(Protocol):
    """Structural interface every tool adapter must satisfy."""

    name: str
    description: str
    input_schema: dict[str, Any]
    requires_approval: bool

    async def execute(
        self, arguments: dict[str, Any], state: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute the tool and return a JSON-serialisable summary dict."""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _elapsed(t0: float) -> float:
    return round((time.monotonic() - t0) * 1000, 2)


# ---------------------------------------------------------------------------
# 1. Dataset preview
# ---------------------------------------------------------------------------

class DatasetPreviewTool:
    name = "dataset_preview"
    description = (
        "Preview rows and schema of a dataset. Use this first to understand "
        "the structure before running analytics or generating charts."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string", "description": "Dataset identifier."},
            "limit":      {"type": "integer", "default": 10, "description": "Number of preview rows."},
        },
        "required": ["dataset_id"],
    }
    requires_approval = False

    def __init__(self, dataset_service: Any) -> None:
        self._svc = dataset_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        dataset_id = arguments["dataset_id"]
        limit = int(arguments.get("limit", 10))
        t0 = time.monotonic()
        preview = self._svc.get_preview(dataset_id, limit=limit)
        return {
            "answer": (
                f"Dataset '{dataset_id}' has {preview.rows} rows and "
                f"{preview.columns} columns. "
                f"Columns: {', '.join(preview.column_names)}."
            ),
            "rows": preview.rows,
            "columns": preview.columns,
            "column_names": list(preview.column_names),
            "preview_rows": preview.preview_rows[:limit],
            "duration_ms": _elapsed(t0),
        }


# ---------------------------------------------------------------------------
# 2. Analytics
# ---------------------------------------------------------------------------

class AnalyticsTool:
    name = "analytics"
    description = (
        "Answer a natural-language question about a dataset using pandas analytics. "
        "Returns a text answer and optional table data."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string"},
            "question":   {"type": "string", "description": "Natural-language question."},
        },
        "required": ["dataset_id", "question"],
    }
    requires_approval = False

    def __init__(self, analytics_service: Any) -> None:
        self._svc = analytics_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        t0 = time.monotonic()
        result = await self._svc.analyze(arguments["dataset_id"], arguments["question"])
        return {
            "answer": result.result.answer,
            "execution_time_ms": result.execution_time_ms,
            "total_time_ms": result.total_time_ms,
            "duration_ms": _elapsed(t0),
        }


# ---------------------------------------------------------------------------
# 3. Visualization
# ---------------------------------------------------------------------------

class VisualizationTool:
    name = "visualization"
    description = (
        "Generate a chart for a dataset based on a natural-language question. "
        "Returns the chart type and a text answer. "
        "Use when the user asks for a chart, graph, or visual."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string"},
            "question":   {"type": "string"},
        },
        "required": ["dataset_id", "question"],
    }
    requires_approval = False

    def __init__(self, visualization_service: Any) -> None:
        self._svc = visualization_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        t0 = time.monotonic()
        resp = await self._svc.create_chart(arguments["dataset_id"], arguments["question"])
        return {
            "answer": resp.answer,
            "chart_type": resp.chart_type.value if resp.chart_type else None,
            "has_chart": resp.chart_spec is not None,
            "total_time_ms": resp.total_time_ms,
            "duration_ms": _elapsed(t0),
        }


# ---------------------------------------------------------------------------
# 4. Forecast
# ---------------------------------------------------------------------------

class ForecastTool:
    name = "forecast"
    description = (
        "Forecast future values or detect anomalies in a time-series dataset. "
        "Use when the user asks for a forecast, prediction, trend, or anomaly."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string"},
            "question":   {"type": "string", "description": "E.g. 'forecast next 6 months'."},
        },
        "required": ["dataset_id", "question"],
    }
    requires_approval = False

    def __init__(self, forecast_service: Any) -> None:
        self._svc = forecast_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        t0 = time.monotonic()
        resp = await self._svc.create_forecast(arguments["dataset_id"], arguments["question"])
        return {
            "answer": resp.answer,
            "operation": resp.operation.value,
            "method_used": resp.method_used,
            "data_points": resp.data_points,
            "horizon": resp.horizon,
            "has_chart": resp.chart_spec is not None,
            "duration_ms": _elapsed(t0),
        }


# ---------------------------------------------------------------------------
# 5. Report
# ---------------------------------------------------------------------------

class ReportTool:
    name = "report"
    description = (
        "Generate a PDF report for a dataset. "
        "Returns a download URL. "
        "Use at most once per run."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string"},
            "questions":  {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional AI-generated sections to include.",
                "default": [],
            },
        },
        "required": ["dataset_id"],
    }
    requires_approval = False

    def __init__(self, report_service: Any) -> None:
        self._svc = report_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        t0 = time.monotonic()
        request = ReportRequest(
            dataset_id=arguments["dataset_id"],
            questions=arguments.get("questions", []),
        )
        meta = await self._svc.generate(request)
        return {
            "answer": f"Report generated. Download at: {meta.download_url}",
            "report_id": meta.report_id,
            "download_url": meta.download_url,
            "size_bytes": meta.size_bytes,
            "duration_ms": _elapsed(t0),
        }


# ---------------------------------------------------------------------------
# 6. CRUD preview
# ---------------------------------------------------------------------------

class CrudPreviewTool:
    name = "crud_preview"
    description = (
        "Preview a database mutation (insert, update, delete, soft-delete) "
        "without executing it. Always call this before crud_execute. "
        "Returns affected rows and a confirmation token when the operation "
        "is destructive."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "connection_id": {"type": "string", "description": "DB connection ID."},
            "dataset_id":    {"type": "string", "description": "Dataset ID (alternative to connection_id+table_name)."},
            "table_name":    {"type": "string"},
            "schema_name":   {"type": "string", "default": None},
            "question":      {"type": "string", "description": "Natural-language mutation instruction."},
        },
        "required": ["question"],
    }
    requires_approval = True   # may pause for human confirmation

    def __init__(self, crud_service: Any) -> None:
        self._svc = crud_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        t0 = time.monotonic()
        request = CrudRequest(
            connection_id=arguments.get("connection_id") or state.get("connection_id"),
            dataset_id=arguments.get("dataset_id") or state.get("dataset_id"),
            schema_name=arguments.get("schema_name"),
            table_name=arguments.get("table_name"),
            question=arguments["question"],
        )
        resp = await self._svc.preview(request)
        return {
            "answer": (
                f"Preview: '{resp.plan.operation.value}' on '{resp.plan.table_name}' "
                f"will affect {resp.affected_row_count} row(s)."
            ),
            "connection_id": resp.connection_id,
            "operation": resp.plan.operation.value,
            "table_name": resp.plan.table_name,
            "affected_row_count": resp.affected_row_count,
            "requires_confirmation": resp.requires_confirmation,
            "confirmation_token": resp.confirmation_token,
            "rollback_supported": resp.rollback_supported,
            "warnings": resp.warnings,
            "plan": resp.plan.model_dump(),
            "duration_ms": _elapsed(t0),
        }


# ---------------------------------------------------------------------------
# 7. CRUD execute
# ---------------------------------------------------------------------------

class CrudExecuteTool:
    name = "crud_execute"
    description = (
        "Execute a database mutation that was previously previewed with crud_preview. "
        "Must follow a crud_preview step. "
        "Destructive operations require the confirmation token from the preview."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "connection_id":      {"type": "string"},
            "plan":               {"type": "object", "description": "CrudPlan dict from the preview result."},
            "confirmation_token": {"type": "string", "default": None},
        },
        "required": ["connection_id", "plan"],
    }
    requires_approval = False  # approval is handled via the crud_preview pause

    def __init__(self, crud_service: Any) -> None:
        self._svc = crud_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            plan = CrudPlan(**arguments["plan"])
        except Exception as exc:
            raise AgentExecutionError(f"Invalid CrudPlan in crud_execute arguments: {exc}") from exc

        request = CrudExecuteRequest(
            connection_id=arguments["connection_id"],
            plan=plan,
            confirmation_token=arguments.get("confirmation_token"),
        )
        resp = await self._svc.execute(request)
        return {
            "answer": (
                f"Executed '{resp.operation.value}' on '{resp.table_name}': "
                f"{resp.affected_rows} row(s) affected."
            ),
            "operation": resp.operation.value,
            "table_name": resp.table_name,
            "affected_rows": resp.affected_rows,
            "rollback_token": resp.rollback_token,
            "audit_id": resp.audit_id,
            "duration_ms": _elapsed(t0),
        }


# ---------------------------------------------------------------------------
# 8. SQL query
# ---------------------------------------------------------------------------

class AnomalyDetectionTool:
    name = "anomaly_detection"
    description = (
        "Detect anomalies in a dataset's numeric columns. "
        "Finds revenue spikes, drops, outliers, KPI deviations, and unexpected patterns "
        "using z-score, IQR, Isolation Forest, and seasonal decomposition. "
        "Use when the user asks about unusual values, outliers, anomalies, or unexpected changes."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id":       {"type": "string"},
            "columns":          {"type": "array", "items": {"type": "string"}},
            "methods":          {"type": "array", "items": {"type": "string"}},
            "zscore_threshold": {"type": "number"},
            "time_column":      {"type": "string"},
        },
        "required": ["dataset_id"],
    }
    requires_approval = False

    def __init__(self, anomaly_service: Any, dataset_service: Any) -> None:
        self._anomaly_svc = anomaly_service
        self._ds_svc = dataset_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

        dataset_id: str = arguments["dataset_id"]
        try:
            df, _ = await run_in_threadpool(self._ds_svc.load_dataframe, dataset_id)
        except Exception as exc:
            return {"error": f"Could not load dataset: {exc}"}

        result = await self._anomaly_svc.detect(df=df, request_dict=arguments)
        summary = result.model_dump()
        summary.pop("chart_spec", None)  # strip large payload from agent context
        return summary


class RootCauseAnalysisTool:
    name = "root_cause_analysis"
    description = (
        "Identify why a metric changed between two time periods. "
        "Decomposes the change into contributing dimensions (region, product, "
        "segment, channel, category) and ranks the primary drivers by impact. "
        "Use when the user asks 'why did X drop/grow' or 'what drove the change in Y'."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id":      {"type": "string"},
            "question":        {"type": "string"},
            "metric_column":   {"type": "string"},
            "period_column":   {"type": "string"},
            "current_period":  {"type": "string"},
            "previous_period": {"type": "string"},
        },
        "required": ["dataset_id", "question"],
    }
    requires_approval = False

    def __init__(self, root_cause_service: Any, dataset_service: Any) -> None:
        self._rca_svc = root_cause_service
        self._ds_svc = dataset_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        import pandas as pd  # noqa: PLC0415
        from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

        dataset_id: str = arguments["dataset_id"]
        try:
            df, _ = await run_in_threadpool(self._ds_svc.load_dataframe, dataset_id)
        except Exception as exc:
            return {"error": f"Could not load dataset: {exc}"}

        result = await self._rca_svc.analyze(df=df, request_dict=arguments)
        return result.model_dump()


class RecommendationTool:
    name = "recommendation"
    description = (
        "Generate prioritised, data-grounded recommendations from anomaly, insight, "
        "or forecast results. Returns a ranked action list with reasons and expected "
        "impact. Use when the user asks 'what should I do', 'what actions should I take', "
        "or 'give me recommendations'."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id":        {"type": "string"},
            "anomalies":         {"type": "object", "description": "Output of anomaly_detection tool."},
            "insights":          {"type": "object", "description": "Output of insight generation."},
            "forecast":          {"type": "object", "description": "Output of forecast tool."},
            "context":           {"type": "string", "description": "Optional business context."},
            "max_recommendations": {"type": "integer", "default": 10},
        },
        "required": ["dataset_id"],
    }
    requires_approval = False

    def __init__(self, recommendation_service: Any) -> None:
        self._svc = recommendation_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        from app.schemas.recommendation import RecommendationRequest  # noqa: PLC0415

        # Reconstruct typed inputs from dicts if present.
        anomalies = None
        insights = None
        if arguments.get("anomalies"):
            try:
                from app.schemas.anomaly import AnomalyResponse  # noqa: PLC0415
                anomalies = AnomalyResponse(**arguments["anomalies"])
            except Exception:
                pass
        if arguments.get("insights"):
            try:
                from app.schemas.insight import InsightResponse  # noqa: PLC0415
                insights = InsightResponse(**arguments["insights"])
            except Exception:
                pass

        request = RecommendationRequest(
            dataset_id=arguments["dataset_id"],
            anomalies=anomalies,
            insights=insights,
            forecast=arguments.get("forecast"),
            context=arguments.get("context"),
            max_recommendations=int(arguments.get("max_recommendations", 10)),
            llm_enhance=True,
        )
        resp = await self._svc.generate(request)
        return {
            "summary": resp.summary,
            "total_count": resp.total_count,
            "llm_enhanced": resp.llm_enhanced,
            "recommendations": [r.model_dump() for r in resp.recommendations[:5]],
        }


class SqlQueryTool:
    name = "sql_query"
    description = (
        "Answer a natural-language question by generating and running a SQL "
        "query against a connected database dataset. "
        "Use for database-backed datasets when direct analytics is needed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string"},
            "question":   {"type": "string"},
        },
        "required": ["dataset_id", "question"],
    }
    requires_approval = False

    def __init__(self, analytics_service: Any) -> None:
        self._svc = analytics_service

    async def execute(self, arguments: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        t0 = time.monotonic()
        resp = await self._svc.answer_question(arguments["dataset_id"], arguments["question"])
        return {
            "answer": resp.answer,
            "total_time_ms": resp.total_time_ms,
            "duration_ms": _elapsed(t0),
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOL_NAMES: tuple[str, ...] = (
    "dataset_preview",
    "analytics",
    "visualization",
    "forecast",
    "report",
    "crud_preview",
    "crud_execute",
    "sql_query",
    "anomaly_detection",
    "root_cause_analysis",
    "recommendation",
)


class ToolRegistry:
    """Holds the set of active tools and exposes them by name."""

    def __init__(self, tools: list[AgentTool]) -> None:
        self._tools: dict[str, AgentTool] = {t.name: t for t in tools}

    def get(self, name: str) -> AgentTool:
        if name not in self._tools:
            from app.core.exceptions import AgentPlanError
            raise AgentPlanError(f"Unknown tool '{name}'. Available: {list(self._tools)}")
        return self._tools[name]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "requires_approval": t.requires_approval,
            }
            for t in self._tools.values()
        ]


def build_registry(
    *,
    dataset_service: Any,
    analytics_service: Any,
    visualization_service: Any,
    forecast_service: Any,
    report_service: Any,
    crud_service: Any,
    anomaly_service: Any = None,
    root_cause_service: Any = None,
    recommendation_service: Any = None,
) -> ToolRegistry:
    """Construct a ToolRegistry from the injected service singletons."""
    tools: list[Any] = [
        DatasetPreviewTool(dataset_service),
        AnalyticsTool(analytics_service),
        VisualizationTool(visualization_service),
        ForecastTool(forecast_service),
        ReportTool(report_service),
        CrudPreviewTool(crud_service),
        CrudExecuteTool(crud_service),
        SqlQueryTool(analytics_service),
    ]
    if anomaly_service is not None:
        tools.append(AnomalyDetectionTool(anomaly_service, dataset_service))
    if root_cause_service is not None:
        tools.append(RootCauseAnalysisTool(root_cause_service, dataset_service))
    if recommendation_service is not None:
        tools.append(RecommendationTool(recommendation_service))
    return ToolRegistry(tools)
