"""End-to-end CrudService tests using a FakePlanner and real SQLite DB."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

# Pin to asyncio; trio is not installed in this environment.
@pytest.fixture(params=["asyncio"])
def anyio_backend():
    return "asyncio"

from app.core.config import Settings
from app.core.crypto import CredentialCipher
from app.core.exceptions import ConfirmationError, CrudPlanValidationError, ValidationError
from app.schemas.connection import ConnectionCreate, DbType
from app.schemas.crud import (
    CrudExecuteRequest,
    CrudOperation,
    CrudPlan,
    CrudRequest,
    RollbackRequest,
)
from app.services.connection_service import ConnectionService
from app.services.crud_audit import JsonlAuditLogger
from app.services.crud_executor import CrudExecutor
from app.services.crud_service import CrudService
from app.services.crud_validator import CrudValidator
from app.services.dataset_service import DatasetService


# ------------------------------------------------------------------ #
# FakePlanner
# ------------------------------------------------------------------ #

class FakePlanner:
    """Returns a pre-configured plan dict; never calls an LLM."""

    def __init__(self, plan_dict: dict) -> None:
        self._plan = plan_dict

    async def generate_crud_plan(self, question, schema, table_name):
        return self._plan


# ------------------------------------------------------------------ #
# Shared fixtures
# ------------------------------------------------------------------ #

def _setup(tmp_path):
    settings = Settings(
        connections_dir=tmp_path / "connections",
        crud_audit_dir=tmp_path / "audit",
        crud_rollback_dir=tmp_path / "rollback",
        crud_max_affected_rows=500,
        crud_max_rollback_rows=1000,
    )
    connections = ConnectionService(settings, CredentialCipher(None))
    datasets = DatasetService(settings, connections)

    # Register a SQLite file-based connection
    db_path = tmp_path / "test.db"
    engine_tmp = create_engine(f"sqlite:///{db_path}")
    with engine_tmp.begin() as conn:
        conn.execute(text(
            "CREATE TABLE orders ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  product TEXT NOT NULL,"
            "  amount  INTEGER DEFAULT 0"
            ")"
        ))
        conn.execute(text(
            "INSERT INTO orders (product, amount) VALUES "
            "('Widget', 5), ('Gadget', 10), ('Doohickey', 3)"
        ))
    engine_tmp.dispose()

    conn_meta = connections.create_connection(
        ConnectionCreate(
            name="test-db",
            db_type=DbType.SQLITE,
            database=str(db_path),
        )
    )
    return settings, connections, datasets, conn_meta


def _service(tmp_path, plan_dict: dict) -> tuple[CrudService, str]:
    settings, connections, datasets, conn_meta = _setup(tmp_path)
    svc = CrudService(
        planner=FakePlanner(plan_dict),
        validator=CrudValidator(max_affected_rows=500),
        executor=CrudExecutor(
            rollback_dir=settings.crud_rollback_dir,
            rollback_ttl_seconds=3600,
        ),
        audit_logger=JsonlAuditLogger(settings.crud_audit_dir),
        connection_service=connections,
        dataset_service=datasets,
    )
    return svc, conn_meta.id


# ------------------------------------------------------------------ #
# Preview tests
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_preview_update_returns_preview(tmp_path):
    plan_dict = {
        "operation": "update",
        "table_name": "orders",
        "filters": [{"column": "id", "operator": "eq", "value": 1}],
        "set_values": {"amount": 99},
    }
    svc, conn_id = _service(tmp_path, plan_dict)
    req = CrudRequest(connection_id=conn_id, table_name="orders", question="set amount=99 for id=1")
    resp = await svc.preview(req)

    assert resp.connection_id == conn_id
    assert resp.plan.operation is CrudOperation.UPDATE
    assert resp.affected_row_count == 1
    assert resp.requires_confirmation is False
    assert resp.confirmation_token is None


@pytest.mark.anyio
async def test_preview_delete_requires_confirmation(tmp_path):
    plan_dict = {
        "operation": "delete",
        "table_name": "orders",
        "filters": [{"column": "id", "operator": "eq", "value": 1}],
    }
    svc, conn_id = _service(tmp_path, plan_dict)
    req = CrudRequest(connection_id=conn_id, table_name="orders", question="delete id=1")
    resp = await svc.preview(req)

    assert resp.requires_confirmation is True
    assert resp.confirmation_token is not None


@pytest.mark.anyio
async def test_preview_unknown_column_raises(tmp_path):
    plan_dict = {
        "operation": "update",
        "table_name": "orders",
        "filters": [{"column": "id", "operator": "eq", "value": 1}],
        "set_values": {"nonexistent": 1},
    }
    svc, conn_id = _service(tmp_path, plan_dict)
    req = CrudRequest(connection_id=conn_id, table_name="orders", question="bad column")
    with pytest.raises(CrudPlanValidationError):
        await svc.preview(req)


# ------------------------------------------------------------------ #
# Execute tests
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_execute_update_no_confirmation_needed(tmp_path):
    plan_dict = {
        "operation": "update",
        "table_name": "orders",
        "filters": [{"column": "id", "operator": "eq", "value": 1}],
        "set_values": {"amount": 99},
    }
    svc, conn_id = _service(tmp_path, plan_dict)
    plan = CrudPlan(**plan_dict)
    req = CrudExecuteRequest(connection_id=conn_id, plan=plan, question="update amount")
    resp = await svc.execute(req)
    assert resp.affected_rows == 1
    assert resp.rollback_token is not None


@pytest.mark.anyio
async def test_execute_delete_without_token_raises(tmp_path):
    plan_dict = {
        "operation": "delete",
        "table_name": "orders",
        "filters": [{"column": "id", "operator": "eq", "value": 1}],
    }
    svc, conn_id = _service(tmp_path, plan_dict)
    plan = CrudPlan(**plan_dict)
    req = CrudExecuteRequest(connection_id=conn_id, plan=plan)
    with pytest.raises(ConfirmationError):
        await svc.execute(req)


@pytest.mark.anyio
async def test_execute_delete_with_valid_token(tmp_path):
    plan_dict = {
        "operation": "delete",
        "table_name": "orders",
        "filters": [{"column": "id", "operator": "eq", "value": 1}],
    }
    svc, conn_id = _service(tmp_path, plan_dict)

    # Get token from preview
    req = CrudRequest(connection_id=conn_id, table_name="orders", question="delete id=1")
    preview = await svc.preview(req)
    assert preview.confirmation_token is not None

    # Execute with token
    exec_req = CrudExecuteRequest(
        connection_id=conn_id,
        plan=preview.plan,
        confirmation_token=preview.confirmation_token,
        question="delete id=1",
    )
    resp = await svc.execute(exec_req)
    assert resp.affected_rows == 1


@pytest.mark.anyio
async def test_execute_token_single_use(tmp_path):
    plan_dict = {
        "operation": "delete",
        "table_name": "orders",
        "filters": [{"column": "id", "operator": "eq", "value": 1}],
    }
    svc, conn_id = _service(tmp_path, plan_dict)
    req = CrudRequest(connection_id=conn_id, table_name="orders", question="delete")
    preview = await svc.preview(req)

    exec_req = CrudExecuteRequest(
        connection_id=conn_id,
        plan=preview.plan,
        confirmation_token=preview.confirmation_token,
    )
    await svc.execute(exec_req)

    # Second use of same token must fail
    with pytest.raises(ConfirmationError):
        await svc.execute(exec_req)


# ------------------------------------------------------------------ #
# Rollback via service
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_rollback_restores_update(tmp_path):
    plan_dict = {
        "operation": "update",
        "table_name": "orders",
        "filters": [{"column": "id", "operator": "eq", "value": 1}],
        "set_values": {"amount": 999},
    }
    svc, conn_id = _service(tmp_path, plan_dict)
    plan = CrudPlan(**plan_dict)
    exec_resp = await svc.execute(
        CrudExecuteRequest(connection_id=conn_id, plan=plan, question="update")
    )
    assert exec_resp.rollback_token is not None

    rb_resp = svc.rollback(
        RollbackRequest(connection_id=conn_id, rollback_token=exec_resp.rollback_token)
    )
    assert rb_resp.restored_rows == 1


# ------------------------------------------------------------------ #
# Audit via service
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_get_audit_returns_entries(tmp_path):
    plan_dict = {
        "operation": "update",
        "table_name": "orders",
        "filters": [{"column": "id", "operator": "eq", "value": 1}],
        "set_values": {"amount": 7},
    }
    svc, conn_id = _service(tmp_path, plan_dict)
    plan = CrudPlan(**plan_dict)
    await svc.execute(
        CrudExecuteRequest(connection_id=conn_id, plan=plan, question="set amount 7")
    )
    audit = svc.get_audit(conn_id)
    assert audit.count == 1
    assert audit.entries[0].action == "update"


# ------------------------------------------------------------------ #
# Connection resolution
# ------------------------------------------------------------------ #

@pytest.mark.anyio
async def test_missing_connection_and_dataset_raises(tmp_path):
    svc, _ = _service(tmp_path, {})
    req = CrudRequest(question="something")
    with pytest.raises(ValidationError):
        await svc.preview(req)
