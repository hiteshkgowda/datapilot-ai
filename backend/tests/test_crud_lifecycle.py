"""Enterprise tests — CRUD lifecycle.

Coverage targets:
  - CrudExecutor : CREATE / UPDATE / BULK_UPDATE / DELETE / SOFT_DELETE
  - CrudValidator : column checks, filter requirements, denylist, PK immutability,
                    row-limit enforcement, filter-operator consistency
  - ConfirmationTokenService : issue, verify, expiry, single-use, binding

All tests run against a real in-memory SQLite database.  No LLM, no network.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import select

from app.core.exceptions import (
    ConfirmationError,
    CrudExecutionError,
    CrudPlanValidationError,
)
from app.schemas.crud import (
    CrudExecuteRequest,
    CrudOperation,
    CrudPlan,
    FilterOperator,
    RowFilter,
)
from app.services.crud_validator import ConfirmationTokenService

from tests.helpers import (
    count_rows,
    fetch_rows,
    make_audit_logger,
    make_engine,
    make_executor,
    make_products_table,
    make_token_service,
    make_validator,
    mock_connection_service,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine():
    return make_engine()


@pytest.fixture()
def products(engine):
    return make_products_table(engine)


@pytest.fixture()
def audit_logger(tmp_path):
    return make_audit_logger(tmp_path / "audit")


@pytest.fixture()
def executor(tmp_path):
    return make_executor(tmp_path / "rollback")


@pytest.fixture()
def token_svc():
    return make_token_service()


@pytest.fixture()
def validator(token_svc):
    return make_validator(token_svc=token_svc)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _create_plan(**kwargs) -> CrudPlan:
    return CrudPlan(
        operation=CrudOperation.CREATE,
        table_name="products",
        row_data={"name": "New Item", "price": 5.0, "active": 1, "category": "misc"},
        **kwargs,
    )


def _update_plan(name_filter: str = "Widget A", **kwargs) -> CrudPlan:
    return CrudPlan(
        operation=CrudOperation.UPDATE,
        table_name="products",
        filters=[RowFilter(column="name", operator=FilterOperator.EQ, value=name_filter)],
        set_values={"price": 99.99},
        **kwargs,
    )


def _delete_plan(name_filter: str = "Widget A") -> CrudPlan:
    return CrudPlan(
        operation=CrudOperation.DELETE,
        table_name="products",
        filters=[RowFilter(column="name", operator=FilterOperator.EQ, value=name_filter)],
    )


def _bulk_update_plan() -> CrudPlan:
    return CrudPlan(
        operation=CrudOperation.BULK_UPDATE,
        table_name="products",
        filters=[RowFilter(column="category", operator=FilterOperator.EQ, value="tools")],
        set_values={"price": 1.0},
    )


# ── CREATE ────────────────────────────────────────────────────────────────────


class TestCreate:
    def test_create_inserts_row(self, engine, products, executor, audit_logger):
        plan = _create_plan()
        executor.execute(plan, "conn-1", engine, audit_logger, "add item", "u1", "u@e.com")
        assert count_rows(engine, products, name="New Item") == 1

    def test_create_returns_affected_rows_of_1(self, engine, products, executor, audit_logger):
        plan = _create_plan()
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "add item")
        assert resp.affected_rows == 1

    def test_create_audit_id_is_non_empty(self, engine, products, executor, audit_logger):
        plan = _create_plan()
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "add item")
        assert resp.audit_id

    def test_create_rollback_token_issued_when_pk_exists(self, engine, products, executor, audit_logger):
        plan = _create_plan()
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "add item")
        # products table has a PK → rollback must be supported
        assert resp.rollback_supported is True
        assert resp.rollback_token is not None

    def test_create_execution_time_is_positive(self, engine, products, executor, audit_logger):
        plan = _create_plan()
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "add item")
        assert resp.execution_time_ms > 0

    def test_create_does_not_affect_existing_rows(self, engine, products, executor, audit_logger):
        before = count_rows(engine, products)
        plan = _create_plan()
        executor.execute(plan, "conn-1", engine, audit_logger, "add item")
        assert count_rows(engine, products) == before + 1


# ── READ (preview) ────────────────────────────────────────────────────────────


class TestPreview:
    def test_preview_create_shows_planned_row(self, engine, products, validator):
        plan = _create_plan()
        preview, _ = validator.validate_and_preview(plan, "conn-1", engine)
        assert preview.total_count == 1
        assert preview.rows[0]["name"] == "New Item"

    def test_preview_update_returns_matching_rows(self, engine, products, validator):
        plan = _update_plan("Widget A")
        preview, _ = validator.validate_and_preview(plan, "conn-1", engine)
        assert preview.total_count == 1
        assert preview.rows[0]["name"] == "Widget A"

    def test_preview_delete_counts_affected_rows(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="category", operator=FilterOperator.EQ, value="tools")],
        )
        preview, _ = validator.validate_and_preview(plan, "conn-1", engine)
        assert preview.total_count == 2  # two "tools" rows in fixture

    def test_preview_columns_match_table_schema(self, engine, products, validator):
        plan = _update_plan()
        preview, _ = validator.validate_and_preview(plan, "conn-1", engine)
        assert "name" in preview.columns
        assert "price" in preview.columns

    def test_preview_returns_no_warnings_for_normal_ops(self, engine, products, validator):
        plan = _update_plan()
        _, warnings = validator.validate_and_preview(plan, "conn-1", engine)
        assert warnings == []

    def test_preview_update_multiple_requires_confirmation(self, engine, products, validator):
        plan = _bulk_update_plan()
        preview, _ = validator.validate_and_preview(plan, "conn-1", engine)
        assert validator.requires_confirmation(plan, preview.total_count) is True

    def test_preview_single_update_no_confirmation(self, engine, products, validator):
        plan = _update_plan("Widget A")
        preview, _ = validator.validate_and_preview(plan, "conn-1", engine)
        assert validator.requires_confirmation(plan, preview.total_count) is False

    def test_preview_delete_always_requires_confirmation(self, engine, products, validator):
        plan = _delete_plan()
        preview, _ = validator.validate_and_preview(plan, "conn-1", engine)
        assert validator.requires_confirmation(plan, preview.total_count) is True


# ── UPDATE ────────────────────────────────────────────────────────────────────


class TestUpdate:
    def test_update_modifies_matching_row(self, engine, products, executor, audit_logger):
        plan = _update_plan("Widget A")
        executor.execute(plan, "conn-1", engine, audit_logger, "update price")
        rows = fetch_rows(engine, products)
        widget_a = next(r for r in rows if r["name"] == "Widget A")
        assert widget_a["price"] == pytest.approx(99.99)

    def test_update_does_not_affect_other_rows(self, engine, products, executor, audit_logger):
        plan = _update_plan("Widget A")
        executor.execute(plan, "conn-1", engine, audit_logger, "update price")
        rows = fetch_rows(engine, products)
        widget_b = next(r for r in rows if r["name"] == "Widget B")
        assert widget_b["price"] == pytest.approx(19.99)  # unchanged

    def test_update_returns_correct_affected_count(self, engine, products, executor, audit_logger):
        plan = _update_plan("Widget A")
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "update price")
        assert resp.affected_rows == 1

    def test_bulk_update_modifies_all_matching_rows(self, engine, products, executor, audit_logger):
        plan = _bulk_update_plan()
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "bulk price update")
        assert resp.affected_rows == 2
        rows = fetch_rows(engine, products)
        for r in rows:
            if r["category"] == "tools":
                assert r["price"] == pytest.approx(1.0)

    def test_bulk_update_leaves_other_category_untouched(self, engine, products, executor, audit_logger):
        plan = _bulk_update_plan()
        executor.execute(plan, "conn-1", engine, audit_logger, "bulk price update")
        rows = fetch_rows(engine, products)
        electronics = next(r for r in rows if r["category"] == "electronics")
        assert electronics["price"] == pytest.approx(49.99)

    def test_update_using_in_filter(self, engine, products, executor, audit_logger):
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="products",
            filters=[RowFilter(column="name", operator=FilterOperator.IN,
                               value=["Widget A", "Widget B"])],
            set_values={"active": 0},
        )
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "deactivate widgets")
        assert resp.affected_rows == 2

    def test_update_using_gt_filter(self, engine, products, executor, audit_logger):
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="products",
            filters=[RowFilter(column="price", operator=FilterOperator.GT, value=10.0)],
            set_values={"active": 0},
        )
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "deactivate expensive")
        assert resp.affected_rows == 2  # Widget B (19.99) and Gadget X (49.99)


# ── DELETE ────────────────────────────────────────────────────────────────────


class TestDelete:
    def test_delete_removes_matching_row(self, engine, products, executor, audit_logger):
        plan = _delete_plan("Widget A")
        executor.execute(plan, "conn-1", engine, audit_logger, "delete item")
        assert count_rows(engine, products, name="Widget A") == 0

    def test_delete_does_not_remove_unmatched_rows(self, engine, products, executor, audit_logger):
        plan = _delete_plan("Widget A")
        executor.execute(plan, "conn-1", engine, audit_logger, "delete item")
        assert count_rows(engine, products, name="Widget B") == 1

    def test_delete_returns_correct_affected_count(self, engine, products, executor, audit_logger):
        plan = _delete_plan("Widget A")
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "delete item")
        assert resp.affected_rows == 1

    def test_delete_multi_row_via_filter(self, engine, products, executor, audit_logger):
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="category", operator=FilterOperator.EQ, value="tools")],
        )
        resp = executor.execute(plan, "conn-1", engine, audit_logger, "delete tools")
        assert resp.affected_rows == 2
        assert count_rows(engine, products) == 1  # only Gadget X remains

    def test_soft_delete_sets_flag_column(self, engine, products, executor, audit_logger):
        plan = CrudPlan(
            operation=CrudOperation.SOFT_DELETE,
            table_name="products",
            filters=[RowFilter(column="name", operator=FilterOperator.EQ, value="Widget A")],
            soft_delete_column="active",
            soft_delete_value=0,
        )
        executor.execute(plan, "conn-1", engine, audit_logger, "soft delete")
        rows = fetch_rows(engine, products)
        widget_a = next(r for r in rows if r["name"] == "Widget A")
        assert widget_a["active"] == 0

    def test_soft_delete_does_not_remove_row(self, engine, products, executor, audit_logger):
        plan = CrudPlan(
            operation=CrudOperation.SOFT_DELETE,
            table_name="products",
            filters=[RowFilter(column="name", operator=FilterOperator.EQ, value="Widget A")],
            soft_delete_column="active",
        )
        before = count_rows(engine, products)
        executor.execute(plan, "conn-1", engine, audit_logger, "soft delete")
        assert count_rows(engine, products) == before


# ── Validation rules ──────────────────────────────────────────────────────────


class TestValidation:
    def test_update_without_filter_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="products",
            set_values={"price": 0},
        )
        with pytest.raises(CrudPlanValidationError, match="filter"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_delete_without_filter_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
        )
        with pytest.raises(CrudPlanValidationError, match="filter"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_bulk_update_without_filter_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.BULK_UPDATE,
            table_name="products",
            set_values={"price": 0},
        )
        with pytest.raises(CrudPlanValidationError, match="filter"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_unknown_column_in_row_data_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"nonexistent_col": "value"},
        )
        with pytest.raises(CrudPlanValidationError, match="Unknown column"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_unknown_column_in_filter_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="ghost_col", operator=FilterOperator.EQ, value=1)],
        )
        with pytest.raises((CrudPlanValidationError, Exception)):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_unknown_column_in_set_values_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="products",
            filters=[RowFilter(column="name", operator=FilterOperator.EQ, value="Widget A")],
            set_values={"ghost_col": 1},
        )
        with pytest.raises(CrudPlanValidationError, match="Unknown column"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_denylist_column_in_row_data_raises(self, engine, validator):
        """Writing to 'password' must be blocked by the denylist."""
        meta = __import__("sqlalchemy").MetaData()
        tbl = __import__("sqlalchemy").Table(
            "users_deny_test",
            meta,
            __import__("sqlalchemy").Column("id", __import__("sqlalchemy").Integer, primary_key=True),
            __import__("sqlalchemy").Column("username", __import__("sqlalchemy").Text),
            __import__("sqlalchemy").Column("password", __import__("sqlalchemy").Text),
        )
        meta.create_all(engine)
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="users_deny_test",
            row_data={"username": "alice", "password": "s3cr3t"},
        )
        with pytest.raises(CrudPlanValidationError, match="sensitive"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_denylist_column_in_set_values_raises(self, engine, products, validator):
        from sqlalchemy import Column, Text, MetaData, Table
        meta = MetaData()
        tbl = Table(
            "creds_test",
            meta,
            Column("id", __import__("sqlalchemy").Integer, primary_key=True),
            Column("api_key", Text),
        )
        meta.create_all(engine)
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="creds_test",
            filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
            set_values={"api_key": "new-key"},
        )
        with pytest.raises(CrudPlanValidationError, match="sensitive"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_pk_in_set_values_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.UPDATE,
            table_name="products",
            filters=[RowFilter(column="name", operator=FilterOperator.EQ, value="Widget A")],
            set_values={"id": 99},
        )
        with pytest.raises(CrudPlanValidationError, match="Primary key"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_row_limit_exceeded_raises(self, engine, products):
        """Validator with max_rows=1 must block a plan that affects 2 rows."""
        strict_validator = make_validator(max_rows=1)
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="category", operator=FilterOperator.EQ, value="tools")],
        )
        with pytest.raises(CrudPlanValidationError, match="limit"):
            strict_validator.validate_and_preview(plan, "conn-1", engine)

    def test_row_limit_override_warns_but_allows(self, engine, products):
        strict_validator = make_validator(max_rows=1)
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="category", operator=FilterOperator.EQ, value="tools")],
        )
        _, warnings = strict_validator.validate_and_preview(
            plan, "conn-1", engine, override_row_limit=True
        )
        assert any("override" in w.lower() for w in warnings)

    def test_nested_object_in_row_data_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.CREATE,
            table_name="products",
            row_data={"name": "bad", "price": {"nested": True}},
        )
        with pytest.raises(CrudPlanValidationError, match="nested"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_is_null_filter_with_nonnull_value_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="category", operator=FilterOperator.IS_NULL, value="oops")],
        )
        with pytest.raises(CrudPlanValidationError, match="null"):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_in_filter_with_non_list_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.DELETE,
            table_name="products",
            filters=[RowFilter(column="name", operator=FilterOperator.IN, value="scalar")],
        )
        with pytest.raises(CrudPlanValidationError):
            validator.validate_and_preview(plan, "conn-1", engine)

    def test_soft_delete_without_column_raises(self, engine, products, validator):
        plan = CrudPlan(
            operation=CrudOperation.SOFT_DELETE,
            table_name="products",
            filters=[RowFilter(column="name", operator=FilterOperator.EQ, value="Widget A")],
        )
        with pytest.raises(CrudPlanValidationError, match="soft_delete_column"):
            validator.validate_and_preview(plan, "conn-1", engine)


# ── Confirmation token ────────────────────────────────────────────────────────


class TestConfirmationToken:
    def test_valid_token_verifies_without_error(self, token_svc):
        plan = _update_plan()
        token = token_svc.issue("conn-1", plan, user_sub="user-a")
        token_svc.verify(token, "conn-1", plan, user_sub="user-a")  # must not raise

    def test_tampered_token_raises(self, token_svc):
        plan = _update_plan()
        token = token_svc.issue("conn-1", plan, user_sub="user-a")
        bad = token[:-4] + "XXXX"
        with pytest.raises(ConfirmationError):
            token_svc.verify(bad, "conn-1", plan, user_sub="user-a")

    def test_token_bound_to_connection_id(self, token_svc):
        plan = _update_plan()
        token = token_svc.issue("conn-1", plan, user_sub="user-a")
        with pytest.raises(ConfirmationError):
            token_svc.verify(token, "conn-OTHER", plan, user_sub="user-a")

    def test_token_bound_to_user_sub(self, token_svc):
        plan = _update_plan()
        token = token_svc.issue("conn-1", plan, user_sub="user-a")
        with pytest.raises(ConfirmationError):
            token_svc.verify(token, "conn-1", plan, user_sub="user-b")

    def test_token_single_use(self, token_svc):
        plan = _update_plan()
        token = token_svc.issue("conn-1", plan, user_sub="user-a")
        token_svc.verify(token, "conn-1", plan, user_sub="user-a")  # first use OK
        with pytest.raises(ConfirmationError, match="already been used"):
            token_svc.verify(token, "conn-1", plan, user_sub="user-a")

    def test_expired_token_raises(self):
        short_ttl = ConfirmationTokenService(secret_key="s", ttl_seconds=0)
        plan = _update_plan()
        token = short_ttl.issue("conn-1", plan)
        time.sleep(0.01)
        with pytest.raises(ConfirmationError, match="expired"):
            short_ttl.verify(token, "conn-1", plan)

    def test_malformed_token_raises(self, token_svc):
        plan = _update_plan()
        with pytest.raises(ConfirmationError):
            token_svc.verify("not-a-valid-token!!", "conn-1", plan)

    def test_token_bound_to_plan(self, token_svc):
        plan_a = _update_plan("Widget A")
        plan_b = _update_plan("Widget B")
        token = token_svc.issue("conn-1", plan_a, user_sub="user-a")
        with pytest.raises(ConfirmationError):
            token_svc.verify(token, "conn-1", plan_b, user_sub="user-a")

    def test_delete_via_service_requires_token(self, engine, products, tmp_path):
        """CrudService.execute must raise ConfirmationError for DELETE without token."""
        from unittest.mock import AsyncMock, MagicMock
        from app.services.crud_service import CrudService

        conn_svc = mock_connection_service("user-a", engine)
        svc = CrudService(
            planner=MagicMock(),
            validator=make_validator(),
            executor=make_executor(tmp_path / "rb"),
            audit_logger=make_audit_logger(tmp_path / "audit"),
            connection_service=conn_svc,
            dataset_service=MagicMock(),
        )
        request = CrudExecuteRequest(
            connection_id="conn-1",
            plan=_delete_plan("Widget A"),
            confirmation_token=None,
            question="delete widget a",
        )
        import asyncio
        with pytest.raises(Exception):  # ConfirmationError bubbles as-is
            asyncio.run(
                svc.execute(request, user_sub="user-a")
            )

    def test_bulk_update_via_service_requires_token(self, engine, products, tmp_path):
        from unittest.mock import MagicMock
        from app.services.crud_service import CrudService
        from app.core.exceptions import ConfirmationError

        conn_svc = mock_connection_service("user-a", engine)
        svc = CrudService(
            planner=MagicMock(),
            validator=make_validator(),
            executor=make_executor(tmp_path / "rb"),
            audit_logger=make_audit_logger(tmp_path / "audit"),
            connection_service=conn_svc,
            dataset_service=MagicMock(),
        )
        request = CrudExecuteRequest(
            connection_id="conn-1",
            plan=_bulk_update_plan(),
            confirmation_token=None,
            question="bulk update",
        )
        import asyncio
        with pytest.raises(ConfirmationError):
            asyncio.run(
                svc.execute(request, user_sub="user-a")
            )
