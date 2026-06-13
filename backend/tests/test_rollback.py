"""Enterprise tests — rollback functionality.

Tests CrudExecutor.rollback() for all reversible operations:
  - CREATE → DELETE by inserted PK
  - UPDATE / BULK_UPDATE → restore pre-image values
  - SOFT_DELETE → restore pre-image values
  - DELETE → re-insert pre-image rows

Also tests error paths: token not found, expired token, wrong connection.
"""

from __future__ import annotations

import json
import time
import pytest

from app.core.exceptions import RollbackError
from app.schemas.crud import CrudOperation, CrudPlan, RowFilter

from tests.helpers import (
    count_rows,
    fetch_rows,
    make_audit_logger,
    make_engine,
    make_executor,
    make_products_table,
)

_CONN = "test-conn"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine():
    e = make_engine()
    make_products_table(e)
    return e


@pytest.fixture()
def audit(tmp_path):
    return make_audit_logger(tmp_path / "audit")


@pytest.fixture()
def executor(tmp_path):
    return make_executor(tmp_path / "rollback")


def _run(executor, plan, engine, audit, question="q"):
    """Execute a plan and return the CrudExecuteResponse."""
    return executor.execute(
        plan=plan,
        connection_id=_CONN,
        engine=engine,
        audit_logger=audit,
        question=question,
        user_sub="sub-tester",
        user_email="test@example.com",
    )


# ── CREATE rollback ───────────────────────────────────────────────────────────


class TestCreateRollback:
    def test_rollback_create_removes_inserted_row(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "New Widget", "price": 5.0, "active": 1, "category": "new"},
        )
        resp = _run(executor, plan, engine, audit)
        assert resp.rollback_token
        before = count_rows(engine, make_products_table.__wrapped__(engine) if False else _get_table(engine))
        rr = executor.rollback(_CONN, resp.rollback_token, engine, audit)
        assert rr.restored_rows == 1
        # Row should be gone
        rows = fetch_rows(engine, _get_table(engine))
        assert not any(r["name"] == "New Widget" for r in rows)

    def test_rollback_create_leaves_other_rows_intact(self, engine, audit, executor):
        original_count = count_rows(engine, _get_table(engine))
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "Temp Item", "price": 1.0, "active": 1, "category": "temp"},
        )
        resp = _run(executor, plan, engine, audit)
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        assert count_rows(engine, _get_table(engine)) == original_count

    def test_rollback_create_token_deleted_after_use(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "OnceOnly", "price": 1.0},
        )
        resp = _run(executor, plan, engine, audit)
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        with pytest.raises(RollbackError, match="not found"):
            executor.rollback(_CONN, resp.rollback_token, engine, audit)

    def test_rollback_create_logged_in_audit(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "Audited", "price": 2.0},
        )
        resp = _run(executor, plan, engine, audit)
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        entries = audit.get_entries(_CONN)
        actions = [e.action for e in entries]
        assert "rollback" in actions


# ── UPDATE rollback ───────────────────────────────────────────────────────────


def _get_table(engine):
    from sqlalchemy import MetaData, Table
    return Table("products", MetaData(), autoload_with=engine)


class TestUpdateRollback:
    def test_rollback_update_restores_old_value(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="products",
            filters=[RowFilter(column="name", operator="eq", value="Widget A")],
            set_values={"price": 999.0},
        )
        resp = _run(executor, plan, engine, audit)
        assert resp.rollback_token
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        rows = fetch_rows(engine, _get_table(engine))
        widget_a = next(r for r in rows if r["name"] == "Widget A")
        assert widget_a["price"] == pytest.approx(9.99)

    def test_rollback_update_only_touches_affected_row(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="products",
            filters=[RowFilter(column="name", operator="eq", value="Widget B")],
            set_values={"price": 0.01},
        )
        resp = _run(executor, plan, engine, audit)
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        rows = fetch_rows(engine, _get_table(engine))
        # Widget A should be unchanged
        widget_a = next(r for r in rows if r["name"] == "Widget A")
        assert widget_a["price"] == pytest.approx(9.99)

    def test_rollback_bulk_update_restores_multiple_rows(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.BULK_UPDATE,
            table_name="products",
            filters=[RowFilter(column="category", operator="eq", value="tools")],
            set_values={"price": 0.0},
        )
        resp = _run(executor, plan, engine, audit)
        assert resp.rollback_token
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        rows = fetch_rows(engine, _get_table(engine))
        tools = [r for r in rows if r["category"] == "tools"]
        prices = [r["price"] for r in tools]
        # Prices should be restored to original values
        assert any(abs(p - 9.99) < 0.01 or abs(p - 19.99) < 0.01 for p in prices)

    def test_rollback_update_returns_correct_restored_count(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="products",
            filters=[RowFilter(column="name", operator="eq", value="Widget A")],
            set_values={"price": 0.5},
        )
        resp = _run(executor, plan, engine, audit)
        rr = executor.rollback(_CONN, resp.rollback_token, engine, audit)
        assert rr.restored_rows == 1


