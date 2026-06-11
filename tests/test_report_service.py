"""Unit tests for the report service.

These tests run without Ollama (a fake planner is injected) and without kaleido
(``figure_to_png`` is monkeypatched to force the table fallback), so they
exercise the full assembly + PDF build deterministically.
"""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from app.core.config import Settings
from app.core.exceptions import LLMError
from app.schemas.report import ReportRequest
from app.services.analytics_service import AnalyticsService
from app.services.dataset_service import DatasetService
from app.services.report_service import ReportService
from app.services.visualization_service import VisualizationService


class FakePlanner:
    """Returns a preset plan dict (used only for AI/QA sections)."""

    def __init__(self, plan: dict | None = None) -> None:
        self._plan = plan or {"operation": "row_count"}

    async def generate_plan(self, question: str, schema: dict) -> dict:
        return self._plan


class RaisingPlanner:
    """Always fails, to test per-question error containment."""

    async def generate_plan(self, question: str, schema: dict) -> dict:
        raise LLMError("model down")


def _build(tmp_path, planner) -> tuple[ReportService, str]:
    settings = Settings(
        upload_dir=tmp_path / "uploads", reports_dir=tmp_path / "reports"
    )
    datasets = DatasetService(settings)
    frame = pd.DataFrame(
        {
            "region": ["North", "South", "North", "East"],
            "product": ["a", "b", "a", "c"],
            "sales": [100, 50, 30, 20],
            "qty": [1, 2, 3, 4],
        }
    )
    meta = datasets.save_csv("data.csv", frame.to_csv(index=False).encode())
    analytics = AnalyticsService(datasets, planner)
    visualization = VisualizationService(analytics)
    service = ReportService(
        datasets,
        analytics,
        visualization,
        reports_dir=settings.reports_dir,
        report_version="1.0",
    )
    return service, meta.id


@pytest.fixture(autouse=True)
def _no_kaleido(monkeypatch):
    """Force the table fallback so tests never depend on kaleido."""
    monkeypatch.setattr(
        "app.services.report_service.figure_to_png", lambda spec: None
    )


def test_battery_only_report(tmp_path):
    service, dataset_id = _build(tmp_path, FakePlanner())
    meta = asyncio.run(service.generate(ReportRequest(dataset_id=dataset_id)))

    assert meta.ai_section_count == 0
    assert meta.deterministic_section_count >= 3  # summary, stats, charts, insights
    assert meta.report_version == "1.0"
    assert meta.dataset_filename == "data.csv"

    pdf_path = tmp_path / "reports" / f"{meta.report_id}.pdf"
    json_path = tmp_path / "reports" / f"{meta.report_id}.json"
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert json_path.is_file()
    assert meta.size_bytes > 0


def test_report_with_ai_section(tmp_path):
    plan = {
        "operation": "groupby_sum",
        "column": "sales",
        "group_by": "region",
        "chart_type": "bar",
    }
    service, dataset_id = _build(tmp_path, FakePlanner(plan))
    meta = asyncio.run(
        service.generate(
            ReportRequest(dataset_id=dataset_id, questions=["sales by region"])
        )
    )
    assert meta.ai_section_count == 1


def test_ai_section_llm_failure_is_contained(tmp_path):
    service, dataset_id = _build(tmp_path, RaisingPlanner())
    # The whole report must still build even when a question's LLM call fails.
    meta = asyncio.run(
        service.generate(
            ReportRequest(dataset_id=dataset_id, questions=["anything"])
        )
    )
    assert meta.ai_section_count == 1
    pdf_path = tmp_path / "reports" / f"{meta.report_id}.pdf"
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_list_reports(tmp_path):
    service, dataset_id = _build(tmp_path, FakePlanner())
    asyncio.run(service.generate(ReportRequest(dataset_id=dataset_id)))
    asyncio.run(service.generate(ReportRequest(dataset_id=dataset_id)))
    assert len(service.list_reports()) == 2
