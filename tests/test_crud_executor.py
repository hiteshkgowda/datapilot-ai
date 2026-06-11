"""SQLite integration tests for CrudExecutor: all 5 operations + rollback."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.core.exceptions import RollbackError
from app.schemas.crud import CrudOperation, CrudPlan, FilterOperator, RowFilter
from app.services.crud_audit import JsonlAuditLogger
from app.services.crud_executor import CrudExecutor


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _make_db(tmp_path):
    db = tmp_path / "exec.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE items ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  label TEXT NOT NULL,"
            "  qty   INTEGER DEFAULT 0,"
            "  removed INTEGER DEFAULT 0"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO items (label, qty) VALUES "
            "('A', 10), ('B', 20), ('C', 30)"
        ))
    return engine


def _executor(tmp_path) -> CrudExecutor:
    return CrudExecutor(
        rollback_dir=tmp_path / "rollback",
        rollback_ttl_seconds=3600,
        max_rollback_rows=1000,
    )


def _audit(tmp_path) -> JsonlAuditLogger:
    return JsonlAuditLogger(tmp_path / "audit")


def _row_count(engine, label=None) -> int:
    with engine.connect() as conn:
        if label:
            row = conn.execute(
                text("SELECT COUNT(*) FROM items WHERE label = :l"), {"l": label}
            ).scalar_one()
        else:
            row = conn.execute(text("SELECT COUNT(*) FROM items")).scalar_one()
    return row


def _fetch(engine, where_id: int) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM items WHERE id = :i"), {"i": where_id}
        ).mappings().one()
    return dict(row)


# ------------------------------------------------------------------ #
# CREATE
# ------------------------------------------------------------------ #

def test_create_inserts_row(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.CREATE,
        table_name="items",
        row_data={"label": "D", "qty": 40},
    )
    resp = ex.execute(plan, "c1", engine, _audit(tmp_path), "add item D")
    assert resp.affected_rows == 1
    assert _row_count(engine) == 4


def test_create_rollback(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.CREATE,
        table_name="items",
        row_data={"label": "D", "qty": 40},
    )
    resp = ex.execute(plan, "c1", engine, _audit(tmp_path), "add item D")
    assert resp.rollback_supported is True
    assert _row_count(engine) == 4

    audit = _audit(tmp_path)
    rb_resp = ex.rollback("c1", resp.rollback_token, engine, audit)
    assert rb_resp.restored_rows == 1
    assert _row_count(engine) == 3


# ------------------------------------------------------------------ #
# UPDATE
# ------------------------------------------------------------------ #

def test_update_single_row(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.UPDATE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        set_values={"qty": 99},
    )
    resp = ex.execute(plan, "c1", engine, _audit(tmp_path), "set qty=99 for id=1")
    assert resp.affected_rows == 1
    assert _fetch(engine, 1)["qty"] == 99


def test_update_rollback(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.UPDATE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        set_values={"qty": 99},
    )
    resp = ex.execute(plan, "c1", engine, _audit(tmp_path), "update qty")
    assert _fetch(engine, 1)["qty"] == 99

    ex.rollback("c1", resp.rollback_token, engine, _audit(tmp_path))
    assert _fetch(engine, 1)["qty"] == 10  # original value


# ------------------------------------------------------------------ #
# BULK_UPDATE
# ------------------------------------------------------------------ #

def test_bulk_update(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.BULK_UPDATE,
        table_name="items",
        filters=[RowFilter(column="qty", operator=FilterOperator.GT, value=0)],
        set_values={"qty": 0},
    )
    resp = ex.execute(plan, "c1", engine, _audit(tmp_path), "zero all qtys")
    assert resp.affected_rows == 3
    with engine.connect() as conn:
        total = conn.execute(text("SELECT SUM(qty) FROM items")).scalar_one()
    assert total == 0


# ------------------------------------------------------------------ #
# SOFT_DELETE
# ------------------------------------------------------------------ #

def test_soft_delete_stamps_column(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.SOFT_DELETE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=2)],
        soft_delete_column="removed",
        soft_delete_value=1,
    )
    resp = ex.execute(plan, "c1", engine, _audit(tmp_path), "soft delete id=2")
    assert resp.affected_rows == 1
    assert _fetch(engine, 2)["removed"] == 1


def test_soft_delete_default_value(tmp_path):
    """When soft_delete_value is None, executor resolves a sensible default."""
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.SOFT_DELETE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=3)],
        soft_delete_column="removed",
        soft_delete_value=None,
    )
    ex.execute(plan, "c1", engine, _audit(tmp_path), "soft delete id=3")
    removed_val = _fetch(engine, 3)["removed"]
    assert removed_val not in (None, 0)  # default was applied


def test_soft_delete_rollback(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.SOFT_DELETE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        soft_delete_column="removed",
        soft_delete_value=1,
    )
    resp = ex.execute(plan, "c1", engine, _audit(tmp_path), "soft delete id=1")
    assert _fetch(engine, 1)["removed"] == 1

    ex.rollback("c1", resp.rollback_token, engine, _audit(tmp_path))
    assert _fetch(engine, 1)["removed"] == 0  # restored to original


# ------------------------------------------------------------------ #
# DELETE
# ------------------------------------------------------------------ #

def test_delete_row(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.DELETE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=2)],
    )
    resp = ex.execute(plan, "c1", engine, _audit(tmp_path), "delete id=2")
    assert resp.affected_rows == 1
    assert _row_count(engine) == 2


def test_delete_rollback(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.DELETE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=2)],
    )
    resp = ex.execute(plan, "c1", engine, _audit(tmp_path), "delete id=2")
    assert _row_count(engine) == 2

    ex.rollback("c1", resp.rollback_token, engine, _audit(tmp_path))
    assert _row_count(engine) == 3
    assert _row_count(engine, label="B") == 1


# ------------------------------------------------------------------ #
# Audit log
# ------------------------------------------------------------------ #

def test_execute_writes_audit_entry(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    audit = _audit(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.UPDATE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        set_values={"qty": 5},
    )
    resp = ex.execute(plan, "myconn", engine, audit, "update qty to 5")
    entries = audit.get_entries("myconn")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.audit_id == resp.audit_id
    assert entry.action == "update"
    assert entry.table_name == "items"
    assert entry.question == "update qty to 5"


def test_rollback_writes_rollback_audit_entry(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    audit = _audit(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.UPDATE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        set_values={"qty": 5},
    )
    resp = ex.execute(plan, "myconn", engine, audit, "update qty")
    ex.rollback("myconn", resp.rollback_token, engine, audit)
    entries = audit.get_entries("myconn", limit=10)
    actions = [e.action for e in entries]
    assert "rollback" in actions


# ------------------------------------------------------------------ #
# Rollback edge cases
# ------------------------------------------------------------------ #

def test_rollback_token_not_found(tmp_path):
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    with pytest.raises(RollbackError, match="not found"):
        ex.rollback("c1", "deadbeef", engine, _audit(tmp_path))


def test_rollback_wrong_connection_id(tmp_path):
    """A token issued for conn_a must not be usable under conn_b.

    The snapshot file is keyed by connection_id, so conn_b will never find
    conn_a's snapshot — it raises RollbackError with "not found".
    """
    engine = _make_db(tmp_path)
    ex = _executor(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.UPDATE,
        table_name="items",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        set_values={"qty": 5},
    )
    resp = ex.execute(plan, "conn_a", engine, _audit(tmp_path), "q")
    with pytest.raises(RollbackError):
        ex.rollback("conn_b", resp.rollback_token, engine, _audit(tmp_path))
