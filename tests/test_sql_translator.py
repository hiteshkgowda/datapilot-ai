"""Unit tests for the SQL translator (SQLite reflection)."""

from __future__ import annotations

import pytest
from sqlalchemy import MetaData, Table, create_engine, text

from app.core.exceptions import PlanValidationError
from app.schemas.query import Operation, QueryPlan
from app.services.sql_translator import SQLTranslator


@pytest.fixture()
def table(tmp_path):
    db = tmp_path / "t.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sales (region TEXT, amount INTEGER)"))
    reflected = Table("sales", MetaData(), autoload_with=engine)
    engine.dispose()
    return reflected


def _sql(plan, table) -> str:
    return str(SQLTranslator().translate(plan, table)).lower()


def test_supports_and_is_scalar():
    t = SQLTranslator()
    assert t.supports(Operation.GROUPBY_SUM)
    assert t.supports(Operation.ROW_COUNT)
    assert not t.supports(Operation.COLUMN_COUNT)
    assert not t.supports(Operation.XY_SELECT)
    assert t.is_scalar(Operation.SUM)
    assert not t.is_scalar(Operation.GROUPBY_SUM)


def test_translate_scalar(table):
    sql = _sql(QueryPlan(operation=Operation.SUM, column="amount"), table)
    assert "sum(" in sql


def test_translate_groupby(table):
    sql = _sql(
        QueryPlan(operation=Operation.GROUPBY_SUM, column="amount", group_by="region"),
        table,
    )
    assert "group by" in sql and "order by" in sql


def test_translate_top_n_has_limit(table):
    sql = _sql(
        QueryPlan(
            operation=Operation.TOP_N, column="amount", group_by="region", n=3
        ),
        table,
    )
    assert "limit" in sql


def test_unknown_column_is_rejected(table):
    with pytest.raises(PlanValidationError):
        SQLTranslator().translate(
            QueryPlan(operation=Operation.SUM, column="missing"), table
        )
