"""Execute supported query plans directly in the database (SQL pushdown).

Aggregates run over the full table — the point of Phase 6 is to avoid loading
large tables into pandas while preserving correctness. Results are built with
the shared formatters so they are identical to the pandas backend.
"""

from __future__ import annotations

import threading

from sqlalchemy import MetaData, Table
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import DatabaseError
from app.schemas.dataset import DatasetMetadata
from app.schemas.query import Operation, QueryPlan
from app.services.analytics_results import (
    ExecutionResult,
    grouped_answer,
    scalar_answer,
)
from app.services.connection_service import ConnectionService
from app.services.sql_translator import SQLTranslator


class SqlExecutor:
    """Run validated plans against a database via SQLAlchemy Core."""

    def __init__(
        self, connections: ConnectionService, translator: SQLTranslator
    ) -> None:
        self._connections = connections
        self._translator = translator
        self._tables: dict[tuple, Table] = {}
        self._lock = threading.Lock()

    def supports(self, operation: Operation) -> bool:
        """Whether an operation can be pushed down."""
        return self._translator.supports(operation)

    def execute(
        self, metadata: DatasetMetadata, plan: QueryPlan
    ) -> ExecutionResult:
        """Translate and execute a plan against the database.

        Raises:
            DatabaseError: on any SQL/engine failure (triggers pandas fallback).
        """
        engine = self._connections.get_engine(metadata.connection_id)
        table = self._reflect(
            metadata.connection_id, engine, metadata.db_schema, metadata.table_name
        )
        statement = self._translator.translate(plan, table)

        try:
            with engine.connect() as connection:
                if self._translator.is_scalar(plan.operation):
                    value = connection.execute(statement).scalar_one()
                    return scalar_answer(plan, value)
                rows = connection.execute(statement).all()
        except SQLAlchemyError as exc:
            raise DatabaseError(f"SQL pushdown failed: {exc}") from exc

        pairs = [(row[0], row[1]) for row in rows]
        value_field = (
            "count" if plan.operation is Operation.GROUPBY_COUNT else plan.column
        )
        return grouped_answer(plan, pairs, value_field=value_field)

    def _reflect(self, connection_id, engine, schema, table_name: str) -> Table:
        """Reflect a table, caching the result per (connection, schema, table)."""
        key = (connection_id, schema, table_name)
        with self._lock:
            cached = self._tables.get(key)
        if cached is not None:
            return cached
        try:
            table = Table(
                table_name, MetaData(), autoload_with=engine, schema=schema
            )
        except SQLAlchemyError as exc:
            raise DatabaseError(
                f"Could not reflect table '{table_name}'."
            ) from exc
        with self._lock:
            self._tables[key] = table
        return table