# ── SOFT_DELETE rollback ──────────────────────────────────────────────────────


class TestSoftDeleteRollback:
    def test_rollback_soft_delete_restores_active_flag(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.SOFT_DELETE,
            table_name="products",
            filters=[RowFilter(column="name", operator="eq", value="Widget A")],
            soft_delete_column="active",
            soft_delete_value=0,
        )
        resp = _run(executor, plan, engine, audit)
        assert resp.rollback_token
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        rows = fetch_rows(engine, _get_table(engine))
        widget_a = next(r for r in rows if r["name"] == "Widget A")
        assert widget_a["active"] == 1


# ── DELETE rollback ───────────────────────────────────────────────────────────


class TestDeleteRollback:
    def test_rollback_delete_restores_removed_row(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="name", operator="eq", value="Widget A")],
        )
        resp = _run(executor, plan, engine, audit)
        assert resp.rollback_token
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        rows = fetch_rows(engine, _get_table(engine))
        assert any(r["name"] == "Widget A" for r in rows)

    def test_rollback_delete_restored_count_matches(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="category", operator="eq", value="tools")],
        )
        resp = _run(executor, plan, engine, audit)
        rr = executor.rollback(_CONN, resp.rollback_token, engine, audit)
        assert rr.restored_rows == 2

    def test_rollback_delete_all_tools_restores_them(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="category", operator="eq", value="tools")],
        )
        resp = _run(executor, plan, engine, audit)
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        assert count_rows(engine, _get_table(engine), category="tools") == 2


# ── Error paths ───────────────────────────────────────────────────────────────


class TestRollbackErrors:
    def test_unknown_token_raises(self, engine, audit, executor):
        with pytest.raises(RollbackError, match="not found"):
            executor.rollback(_CONN, "nonexistent-token", engine, audit)

    def test_expired_token_raises(self, engine, audit, tmp_path):
        ex = make_executor(tmp_path / "exp_rb")
        ex._rollback_ttl = 0  # expire immediately
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "ExpiredTest", "price": 1.0},
        )
        resp = _run(ex, plan, engine, audit)
        # Force expiry by writing a snapshot with past expires_at
        snap_files = list(ex._rollback_dir.iterdir())
        assert snap_files
        for sf in snap_files:
            snap = json.loads(sf.read_text())
            snap["expires_at"] = time.time() - 1
            sf.write_text(json.dumps(snap))

        with pytest.raises(RollbackError, match="expired"):
            ex.rollback(_CONN, resp.rollback_token, engine, audit)

    def test_wrong_connection_raises(self, engine, audit, executor):
        """Snapshot path embeds connection_id, so a wrong connection gives 'not found'."""
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "WrongConn", "price": 1.0},
        )
        resp = _run(executor, plan, engine, audit)
        with pytest.raises(RollbackError):
            executor.rollback("different-conn", resp.rollback_token, engine, audit)

    def test_token_single_use(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "SingleUse", "price": 1.0},
        )
        resp = _run(executor, plan, engine, audit)
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        with pytest.raises(RollbackError):
            executor.rollback(_CONN, resp.rollback_token, engine, audit)

    def test_snapshot_file_deleted_after_rollback(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "CleanupTest", "price": 1.0},
        )
        resp = _run(executor, plan, engine, audit)
        snap_path = executor._snapshot_path(_CONN, resp.rollback_token)
        assert snap_path.is_file()
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        assert not snap_path.is_file()

    def test_rollback_response_has_positive_exec_time(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "TimingTest", "price": 1.0},
        )
        resp = _run(executor, plan, engine, audit)
        rr = executor.rollback(_CONN, resp.rollback_token, engine, audit)
        assert rr.execution_time_ms >= 0
        assert rr.audit_id

    def test_rollback_supports_flag_set_on_create(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "FlagTest", "price": 1.0},
        )
        resp = _run(executor, plan, engine, audit)
        assert resp.rollback_supported is True
        assert resp.rollback_token is not None

    def test_rollback_is_logged_as_rollback_action(self, engine, audit, executor):
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="products",
            filters=[RowFilter(column="name", operator="eq", value="Widget A")],
            set_values={"price": 42.0},
        )
        resp = _run(executor, plan, engine, audit)
        executor.rollback(_CONN, resp.rollback_token, engine, audit)
        entries = audit.get_entries(_CONN)
        # Newest entry (index 0) should be the rollback
        assert entries[0].action == "rollback"
        assert entries[0].rollback_token == resp.rollback_token
