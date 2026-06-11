"""Report service: deterministic report assembly + persistence.

Builds a professional PDF from a dataset. The core report is a *deterministic*
battery of programmatic query plans (no LLM); optional user questions add
clearly-separated AI-generated sections.

Storage layout (inside ``REPORTS_DIR``):
    <report_id>.pdf    -> the rendered PDF
    <report_id>.json   -> serialized :class:`ReportMetadata`
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import DataAssistantError, LLMError, ReportNotFoundError
from app.schemas.forecast import (
    AggMethod,
    ForecastOperation,
    ForecastPlan,
    Frequency,
)
from app.schemas.query import Operation, QueryPlan
from app.schemas.report import ReportMetadata, ReportRequest
from app.services.analytics_service import AnalyticsService
from app.services.dataset_service import DatasetSchema, DatasetService
from app.services.forecast_service import ForecastService
from app.services.pdf_builder import (
    ChartSection,
    PdfBuilder,
    QASection,
    ReportModel,
    StatRow,
    figure_to_png,
)
from app.services.visualization_service import VisualizationService


@dataclass(frozen=True)
class ReportForecastConfig:
    """Explicit, deterministic configuration for the report forecast section.

    A forecast is only added when ``enabled`` and ``target_column`` (and
    ``date_column``) are set — there is no automatic column selection.
    """

    enabled: bool = False
    date_column: Optional[str] = None
    target_column: Optional[str] = None
    frequency: str = "M"
    aggregation: str = "sum"
    horizon: int = 12


class ReportService:
    """Generate, persist and retrieve PDF reports."""

    def __init__(
        self,
        dataset_service: DatasetService,
        analytics: AnalyticsService,
        visualization: VisualizationService,
        reports_dir: Path,
        report_version: str,
        forecast_service: Optional[ForecastService] = None,
        forecast_config: Optional[ReportForecastConfig] = None,
    ) -> None:
        self._datasets = dataset_service
        self._analytics = analytics
        self._visualization = visualization
        self._reports_dir = reports_dir
        self._report_version = report_version
        self._forecast = forecast_service
        self._forecast_config = forecast_config or ReportForecastConfig()
        self._pdf_builder = PdfBuilder()
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def generate(self, request: ReportRequest, owner_sub: str = "") -> ReportMetadata:
        """Generate a report for a dataset and persist the PDF + metadata."""
        frame, schema = await run_in_threadpool(
            self._datasets.load_with_schema, request.dataset_id
        )
        _, dataset_meta = await run_in_threadpool(
            self._datasets.load_dataframe, request.dataset_id
        )

        summary = self._build_summary(frame, schema)
        statistics = self._build_statistics(frame, schema)
        charts, grouped_for_insight = await self._build_deterministic_charts(
            request.dataset_id, schema
        )
        charts += await self._build_forecast_section(request.dataset_id, schema)
        insights = self._build_insights(summary, statistics, grouped_for_insight)
        qa_sections = await self._build_qa_sections(
            request.dataset_id, request.questions
        )

        report_id = uuid.uuid4().hex
        generated_at = datetime.now(timezone.utc)
        model = ReportModel(
            report_id=report_id,
            report_version=self._report_version,
            generated_at=generated_at,
            dataset_id=request.dataset_id,
            dataset_filename=dataset_meta.filename,
            summary=summary,
            statistics=statistics,
            charts=charts,
            insights=insights,
            qa_sections=qa_sections,
        )

        pdf_bytes = await run_in_threadpool(self._pdf_builder.build, model)

        deterministic_count = (
            1  # summary
            + (1 if statistics else 0)
            + len(charts)
            + (1 if insights else 0)
        )
        metadata = ReportMetadata(
            report_id=report_id,
            report_version=self._report_version,
            generated_at=generated_at,
            dataset_id=request.dataset_id,
            dataset_filename=dataset_meta.filename,
            size_bytes=len(pdf_bytes),
            deterministic_section_count=deterministic_count,
            ai_section_count=len(qa_sections),
            download_url=f"/api/v1/reports/{report_id}/download",
            owner_sub=owner_sub,
        )
        await run_in_threadpool(self._persist, report_id, pdf_bytes, metadata)
        return metadata

    def list_reports(self, owner_sub: str = "") -> list[ReportMetadata]:
        """Return reports visible to ``owner_sub``, newest first.

        Pre-auth reports (``owner_sub=""``) are visible to every authenticated
        user so existing data isn't silently lost after the auth migration.
        """
        reports: list[ReportMetadata] = []
        for meta_path in self._reports_dir.glob("*.json"):
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
                meta = ReportMetadata(**raw)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if owner_sub and meta.owner_sub and meta.owner_sub != owner_sub:
                continue
            reports.append(meta)
        reports.sort(key=lambda meta: meta.generated_at, reverse=True)
        return reports

    def get_report_path(self, report_id: str, owner_sub: str = "") -> Path:
        """Return the PDF path for a report, or raise if it does not exist or is not owned."""
        meta_path = self._reports_dir / f"{report_id}.json"
        if meta_path.is_file():
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
                meta = ReportMetadata(**raw)
                if owner_sub and meta.owner_sub and meta.owner_sub != owner_sub:
                    raise ReportNotFoundError(f"Report '{report_id}' was not found.")
            except (OSError, json.JSONDecodeError, ValueError):
                pass
        path = self._reports_dir / f"{report_id}.pdf"
        if not path.is_file():
            raise ReportNotFoundError(f"Report '{report_id}' was not found.")
        return path

    # ------------------------------------------------------------------ #
    # Deterministic sections
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_summary(frame: pd.DataFrame, schema: DatasetSchema) -> dict[str, Any]:
        return {
            "rows": int(frame.shape[0]),
            "columns": int(frame.shape[1]),
            "column_names": list(schema.column_names),
            "dtypes": dict(schema.dtypes),
        }

    @staticmethod
    def _build_statistics(
        frame: pd.DataFrame, schema: DatasetSchema
    ) -> list[StatRow]:
        lookup = {str(col): col for col in frame.columns}
        rows: list[StatRow] = []
        for name in schema.column_names:
            if name not in schema.numeric_columns:
                continue
            series = frame[lookup[name]]
            rows.append(
                StatRow(
                    column=name,
                    count=int(series.count()),
                    mean=float(series.mean()),
                    minimum=float(series.min()),
                    maximum=float(series.max()),
                    total=float(series.sum()),
                )
            )
        return rows

    async def _build_deterministic_charts(
        self, dataset_id: str, schema: DatasetSchema
    ) -> tuple[list[ChartSection], Optional[dict[str, Any]]]:
        """Build auto-selected charts; return them plus a groupby result."""
        categorical = [
            c for c in schema.column_names if c not in schema.numeric_columns
        ]
        numeric = [c for c in schema.column_names if c in schema.numeric_columns]

        targets: list[tuple[str, QueryPlan]] = []
        if categorical and numeric:
            targets.append(
                (
                    f"Total {numeric[0]} by {categorical[0]}",
                    QueryPlan(
                        operation=Operation.GROUPBY_SUM,
                        column=numeric[0],
                        group_by=categorical[0],
                    ),
                )
            )
        if categorical:
            targets.append(
                (
                    f"Distribution by {categorical[0]}",
                    QueryPlan(
                        operation=Operation.GROUPBY_COUNT, group_by=categorical[0]
                    ),
                )
            )
        if len(numeric) >= 2:
            targets.append(
                (
                    f"{numeric[1]} vs {numeric[0]}",
                    QueryPlan(
                        operation=Operation.XY_SELECT,
                        x_column=numeric[0],
                        y_column=numeric[1],
                    ),
                )
            )

        charts: list[ChartSection] = []
        grouped_for_insight: Optional[dict[str, Any]] = None
        for title, plan in targets:
            analysis = await self._analytics.execute_plan(dataset_id, plan)
            if plan.operation is Operation.GROUPBY_SUM and analysis.result.table:
                grouped_for_insight = {
                    "group_field": analysis.result.x_field,
                    "value_field": analysis.result.y_field,
                    "top": analysis.result.table[0],
                }
            built = await self._visualization.build_chart(analysis.result, plan)
            if built is None:
                continue
            chart_type, chart_spec = built
            charts.append(
                self._chart_section(title, chart_type.value, chart_spec, analysis.result.table)
            )
        return charts, grouped_for_insight

    async def _build_forecast_section(
        self, dataset_id: str, schema: DatasetSchema
    ) -> list[ChartSection]:
        """Add a deterministic forecast chart when explicitly configured.

        Returns an empty list unless a forecast service is available, the
        feature is enabled, and both the configured date and target columns
        exist in the dataset. No automatic column selection is performed.
        """
        config = self._forecast_config
        columns = set(schema.column_names)
        if (
            self._forecast is None
            or not config.enabled
            or not config.target_column
            or not config.date_column
            or config.date_column not in columns
            or config.target_column not in columns
        ):
            return []

        plan = ForecastPlan(
            operation=ForecastOperation.FORECAST,
            date_column=config.date_column,
            value_column=config.target_column,
            frequency=Frequency(config.frequency),
            aggregation=AggMethod(config.aggregation),
            horizon=config.horizon,
        )
        try:
            response = await self._forecast.run_plan(dataset_id, plan)
        except DataAssistantError:
            # A forecast failure must never break report generation.
            return []
        if response.chart_spec is None:
            return []
        return [
            self._chart_section(
                f"Forecast — {response.method_used}",
                "line",
                response.chart_spec,
                response.table_data,
            )
        ]

    @staticmethod
    def _build_insights(
        summary: dict[str, Any],
        statistics: list[StatRow],
        grouped: Optional[dict[str, Any]],
    ) -> list[str]:
        insights = [
            f"The dataset contains {summary['rows']} records across "
            f"{summary['columns']} fields."
        ]
        if statistics:
            first = statistics[0]
            insights.append(
                f"'{first.column}' ranges from {first.minimum:,.4g} to "
                f"{first.maximum:,.4g}, averaging {first.mean:,.4g}."
            )
        if grouped is not None:
            top = grouped["top"]
            insights.append(
                f"The highest total {grouped['value_field']} is in "
                f"'{top[grouped['group_field']]}' "
                f"({top[grouped['value_field']]:,.4g})."
            )
        return insights

    # ------------------------------------------------------------------ #
    # AI-generated sections
    # ------------------------------------------------------------------ #
    async def _build_qa_sections(
        self, dataset_id: str, questions: list[str]
    ) -> list[QASection]:
        sections: list[QASection] = []
        for question in questions:
            cleaned = question.strip()
            if not cleaned:
                continue
            try:
                response = await self._visualization.create_chart(
                    dataset_id, cleaned
                )
            except LLMError:
                sections.append(
                    QASection(
                        question=cleaned,
                        answer="The AI model was unavailable for this question.",
                    )
                )
                continue
            except DataAssistantError as exc:
                sections.append(
                    QASection(
                        question=cleaned,
                        answer=f"The question could not be answered: {exc}",
                    )
                )
                continue

            chart_section: Optional[ChartSection] = None
            if response.chart_spec and response.chart_type is not None:
                chart_section = self._chart_section(
                    "Chart",
                    response.chart_type.value,
                    response.chart_spec,
                    response.table_data,
                )
            sections.append(
                QASection(
                    question=cleaned,
                    answer=response.answer,
                    chart=chart_section,
                )
            )
        return sections

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _chart_section(
        title: str,
        chart_type: str,
        chart_spec: dict,
        table: list[dict[str, Any]],
    ) -> ChartSection:
        """Render a chart spec to PNG, falling back to a table on failure."""
        png = figure_to_png(chart_spec)
        if png is not None:
            return ChartSection(
                title=title,
                chart_type=chart_type,
                render_mode="image",
                image_png=png,
            )
        return ChartSection(
            title=title,
            chart_type=chart_type,
            render_mode="table",
            table=table,
        )

    def _persist(
        self, report_id: str, pdf_bytes: bytes, metadata: ReportMetadata
    ) -> None:
        pdf_path = self._reports_dir / f"{report_id}.pdf"
        meta_path = self._reports_dir / f"{report_id}.json"
        pdf_path.write_bytes(pdf_bytes)
        meta_path.write_text(metadata.model_dump_json(), encoding="utf-8")
