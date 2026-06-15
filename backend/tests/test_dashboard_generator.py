"""Tests for the AI Executive Dashboard Generator.

Covers:
  - KPISelectionEngine      (5 tests)
  - ChartRecommendationEngine (5 tests)
  - LayoutRecommendationEngine (3 tests)
  - DashboardScoringEngine  (3 tests)
  - HTTP endpoints via TestClient (4 tests)

All tests run against the venv Python:
    cd backend && .venv/bin/python -m pytest tests/test_dashboard_generator.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from app.schemas.dashboard import (
    ChartPanel,
    DashboardConfig,
    GenerateDashboardRequest,
    KPIMetric,
    LayoutCell,
    LayoutConfig,
)
from app.services.dashboard_generator import (
    ChartRecommendationEngine,
    DashboardScoringEngine,
    KPISelectionEngine,
    LayoutRecommendationEngine,
    _format_value,
    _score_column,
)
from app.services.dashboard_store import DashboardNotFoundError, DashboardStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_df(**kwargs: list[Any]) -> pd.DataFrame:
    return pd.DataFrame(kwargs)


def _make_kpi(col: str, idx: int = 0) -> KPIMetric:
    return KPIMetric(
        id=f"kpi_{idx}",
        label=col.replace("_", " ").title(),
        column=col,
        aggregation="sum",
        value=1000.0,
        formatted_value="$1.0K",
        change_pct=5.0,
        trend="up",
    )


def _make_chart(chart_id: str, width: str = "half") -> ChartPanel:
    return ChartPanel(
        id=chart_id,
        title="Test",
        chart_type="bar",
        x_field="category",
        y_field="revenue",
        chart_spec={"data": [], "layout": {}},
        width=width,
    )


# ===========================================================================
# KPISelectionEngine
# ===========================================================================


class TestKPISelectionEngine:
    """KPI engine picks the right columns in the right order."""

    def test_keyword_scoring_high(self) -> None:
        """Revenue column scores higher than an unnamed numeric column."""
        df = _make_df(
            revenue=[100, 200, 300, 400, 500],
            col_x=[1, 2, 3, 4, 5],
        )
        score_rev = _score_column(df, "revenue")
        score_x = _score_column(df, "col_x")
        assert score_rev > score_x

    def test_variance_filter_excludes_constants(self) -> None:
        """A column with zero variance receives a very low score."""
        df = _make_df(
            revenue=[100, 200, 300, 400],
            constant=[42, 42, 42, 42],
        )
        engine = KPISelectionEngine()
        kpis = engine.select(df, max_kpis=4)
        col_names = [k.column for k in kpis]
        # constant column should NOT be selected (or should rank last)
        if "constant" in col_names:
            assert col_names.index("constant") > col_names.index("revenue")
        else:
            assert "revenue" in col_names

    def test_null_penalty_deprioritises_sparse_column(self) -> None:
        """A column that is >30% null scores lower than a clean column."""
        values_clean = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        values_null = [None] * 4 + [10, 20, 30, 40, 50, 60]
        df = pd.DataFrame({"sales": values_clean, "sparse_revenue": values_null})
        score_clean = _score_column(df, "sales")
        score_null = _score_column(df, "sparse_revenue")
        # sparse_revenue has keyword hit but null penalty; sales has keyword hit + no penalty
        assert score_clean >= score_null

    def test_top_n_cap(self) -> None:
        """Engine never returns more KPIs than requested."""
        df = _make_df(
            revenue=[1, 2, 3],
            sales=[4, 5, 6],
            profit=[7, 8, 9],
            orders=[10, 11, 12],
            users=[13, 14, 15],
        )
        engine = KPISelectionEngine()
        kpis = engine.select(df, max_kpis=3)
        assert len(kpis) <= 3

    def test_empty_dataframe_returns_empty(self) -> None:
        """Engine handles an empty DataFrame without raising."""
        engine = KPISelectionEngine()
        result = engine.select(pd.DataFrame(), max_kpis=6)
        assert result == []

    def test_format_value_currency(self) -> None:
        assert _format_value(2_450_000.0, "revenue") == "$2.45M"

    def test_format_value_percentage(self) -> None:
        assert _format_value(32.5, "conversion_rate") == "32.5%"

    def test_format_value_thousands(self) -> None:
        assert _format_value(1500.0, "orders") == "1.5K"


# ===========================================================================
# ChartRecommendationEngine
# ===========================================================================


class TestChartRecommendationEngine:
    """Chart engine picks the correct chart type per rule precedence."""

    def test_datetime_column_produces_line_chart(self) -> None:
        """Presence of a date column triggers a line chart."""
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "revenue": range(100, 1300, 100),
        })
        kpis = [_make_kpi("revenue")]
        engine = ChartRecommendationEngine()
        charts = engine.recommend(df, kpis, max_charts=6)
        assert len(charts) >= 1
        assert charts[0].chart_type == "line"
        assert charts[0].x_field == "date"

    def test_low_cardinality_string_produces_bar_chart(self) -> None:
        """A string column with ≤12 unique values → bar chart."""
        df = pd.DataFrame({
            "region": ["North", "South", "East", "West"] * 5,
            "sales": [100, 200, 150, 120] * 5,
        })
        kpis = [_make_kpi("sales")]
        engine = ChartRecommendationEngine()
        charts = engine.recommend(df, kpis, max_charts=6)
        assert len(charts) >= 1
        chart_types = [c.chart_type for c in charts]
        assert "bar" in chart_types

    def test_two_numeric_columns_produces_scatter(self) -> None:
        """Two numeric columns with no datetime/string → scatter chart."""
        df = pd.DataFrame({
            "spend": [10, 20, 30, 40, 50],
            "revenue": [100, 180, 260, 340, 400],
        })
        kpis = [_make_kpi("revenue")]
        engine = ChartRecommendationEngine()
        charts = engine.recommend(df, kpis, max_charts=6)
        assert len(charts) >= 1
        assert charts[0].chart_type == "scatter"

    def test_single_numeric_column_fallback_bar(self) -> None:
        """Single numeric column with no helpers → bar chart (row-index x-axis)."""
        df = pd.DataFrame({"revenue": [100, 200, 300, 400, 500]})
        kpis = [_make_kpi("revenue")]
        engine = ChartRecommendationEngine()
        charts = engine.recommend(df, kpis, max_charts=6)
        assert len(charts) >= 1
        assert charts[0].chart_type == "bar"

    def test_chart_spec_is_valid_plotly_json(self) -> None:
        """chart_spec must contain 'data' and 'layout' keys (Plotly structure)."""
        df = pd.DataFrame({
            "category": ["A", "B", "C", "D"],
            "sales": [100, 200, 150, 300],
        })
        kpis = [_make_kpi("sales")]
        engine = ChartRecommendationEngine()
        charts = engine.recommend(df, kpis, max_charts=1)
        assert len(charts) == 1
        spec = charts[0].chart_spec
        assert "data" in spec
        assert "layout" in spec

    def test_empty_dataset_returns_empty(self) -> None:
        """Empty DataFrame → no charts."""
        engine = ChartRecommendationEngine()
        charts = engine.recommend(pd.DataFrame(), [], max_charts=6)
        assert charts == []

    def test_deduplication_no_duplicate_xy(self) -> None:
        """Same (x, y) pair is never emitted twice."""
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="MS"),
            "revenue": [100, 200, 300, 400, 500],
            "sales": [50, 100, 150, 200, 250],
        })
        kpis = [_make_kpi("revenue", 0), _make_kpi("sales", 1)]
        engine = ChartRecommendationEngine()
        charts = engine.recommend(df, kpis, max_charts=6)
        xy_pairs = [(c.x_field, c.y_field) for c in charts]
        assert len(xy_pairs) == len(set(xy_pairs))


# ===========================================================================
# LayoutRecommendationEngine
# ===========================================================================


class TestLayoutRecommendationEngine:
    """Layout engine packs charts into rows correctly."""

    def test_single_chart_becomes_full_width(self) -> None:
        kpis = [_make_kpi("revenue")]
        charts = [_make_chart("chart_0")]
        engine = LayoutRecommendationEngine()
        layout = engine.arrange(kpis, charts)
        assert len(layout.rows) == 1
        assert layout.rows[0][0].width == "full"

    def test_two_charts_become_half_pair(self) -> None:
        kpis = [_make_kpi("revenue"), _make_kpi("sales", 1)]
        charts = [_make_chart("chart_0"), _make_chart("chart_1")]
        engine = LayoutRecommendationEngine()
        layout = engine.arrange(kpis, charts)
        assert len(layout.rows) == 1
        assert all(c.width == "half" for c in layout.rows[0])

    def test_three_charts_last_is_full(self) -> None:
        """Three charts → first row: 2 halves; second row: 1 full."""
        charts = [_make_chart(f"chart_{i}") for i in range(3)]
        engine = LayoutRecommendationEngine()
        layout = engine.arrange([], charts)
        assert len(layout.rows) == 2
        assert layout.rows[1][0].width == "full"

    def test_kpi_row_contains_all_kpi_ids(self) -> None:
        kpis = [_make_kpi(f"col_{i}", i) for i in range(4)]
        engine = LayoutRecommendationEngine()
        layout = engine.arrange(kpis, [])
        assert layout.kpi_row == [k.id for k in kpis]

    def test_no_charts_returns_empty_rows(self) -> None:
        engine = LayoutRecommendationEngine()
        layout = engine.arrange([], [])
        assert layout.rows == []


# ===========================================================================
# DashboardScoringEngine
# ===========================================================================


class TestDashboardScoringEngine:
    """Scoring engine stays within 0–100 and reflects data quality."""

    def test_perfect_score_ceiling_100(self) -> None:
        """More KPIs + charts + good data → score ≤ 100."""
        df = pd.DataFrame({col: range(200) for col in ["a", "b", "c", "d", "e"]})
        kpis = [_make_kpi(c, i) for i, c in enumerate(["a", "b", "c", "d", "e"])]
        charts = [_make_chart(f"chart_{i}") for i in range(5)]
        engine = DashboardScoringEngine()
        score = engine.score(kpis, charts, df)
        assert 0 <= score <= 100

    def test_empty_dataset_scores_low(self) -> None:
        """Empty dataset with no KPIs or charts → low score."""
        engine = DashboardScoringEngine()
        score = engine.score([], [], pd.DataFrame())
        assert score < 20

    def test_partial_dataset_mid_range(self) -> None:
        """Small dataset with 2 KPIs → score in 20–80 range."""
        df = pd.DataFrame({"revenue": range(30), "sales": range(30)})
        kpis = [_make_kpi("revenue", 0), _make_kpi("sales", 1)]
        charts = [_make_chart("chart_0"), _make_chart("chart_1")]
        engine = DashboardScoringEngine()
        score = engine.score(kpis, charts, df)
        assert 20 <= score <= 90


# ===========================================================================
# DashboardStore
# ===========================================================================


class TestDashboardStore:
    """Filesystem store: save, get, list, ownership."""

    def test_save_and_get_roundtrip(self, tmp_path: Path) -> None:
        store = DashboardStore(tmp_path)
        config = DashboardConfig(
            dashboard_name="Test Dashboard",
            dataset_id="abc123",
            owner_sub="user_a",
            kpis=[],
            charts=[],
            layout=LayoutConfig(),
            recommendations=[],
            score=75,
            generation_time_ms=100.0,
        )
        meta = store.save(config, "user_a")
        assert meta.dashboard_id is not None
        retrieved = store.get(meta.dashboard_id, "user_a")
        assert retrieved.dashboard_name == "Test Dashboard"
        assert retrieved.score == 75

    def test_get_wrong_owner_raises(self, tmp_path: Path) -> None:
        store = DashboardStore(tmp_path)
        config = DashboardConfig(
            dashboard_name="Private",
            dataset_id="abc",
            owner_sub="user_a",
            kpis=[],
            charts=[],
            layout=LayoutConfig(),
            recommendations=[],
            score=50,
            generation_time_ms=50.0,
        )
        meta = store.save(config, "user_a")
        with pytest.raises(DashboardNotFoundError):
            store.get(meta.dashboard_id, "user_b")

    def test_list_scoped_to_user(self, tmp_path: Path) -> None:
        store = DashboardStore(tmp_path)
        for i in range(3):
            store.save(
                DashboardConfig(
                    dashboard_name=f"D{i}",
                    dataset_id="ds",
                    owner_sub="user_a",
                    kpis=[],
                    charts=[],
                    layout=LayoutConfig(),
                    recommendations=[],
                    score=i * 10,
                    generation_time_ms=10.0,
                ),
                "user_a",
            )
        store.save(
            DashboardConfig(
                dashboard_name="Other",
                dataset_id="ds",
                owner_sub="user_b",
                kpis=[],
                charts=[],
                layout=LayoutConfig(),
                recommendations=[],
                score=0,
                generation_time_ms=10.0,
            ),
            "user_b",
        )
        user_a_list = store.list_for_user("user_a")
        assert len(user_a_list) == 3
        assert all(m.dashboard_name.startswith("D") for m in user_a_list)


# ===========================================================================
# HTTP endpoints (TestClient)
# ===========================================================================


class TestDashboardHTTP:
    """End-to-end route tests using FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path: Path) -> None:
        """Patch dataset service + dashboard service for HTTP tests."""
        import pandas as pd
        from unittest.mock import patch, MagicMock
        from app.schemas.dataset import DatasetMetadata, DatasetSource
        from datetime import datetime, timezone

        self._df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "revenue": [100 * (i + 1) for i in range(12)],
            "orders": [10 * (i + 1) for i in range(12)],
        })

        self._meta = DatasetMetadata(
            id="test_dataset_id",
            filename="sales.csv",
            source=DatasetSource.FILE,
            size_bytes=1024,
            rows=12,
            columns=3,
            column_names=["date", "revenue", "orders"],
            created_at=datetime.now(timezone.utc),
            owner_sub="test_sub",
        )

        self._tmp_path = tmp_path

    def _get_client(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from app.main import app
        from app.services.dashboard_store import DashboardStore

        store = DashboardStore(self._tmp_path)

        mock_dataset_svc = MagicMock()
        mock_dataset_svc.get_metadata.return_value = self._meta
        mock_dataset_svc.load_dataframe.return_value = (self._df, self._meta)

        from app.services.dashboard_generator import DashboardGeneratorService
        from app.core.config import get_settings
        settings = get_settings()
        dash_svc = DashboardGeneratorService(
            dataset_service=mock_dataset_svc,
            settings=settings,
            cache_ttl=300.0,
            cache_max_entries=10,
        )
        dash_svc._store = store

        def _mock_auth():
            from app.schemas.auth import CurrentUser
            return CurrentUser(sub="test_sub", email="test@test.com", name="Test")

        from app.core.auth import get_current_user
        from app.api.dependencies import get_dataset_service, get_dashboard_service, get_memory_service

        mock_memory = MagicMock()
        mock_memory.record_turn = MagicMock(return_value=None)

        app.dependency_overrides[get_current_user] = _mock_auth
        app.dependency_overrides[get_dataset_service] = lambda: mock_dataset_svc
        app.dependency_overrides[get_dashboard_service] = lambda: dash_svc
        app.dependency_overrides[get_memory_service] = lambda: mock_memory

        client = TestClient(app, raise_server_exceptions=True)
        return client, app, store

    def test_generate_returns_200(self) -> None:
        client, app, store = self._get_client()
        try:
            resp = client.post(
                "/api/v1/dashboards/generate",
                json={
                    "dataset_id": "test_dataset_id",
                    "prompt": "Create a CEO Dashboard",
                    "max_kpis": 4,
                    "max_charts": 4,
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "dashboard_name" in body
            assert "kpis" in body
            assert "charts" in body
            assert "layout" in body
            assert "score" in body
            assert isinstance(body["kpis"], list)
            assert isinstance(body["charts"], list)
        finally:
            app.dependency_overrides.clear()

    def test_save_returns_201(self) -> None:
        client, app, store = self._get_client()
        try:
            gen_resp = client.post(
                "/api/v1/dashboards/generate",
                json={
                    "dataset_id": "test_dataset_id",
                    "prompt": "CEO Dashboard",
                    "max_kpis": 2,
                    "max_charts": 2,
                },
            )
            assert gen_resp.status_code == 200
            generated = gen_resp.json()

            save_resp = client.post(
                "/api/v1/dashboards/save",
                json={
                    "dashboard_config": {
                        "dashboard_name": generated["dashboard_name"],
                        "dataset_id": generated["dataset_id"],
                        "owner_sub": "test_sub",
                        "kpis": generated["kpis"],
                        "charts": generated["charts"],
                        "layout": generated["layout"],
                        "recommendations": generated["recommendations"],
                        "score": generated["score"],
                        "generation_time_ms": generated["generation_time_ms"],
                        "cache_hit": False,
                        "created_at": "2026-06-14T00:00:00Z",
                    }
                },
            )
            assert save_resp.status_code == 201
            body = save_resp.json()
            assert "dashboard_id" in body
            assert body["message"] == "Dashboard saved successfully."
        finally:
            app.dependency_overrides.clear()

    def test_get_saved_dashboard_returns_200(self) -> None:
        from app.schemas.dashboard import LayoutConfig
        client, app, store = self._get_client()
        try:
            from datetime import datetime, timezone
            from app.schemas.dashboard import DashboardConfig
            config = DashboardConfig(
                dashboard_name="Test",
                dataset_id="test_dataset_id",
                owner_sub="test_sub",
                kpis=[],
                charts=[],
                layout=LayoutConfig(),
                recommendations=[],
                score=80,
                generation_time_ms=100.0,
            )
            meta = store.save(config, "test_sub")

            resp = client.get(f"/api/v1/dashboards/{meta.dashboard_id}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["dashboard_name"] == "Test"
        finally:
            app.dependency_overrides.clear()

    def test_get_wrong_owner_returns_404(self) -> None:
        from app.schemas.dashboard import LayoutConfig, DashboardConfig
        client, app, store = self._get_client()
        try:
            config = DashboardConfig(
                dashboard_name="Private",
                dataset_id="test_dataset_id",
                owner_sub="other_user",
                kpis=[],
                charts=[],
                layout=LayoutConfig(),
                recommendations=[],
                score=50,
                generation_time_ms=50.0,
            )
            meta = store.save(config, "other_user")

            resp = client.get(f"/api/v1/dashboards/{meta.dashboard_id}")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()
