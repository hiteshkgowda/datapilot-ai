"""Unit tests for CrudValidator (all 9 rules) and ConfirmationTokenService."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine, text

from app.core.exceptions import ConfirmationError, CrudPlanValidationError
from app.schemas.crud import CrudOperation, CrudPlan, FilterOperator, RowFilter
from app.services.crud_validator import (
    ConfirmationTokenService,
    CrudValidator,
    _apply_filter,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _make_db(tmp_path):
    """Tiny SQLite DB with a 'products' table for validation tests."""
    db = tmp_path / "v.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE products ("
            "  id INTEGER PRIMARY KEY,"
            "  name TEXT NOT NULL,"
            "  price REAL,"
            "  deleted INTEGER DEFAULT 0"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO products (name, price) VALUES "
            "('Alpha', 10.0), ('Beta', 20.0), ('Gamma', 30.0)"
        ))
    return engine


def _plan(**kwargs) -> CrudPlan:
    defaults = {
        "operation": CrudOperation.UPDATE,
        "table_name": "products",
        "filters": [RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        "set_values": {"price": 99.0},
    }
    defaults.update(kwargs)
    return CrudPlan(**defaults)


def _validator() -> CrudValidator:
    return CrudValidator(max_affected_rows=500)


# ------------------------------------------------------------------ #
# Rule 1 — unknown columns
# ------------------------------------------------------------------ #

def test_unknown_column_in_set_values(tmp_path):
    engine = _make_db(tmp_path)
    plan = _plan(set_values={"nonexistent": 1})
    with pytest.raises(CrudPlanValidationError, match="Unknown column"):
        _validator().validate_and_preview(plan, "c1", engine)


def test_unknown_column_in_filter(tmp_path):
    engine = _make_db(tmp_path)
    plan = _plan(
        filters=[RowFilter(column="ghost", operator=FilterOperator.EQ, value=1)]
    )
    with pytest.raises(CrudPlanValidationError, match="Unknown column"):
        _validator().validate_and_preview(plan, "c1", engine)


# ------------------------------------------------------------------ #
# Rule 2 — nested objects in scalar positions
# ------------------------------------------------------------------ #

def test_nested_dict_in_set_values_rejected(tmp_path):
    engine = _make_db(tmp_path)
    plan = _plan(set_values={"price": {"nested": True}})
    with pytest.raises(CrudPlanValidationError, match="nested objects"):
        _validator().validate_and_preview(plan, "c1", engine)


# ------------------------------------------------------------------ #
# Rule 3 — destructive ops must have filters
# ------------------------------------------------------------------ #

def test_delete_without_filter_rejected(tmp_path):
    engine = _make_db(tmp_path)
    plan = CrudPlan(operation=CrudOperation.DELETE, table_name="products", filters=None)
    with pytest.raises(CrudPlanValidationError, match="requires at least one filter"):
        _validator().validate_and_preview(plan, "c1", engine)


def test_bulk_update_without_filter_rejected(tmp_path):
    engine = _make_db(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.BULK_UPDATE,
        table_name="products",
        filters=None,
        set_values={"price": 1.0},
    )
    with pytest.raises(CrudPlanValidationError, match="requires at least one filter"):
        _validator().validate_and_preview(plan, "c1", engine)


# ------------------------------------------------------------------ #
# Rule 4 — PK immutability
# ------------------------------------------------------------------ #

def test_pk_column_in_set_values_rejected(tmp_path):
    engine = _make_db(tmp_path)
    plan = _plan(set_values={"id": 999, "price": 5.0})
    with pytest.raises(CrudPlanValidationError, match="Primary key"):
        _validator().validate_and_preview(plan, "c1", engine)


# ------------------------------------------------------------------ #
# Rule 5 — denylist
# ------------------------------------------------------------------ #

def test_password_column_write_rejected(tmp_path):
    db = tmp_path / "sec.db"
    engine = create_engine(f"sqlite:///{db}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, password TEXT)"
        ))
        conn.execute(text("INSERT INTO users VALUES (1, 'hashed')"))
    plan = CrudPlan(
        operation=CrudOperation.UPDATE,
        table_name="users",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        set_values={"password": "new"},
    )
    with pytest.raises(CrudPlanValidationError, match="sensitive column"):
        _validator().validate_and_preview(plan, "c1", engine)


# ------------------------------------------------------------------ #
# Rule 6 — SOFT_DELETE must name valid column
# ------------------------------------------------------------------ #

def test_soft_delete_missing_column_rejected(tmp_path):
    engine = _make_db(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.SOFT_DELETE,
        table_name="products",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        soft_delete_column=None,
    )
    with pytest.raises(CrudPlanValidationError, match="soft_delete_column"):
        _validator().validate_and_preview(plan, "c1", engine)


def test_soft_delete_nonexistent_column_rejected(tmp_path):
    engine = _make_db(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.SOFT_DELETE,
        table_name="products",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
        soft_delete_column="nonexistent",
    )
    with pytest.raises(CrudPlanValidationError, match="nonexistent"):
        _validator().validate_and_preview(plan, "c1", engine)


# ------------------------------------------------------------------ #
# Rule 7 — operator/value consistency
# ------------------------------------------------------------------ #

def test_is_null_with_non_null_value_rejected(tmp_path):
    engine = _make_db(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.DELETE,
        table_name="products",
        filters=[RowFilter(column="price", operator=FilterOperator.IS_NULL, value="bad")],
    )
    with pytest.raises(CrudPlanValidationError, match="must have null value"):
        _validator().validate_and_preview(plan, "c1", engine)


def test_in_operator_with_non_list_rejected(tmp_path):
    engine = _make_db(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.DELETE,
        table_name="products",
        filters=[RowFilter(column="id", operator=FilterOperator.IN, value=1)],
    )
    with pytest.raises(CrudPlanValidationError, match="non-empty list"):
        _validator().validate_and_preview(plan, "c1", engine)


def test_in_operator_with_empty_list_rejected(tmp_path):
    engine = _make_db(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.DELETE,
        table_name="products",
        filters=[RowFilter(column="id", operator=FilterOperator.IN, value=[])],
    )
    with pytest.raises(CrudPlanValidationError, match="non-empty list"):
        _validator().validate_and_preview(plan, "c1", engine)


# ------------------------------------------------------------------ #
# Rule 8 — row count limit
# ------------------------------------------------------------------ #

def test_bulk_delete_exceeds_row_limit(tmp_path):
    engine = _make_db(tmp_path)
    # max_affected_rows=1, but 3 rows match
    validator = CrudValidator(max_affected_rows=1)
    plan = CrudPlan(
        operation=CrudOperation.DELETE,
        table_name="products",
        filters=[RowFilter(column="price", operator=FilterOperator.GT, value=0)],
    )
    with pytest.raises(CrudPlanValidationError, match="exceeds the safety limit"):
        validator.validate_and_preview(plan, "c1", engine)


def test_row_limit_override_passes_with_warning(tmp_path):
    engine = _make_db(tmp_path)
    validator = CrudValidator(max_affected_rows=1)
    plan = CrudPlan(
        operation=CrudOperation.DELETE,
        table_name="products",
        filters=[RowFilter(column="price", operator=FilterOperator.GT, value=0)],
    )
    preview, warnings = validator.validate_and_preview(plan, "c1", engine, override_row_limit=True)
    assert preview.total_count == 3
    assert any("override" in w.lower() for w in warnings)


# ------------------------------------------------------------------ #
# Happy path
# ------------------------------------------------------------------ #

def test_valid_update_returns_preview(tmp_path):
    engine = _make_db(tmp_path)
    plan = _plan()
    preview, warnings = _validator().validate_and_preview(plan, "c1", engine)
    assert preview.total_count == 1
    assert preview.rows[0]["id"] == 1
    assert warnings == []


def test_valid_create_returns_row_data_preview(tmp_path):
    engine = _make_db(tmp_path)
    plan = CrudPlan(
        operation=CrudOperation.CREATE,
        table_name="products",
        row_data={"name": "Delta", "price": 40.0},
    )
    preview, _ = _validator().validate_and_preview(plan, "c1", engine)
    assert preview.total_count == 1
    assert preview.rows[0]["name"] == "Delta"


# ------------------------------------------------------------------ #
# requires_confirmation
# ------------------------------------------------------------------ #

def test_requires_confirmation_for_delete():
    v = _validator()
    plan = CrudPlan(
        operation=CrudOperation.DELETE,
        table_name="t",
        filters=[RowFilter(column="id", operator=FilterOperator.EQ, value=1)],
    )
    assert v.requires_confirmation(plan, 1) is True


def test_requires_confirmation_for_bulk_update():
    v = _validator()
    plan = CrudPlan(
        operation=CrudOperation.BULK_UPDATE,
        table_name="t",
        filters=[RowFilter(column="id", operator=FilterOperator.GT, value=0)],
        set_values={"price": 0},
    )
    assert v.requires_confirmation(plan, 100) is True


def test_update_single_row_no_confirmation():
    v = _validator()
    plan = _plan()
    assert v.requires_confirmation(plan, 1) is False


def test_update_multi_row_requires_confirmation():
    v = _validator()
    plan = _plan()
    assert v.requires_confirmation(plan, 5) is True


# ------------------------------------------------------------------ #
# ConfirmationTokenService
# ------------------------------------------------------------------ #

def test_token_round_trip():
    svc = ConfirmationTokenService()
    plan = _plan()
    token = svc.issue("conn1", plan)
    svc.verify(token, "conn1", plan)  # should not raise


def test_token_wrong_connection_id_rejected():
    svc = ConfirmationTokenService()
    plan = _plan()
    token = svc.issue("conn1", plan)
    with pytest.raises(ConfirmationError):
        svc.verify(token, "conn2", plan)


def test_token_wrong_plan_rejected():
    svc = ConfirmationTokenService()
    plan_a = _plan(set_values={"price": 10.0})
    plan_b = _plan(set_values={"price": 99.0})
    token = svc.issue("conn1", plan_a)
    with pytest.raises(ConfirmationError):
        svc.verify(token, "conn1", plan_b)


def test_token_single_use():
    svc = ConfirmationTokenService()
    plan = _plan()
    token = svc.issue("conn1", plan)
    svc.verify(token, "conn1", plan)
    with pytest.raises(ConfirmationError, match="already been used"):
        svc.verify(token, "conn1", plan)


def test_token_expired():
    svc = ConfirmationTokenService(ttl_seconds=1)
    plan = _plan()
    token = svc.issue("conn1", plan)
    time.sleep(1.1)
    with pytest.raises(ConfirmationError, match="expired"):
        svc.verify(token, "conn1", plan)


def test_malformed_token_rejected():
    svc = ConfirmationTokenService()
    with pytest.raises(ConfirmationError, match="Malformed"):
        svc.verify("notavalidtoken!!!", "conn1", _plan())
