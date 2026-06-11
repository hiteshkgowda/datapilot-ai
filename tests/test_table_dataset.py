"""Integration tests: a database table behaves like a dataset (SQLite-based).

Proves the core Phase 5 claim — a registered table flows through the same
DatasetService contract and is analyzed by the existing AnalyticsService with
no changes.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.core.crypto import CredentialCipher
from app.schemas.connection import ConnectionCreate, DbType, RegisterTableRequest
from app.schemas.dataset import DatasetSource
from app.schemas.query import Operation, QueryPlan
from app.services.analytics_service import AnalyticsService
from app.services.connection_service import ConnectionService
from app.services.dataset_service import DatasetService


class FakePlanner:
    async def generate_plan(self, question, schema):
        return {"operation": "row_count"}


def _setup(tmp_path):
    db_path = tmp_path / "sample.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sales (region TEXT, amount INTEGER)"))
        conn.execute(
            text(
                "INSERT INTO sales (region, amount) VALUES "
                "('North', 100), ('South', 50), ('North', 30), ('East', 20)"
            )
        )
    engine.dispose()

    settings = Settings(
        connections_dir=tmp_path / "connections", upload_dir=tmp_path / "uploads"
    )
    connections = ConnectionService(settings, CredentialCipher(None))
    datasets = DatasetService(settings, connections)
    conn_meta = connections.create_connection(
        ConnectionCreate(name="local", db_type=DbType.SQLITE, database=str(db_path))
    )
    tables = connections.list_tables(conn_meta.id)
    schema = next(t for t in tables if t.name == "sales").schema_name
    return datasets, connections, conn_meta.id, schema


def test_register_table_creates_dataset(tmp_path):
    datasets, _conns, conn_id, schema = _setup(tmp_path)
    meta = datasets.register_table(
        conn_id, RegisterTableRequest(schema_name=schema, table="sales")
    )
    assert meta.source is DatasetSource.TABLE
    assert meta.estimated_row_count == 4
    assert meta.truncated is False
    assert meta.columns == 2
    assert set(meta.column_names) == {"region", "amount"}
    # The metadata sidecar is listed like any other dataset.
    assert any(d.id == meta.id for d in datasets.list_datasets())


def test_table_dataset_loads_and_analyzes(tmp_path):
    datasets, _conns, conn_id, schema = _setup(tmp_path)
    meta = datasets.register_table(
        conn_id, RegisterTableRequest(schema_name=schema, table="sales")
    )

    # Same DatasetService contract as a file dataset.
    frame, dataset_schema = datasets.load_with_schema(meta.id)
    assert frame.shape == (4, 2)
    assert "amount" in dataset_schema.numeric_columns

    # The existing AnalyticsService runs unchanged on the table dataset.
    analytics = AnalyticsService(datasets, FakePlanner())
    plan = QueryPlan(
        operation=Operation.GROUPBY_SUM, column="amount", group_by="region"
    )
    analysis = asyncio.run(analytics.execute_plan(meta.id, plan))
    # North = 100 + 30 = 130 leads.
    assert analysis.result.table[0]["region"] == "North"
    assert analysis.result.table[0]["amount"] == 130
