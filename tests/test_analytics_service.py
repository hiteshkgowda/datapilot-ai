"""Unit tests for the analytics service.

These tests exercise the safety-critical core — plan validation and the fixed
pandas executor — using a *mocked* planner, so no running Ollama is required.
"""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from datetime import datetime, timezone

from app.core.exceptions import PlanValidationError
from app.schemas.dataset import DatasetMetadata, DatasetSource
from app.services.analytics_service import AnalyticsService
from app.services.dataset_service import DatasetService


class FakePlanner:
    """A planner stub that returns a preset raw plan dict."""

    def __init__(self, plan: dict) -> None:
        self._plan = plan

    async def generate_plan(self, question: str, schema: dict) -> dict:
        return self._plan


class FakeDatasetService:
    """A dataset-service stub returning a fixed (file) DataFrame and schema."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def get_metadata(self, dataset_id: str) -> DatasetMetadata:
        return DatasetMetadata(
            id=dataset_id,
            filename="fake.csv",
            source=DatasetSource.FILE,
            size_bytes=0,
            rows=int(self._frame.shape[0]),
            columns=int(self._frame.shape[1]),
            column_names=[str(c) for c in self._frame.columns],
            created_at=datetime.now(timezone.utc),
        )

    def get_schema(self, dataset_id: str):
        return DatasetService._build_schema(self._frame)

    def load_dataframe(self, dataset_id: str):
        return self._frame, self.get_metadata(dataset_id)

    def load_with_schema(self, dataset_id: str):
        return self._frame, DatasetService._build_schema(self._frame)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "region": ["North", "South", "North", "East"],
            "product": ["a", "b", "a", "c"],
            "sales": [100, 50, 30, 20],
            "qty": [1, 2, 3, 4],
        }
    )


def _ask(plan: dict, question: str = "?"):
    """Run answer_question synchronously for a given mocked plan."""
    service = AnalyticsService(FakeDatasetService(_frame()), FakePlanner(plan))
    return asyncio.run(service.answer_question("dataset-1", question))


# --------------------------------------------------------------------------- #
# Valid plans
# --------------------------------------------------------------------------- #
def test_row_count():
    result = _ask({"operation": "row_count"})
    assert "4" in result.answer
    assert result.execution_time_ms >= 0
    assert result.total_time_ms >= 0
    assert result.query_plan.operation.value == "row_count"


def test_column_count():
    result = _ask({"operation": "column_count"})
    assert "4" in result.answer


def test_sum():
    result = _ask({"operation": "sum", "column": "sales"})
    assert "200" in result.answer


def test_average():
    result = _ask({"operation": "average", "column": "qty"})
    assert "2.5" in result.answer


def test_max_and_min():
    assert "100" in _ask({"operation": "max", "column": "sales"}).answer
    assert "20" in _ask({"operation": "min", "column": "sales"}).answer


def test_groupby_sum():
    result = _ask(
        {"operation": "groupby_sum", "column": "sales", "group_by": "region"}
    )
    # North = 100 + 30 = 130 and should lead (sorted descending).
    assert "North" in result.answer
    assert "130" in result.answer


# --------------------------------------------------------------------------- #
# top_n execution
# --------------------------------------------------------------------------- #
def test_top_n_execution_and_ordering():
    result = _ask(
        {"operation": "top_n", "column": "sales", "group_by": "product", "n": 2}
    )
    lines = result.answer.splitlines()
    # Header + 2 rows; product 'a' (130) must rank above 'b' (50).
    assert len(lines) == 3
    assert "a" in lines[1]
    assert "130" in lines[1]
    pos_a = result.answer.index("a:")
    pos_b = result.answer.index("b:")
    assert pos_a < pos_b


# --------------------------------------------------------------------------- #
# Invalid plans
# --------------------------------------------------------------------------- #
def test_invalid_operation_rejected():
    with pytest.raises(PlanValidationError):
        _ask({"operation": "frobnicate", "column": "sales"})


def test_missing_column_rejected():
    with pytest.raises(PlanValidationError):
        _ask({"operation": "sum", "column": "does_not_exist"})


def test_numeric_validation_rejects_text_column():
    with pytest.raises(PlanValidationError):
        _ask({"operation": "sum", "column": "region"})


def test_sum_requires_column():
    with pytest.raises(PlanValidationError):
        _ask({"operation": "sum"})


def test_groupby_requires_group_by():
    with pytest.raises(PlanValidationError):
        _ask({"operation": "groupby_sum", "column": "sales"})


def test_top_n_requires_n():
    with pytest.raises(PlanValidationError):
        _ask({"operation": "top_n", "column": "sales", "group_by": "product"})


# --------------------------------------------------------------------------- #
# New operations: groupby_count and xy_select
# --------------------------------------------------------------------------- #
def test_groupby_count():
    result = _ask({"operation": "groupby_count", "group_by": "region"})
    # North appears twice, South once, East once.
    assert "North" in result.answer
    assert "2" in result.answer


def test_groupby_count_requires_group_by():
    with pytest.raises(PlanValidationError):
        _ask({"operation": "groupby_count"})


def test_xy_select():
    result = _ask(
        {"operation": "xy_select", "x_column": "sales", "y_column": "qty"}
    )
    assert "point" in result.answer.lower()


def test_xy_select_requires_numeric_columns():
    with pytest.raises(PlanValidationError):
        _ask({"operation": "xy_select", "x_column": "region", "y_column": "qty"})


def test_xy_select_requires_both_columns():
    with pytest.raises(PlanValidationError):
        _ask({"operation": "xy_select", "x_column": "sales"})
