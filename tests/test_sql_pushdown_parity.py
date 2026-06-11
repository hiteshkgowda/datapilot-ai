"""SQL pushdown vs pandas: parity, full-table semantics, NULL groups, fallback."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.core.crypto import CredentialCipher
from app.core.exceptions import DatabaseError
from app.schemas.connection import ConnectionCreate, DbType, RegisterTableRequest
from app.schemas.query import Operation, QueryPlan
from app.services.analytics_service import AnalyticsService
from app.services.connection_service import ConnectionService
from app.services.dataset_service import DatasetService
from app.services.sql_executor import SqlExecutor
from app.services.sql_translator import SQLTranslator


class FakePlanner:
    async def generate_plan(self, question, schema):
        return {"operation": "row_count"}


def _setup(tmp_path, db_max_rows=25000, with_null=False):
    db = tmp_path / "shop.db"
    engine = create_engine(f"sqlite:///{db}")
    rows = [
        ("North", 100), ("North", 30), ("North", 10),
        ("South", 50), ("South", 5),
        ("East", 20),
    ]
    if with_null:
        rows.append((None, 7))
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sales (region TEXT, amount INTEGER)"))
        for region, amount in rows:
            conn.execute(
                text("INSERT INTO sales (region, amount) VALUES (:r, :a)"),
                {"r": region, "a": amount},
            )
    engine.dispose()

    settings = Settings(
        connections_dir=tmp_path / "connections",
        upload_dir=tmp_path / "uploads",
        db_max_rows=db_max_rows,
    )
    connections = ConnectionService(settings, CredentialCipher(None))
    datasets = DatasetService(settings, connections)
    conn_meta = connections.create_connection(
        ConnectionCreate(name="local", db_type=DbType.SQLITE, database=str(db))
    )
    schema = next(
        t for t in connections.list_tables(conn_meta.id) if t.name == "sales"
    ).schema_name
    dataset = datasets.register_table(
        conn_meta.id, RegisterTableRequest(schema_name=schema, table="sales")
    )

    sql_service = AnalyticsService(
        datasets,
        FakePlanner(),
        sql_executor=SqlExecutor(connections, SQLTranslator()),
    )
    pandas_service = AnalyticsService(datasets, FakePlanner(), sql_executor=None)
    return sql_service, pandas_service, dataset.id


def _run(service, dataset_id, plan):
    return asyncio.run(service.execute_plan(dataset_id, plan)).result


PLANS = [
    QueryPlan(operation=Operation.ROW_COUNT),
    QueryPlan(operation=Operation.SUM, column="amount"),
    QueryPlan(operation=Operation.AVERAGE, column="amount"),
    QueryPlan(operation=Operation.MAX, column="amount"),
    QueryPlan(operation=Operation.MIN, column="amount"),
    QueryPlan(operation=Operation.GROUPBY_SUM, column="amount", group_by="region"),
    QueryPlan(operation=Operation.GROUPBY_COUNT, group_by="region"),
    QueryPlan(operation=Operation.TOP_N, column="amount", group_by="region", n=2),
]


@pytest.mark.parametrize("plan", PLANS, ids=[p.operation.value for p in PLANS])
def test_sql_matches_pandas(tmp_path, plan):
    sql_service, pandas_service, dataset_id = _setup(tmp_path)
    sql_result = _run(sql_service, dataset_id, plan)
    pandas_result = _run(pandas_service, dataset_id, plan)
    assert sql_result == pandas_result


def test_pushdown_uses_full_table_beyond_cap(tmp_path):
    # Cap below table size: pushdown aggregates all 6 rows; pandas only the cap.
    sql_service, pandas_service, dataset_id = _setup(tmp_path, db_max_rows=3)
    plan = QueryPlan(operation=Operation.ROW_COUNT)
    assert _run(sql_service, dataset_id, plan).table[0]["value"] == 6
    assert _run(pandas_service, dataset_id, plan).table[0]["value"] == 3


def test_sql_includes_null_group_pandas_drops_it(tmp_path):
    sql_service, pandas_service, dataset_id = _setup(tmp_path, with_null=True)
    plan = QueryPlan(operation=Operation.GROUPBY_COUNT, group_by="region")
    sql_keys = {row["region"] for row in _run(sql_service, dataset_id, plan).table}
    pandas_keys = {
        row["region"] for row in _run(pandas_service, dataset_id, plan).table
    }
    assert None in sql_keys  # SQL keeps the NULL group
    assert None not in pandas_keys  # pandas drops it (documented difference)


def test_fallback_to_pandas_on_sql_error(tmp_path, monkeypatch):
    sql_service, _pandas, dataset_id = _setup(tmp_path)

    def boom(metadata, plan):
        raise DatabaseError("simulated SQL failure")

    monkeypatch.setattr(sql_service._sql_executor, "execute", boom)
    # Still returns the correct (pandas-computed) result.
    result = _run(sql_service, dataset_id, QueryPlan(operation=Operation.SUM, column="amount"))
    assert result.table[0]["value"] == 215
