"""Shared test helpers — no pytest fixtures here, just reusable factories."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy import Column, Float, Integer, MetaData, Table, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from app.services.crud_audit import JsonlAuditLogger
from app.services.crud_executor import CrudExecutor
from app.services.crud_validator import ConfirmationTokenService, CrudValidator


# ── SQLite helpers ────────────────────────────────────────────────────────────


def make_engine() -> Engine:
    """Return a fresh in-memory SQLite engine with a single shared connection.

    ``StaticPool`` ensures all ``engine.begin()`` / ``engine.connect()`` calls
    reach the same underlying connection, so the in-memory database is never
    accidentally empty when a second connection opens.
    """
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def make_products_table(engine: Engine) -> Table:
    """Create and populate a ``products`` table; return the Table object."""
    meta = MetaData()
    table = Table(
        "products",
        meta,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("name", Text, nullable=False),
        Column("price", Float, nullable=True),
        Column("active", Integer, default=1),
        Column("category", Text, nullable=True),
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            table.insert(),
            [
                {"name": "Widget A", "price": 9.99,  "active": 1, "category": "tools"},
                {"name": "Widget B", "price": 19.99, "active": 1, "category": "tools"},
                {"name": "Gadget X", "price": 49.99, "active": 0, "category": "electronics"},
            ],
        )
    return table


# ── Service factories ─────────────────────────────────────────────────────────


def make_audit_logger(audit_dir: Path) -> JsonlAuditLogger:
    return JsonlAuditLogger(audit_dir)


def make_token_service(ttl_seconds: int = 300) -> ConfirmationTokenService:
    return ConfirmationTokenService(secret_key="test-secret-key", ttl_seconds=ttl_seconds)


def make_validator(
    max_rows: int = 500,
    token_svc: ConfirmationTokenService | None = None,
) -> CrudValidator:
    return CrudValidator(
        max_affected_rows=max_rows,
        confirmation_service=token_svc or make_token_service(),
    )


def make_executor(rollback_dir: Path) -> CrudExecutor:
    return CrudExecutor(
        rollback_dir=rollback_dir,
        rollback_ttl_seconds=3600,
        max_rollback_rows=1000,
    )


# ── ConnectionService mock ────────────────────────────────────────────────────


def mock_connection_service(owner_sub: str, engine: Engine) -> MagicMock:
    """Return a ConnectionService stub for the given owner and engine."""
    svc = MagicMock()
    record = MagicMock()
    record.owner_sub = owner_sub
    svc._read_record.return_value = record
    svc.get_engine.return_value = engine
    # describe_table returns lightweight column descriptors
    col_id = MagicMock(); col_id.name = "id";       col_id.data_type = "INTEGER"
    col_nm = MagicMock(); col_nm.name = "name";     col_nm.data_type = "TEXT"
    col_pr = MagicMock(); col_pr.name = "price";    col_pr.data_type = "FLOAT"
    col_ac = MagicMock(); col_ac.name = "active";   col_ac.data_type = "INTEGER"
    col_ct = MagicMock(); col_ct.name = "category"; col_ct.data_type = "TEXT"
    svc.describe_table.return_value = [col_id, col_nm, col_pr, col_ac, col_ct]
    return svc


# ── Row counting helper ───────────────────────────────────────────────────────


def count_rows(engine: Engine, table: Table, **filters: Any) -> int:
    """Return the number of rows in ``table`` matching simple equality filters."""
    from sqlalchemy import select, func
    stmt = select(func.count()).select_from(table)
    for col, val in filters.items():
        stmt = stmt.where(table.c[col] == val)
    with engine.connect() as conn:
        return conn.execute(stmt).scalar_one()


def fetch_rows(engine: Engine, table: Table) -> list[dict]:
    """Return all rows from ``table`` as a list of dicts."""
    from sqlalchemy import select
    with engine.connect() as conn:
        result = conn.execute(select(table))
        cols = list(result.keys())
        return [dict(zip(cols, row)) for row in result.all()]
