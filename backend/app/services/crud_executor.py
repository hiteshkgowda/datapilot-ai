"""SQLAlchemy Core DML executor for CRUD operations (Phase 7).

All mutations run inside ``engine.begin()`` transactions.  Pre-images are
captured inside the same transaction for snapshot-based rollback.  No raw
SQL strings are ever formatted; all DML uses reflected Table objects and
bound parameters.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import MetaData, Table, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import CrudExecutionError, RollbackError
from app.schemas.crud import (
    CrudExecuteResponse,
    CrudOperation,
    CrudPlan,
    RollbackResponse,
)
from app.services.crud_audit import AuditEntry, AuditLogger, new_audit_id
from app.services.crud_validator import _apply_filter


def _serialize_value(val: Any) -> Any:
    """Coerce non-JSON-serialisable types (datetime, Decimal…) to strings."""
    if isinstance(val, datetime):
        return val.isoformat()
    try:
        json.dumps(val)
        return val
    except (TypeError, ValueError):
        return str(val)


class CrudExecutor:
    """Execute validated CrudPlan objects via SQLAlchemy Core DML.

    Thread-safe: table reflection is cached behind a lock; rollback snapshots
    are written to individual JSON files (one per operation).
    """

    def __init__(
        self,
        rollback_dir: Path,
        rollback_ttl_seconds: int = 3600,
        max_rollback_rows: int = 1000,
    ) -> None:
        self._rollback_dir = rollback_dir
        self._rollback_dir.mkdir(parents=True, exist_ok=True)
        self._rollback_ttl = rollback_ttl_seconds
        self._max_rollback = max_rollback_rows
        self._table_cache: dict[tuple[int, Optional[str], str], Table] = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Execute
    # ------------------------------------------------------------------ #

    def execute(
        self,
        plan: CrudPlan,
        connection_id: str,
        engine: Engine,
        audit_logger: AuditLogger,
        question: str,
        user_sub: str = "",
        user_email: str = "",
    ) -> CrudExecuteResponse:
        table = self._reflect(engine, plan)
        pk_cols = self._get_pk_cols(table)
        start = time.perf_counter()

        try:
            with engine.begin() as conn:
                pre_image = self._capture_pre_image(conn, table, plan)
                rollback_supported = self._is_rollback_supported(
                    plan.operation, pre_image, pk_cols
                )
                affected_rows, inserted_pk = self._run_dml(conn, table, plan, pk_cols)
        except SQLAlchemyError as exc:
            raise CrudExecutionError(f"Database error during {plan.operation.value}: {exc}") from exc

        elapsed_ms = (time.perf_counter() - start) * 1000
        rollback_token: Optional[str] = None
        if rollback_supported:
            rollback_token = self._save_snapshot(
                connection_id, plan, pre_image, pk_cols, inserted_pk
            )

        audit_id = new_audit_id()
        audit_logger.log(
            connection_id,
            AuditEntry(
                audit_id=audit_id,
                timestamp=datetime.now(timezone.utc),
                action=plan.operation.value,
                connection_id=connection_id,
                schema_name=plan.schema_name,
                table_name=plan.table_name,
                filters=[f.model_dump() for f in (plan.filters or [])],
                set_values=plan.set_values,
                row_data=plan.row_data,
                affected_rows=affected_rows,
                rollback_token=rollback_token,
                rollback_supported=rollback_supported,
                execution_time_ms=elapsed_ms,
                question=question,
                user_sub=user_sub,
                user_email=user_email,
            ),
        )

        return CrudExecuteResponse(
            operation=plan.operation,
            table_name=plan.table_name,
            affected_rows=affected_rows,
            rollback_token=rollback_token,
            rollback_supported=rollback_supported,
            execution_time_ms=elapsed_ms,
            audit_id=audit_id,
        )

    # ------------------------------------------------------------------ #
    # Rollback
    # ------------------------------------------------------------------ #

    def rollback(
        self,
        connection_id: str,
        rollback_token: str,
        engine: Engine,
        audit_logger: AuditLogger,
    ) -> RollbackResponse:
        snapshot = self._load_snapshot(connection_id, rollback_token)
        plan = CrudPlan(**snapshot["plan"])
        table = self._reflect(engine, plan)
        pre_image: list[dict[str, Any]] = snapshot["pre_image"]
        pk_cols: list[str] = snapshot["pk_cols"]
        operation: str = snapshot["operation"]
        inserted_pk: dict[str, Any] = snapshot.get("inserted_pk", {})
        start = time.perf_counter()

        try:
            with engine.begin() as conn:
                restored = self._run_reverse_dml(
                    conn, table, operation, pre_image, pk_cols, inserted_pk
                )
        except SQLAlchemyError as exc:
            raise RollbackError(f"Rollback failed: {exc}") from exc

        self._delete_snapshot(connection_id, rollback_token)
        elapsed_ms = (time.perf_counter() - start) * 1000
        audit_id = new_audit_id()

        audit_logger.log(
            connection_id,
            AuditEntry(
                audit_id=audit_id,
                timestamp=datetime.now(timezone.utc),
                action="rollback",
                connection_id=connection_id,
                schema_name=snapshot.get("schema_name"),
                table_name=snapshot["table_name"],
                filters=None,
                set_values=None,
                row_data=None,
                affected_rows=restored,
                rollback_token=rollback_token,
                rollback_supported=False,
                execution_time_ms=elapsed_ms,
                question=f"rollback of {operation}",
            ),
        )

        return RollbackResponse(
            restored_rows=restored,
            execution_time_ms=elapsed_ms,
            audit_id=audit_id,
        )

    # ------------------------------------------------------------------ #
    # DML (SQLAlchemy Core — no raw SQL strings)
    # ------------------------------------------------------------------ #

    def _run_dml(
        self,
        conn: Any,
        table: Table,
        plan: CrudPlan,
        pk_cols: list[str],
    ) -> tuple[int, dict[str, Any]]:
        """Return (affected_rows, inserted_pk)."""
        op = plan.operation

        if op is CrudOperation.CREATE:
            result = conn.execute(table.insert().values(**(plan.row_data or {})))
            inserted_pk: dict[str, Any] = {}
            if result.inserted_primary_key is not None:
                inserted_pk = dict(zip(pk_cols, result.inserted_primary_key))
            return 1, inserted_pk

        if op in (CrudOperation.UPDATE, CrudOperation.BULK_UPDATE):
            stmt = table.update()
            for f in (plan.filters or []):
                stmt = stmt.where(_apply_filter(table, f))
            stmt = stmt.values(**(plan.set_values or {}))
            result = conn.execute(stmt)
            return result.rowcount, {}

        if op is CrudOperation.SOFT_DELETE:
            col_name = plan.soft_delete_column
            val = plan.soft_delete_value
            if val is None:
                val = self._resolve_soft_delete_default(table, col_name)
            stmt = table.update()
            for f in (plan.filters or []):
                stmt = stmt.where(_apply_filter(table, f))
            stmt = stmt.values(**{col_name: val})
            result = conn.execute(stmt)
            return result.rowcount, {}

        if op is CrudOperation.DELETE:
            stmt = table.delete()
            for f in (plan.filters or []):
                stmt = stmt.where(_apply_filter(table, f))
            result = conn.execute(stmt)
            return result.rowcount, {}

        raise CrudExecutionError(f"Unsupported operation: {op.value}")

    def _run_reverse_dml(
        self,
        conn: Any,
        table: Table,
        operation: str,
        pre_image: list[dict[str, Any]],
        pk_cols: list[str],
        inserted_pk: dict[str, Any],
    ) -> int:
        if operation == "create":
            if not inserted_pk:
                raise RollbackError("No inserted PK in snapshot; cannot undo CREATE.")
            stmt = table.delete()
            for col, val in inserted_pk.items():
                stmt = stmt.where(table.c[col] == val)
            return conn.execute(stmt).rowcount

        if operation in ("update", "bulk_update", "soft_delete"):
            restored = 0
            for old_row in pre_image:
                stmt = table.update()
                for pk_col in pk_cols:
                    stmt = stmt.where(table.c[pk_col] == old_row[pk_col])
                set_vals = {k: v for k, v in old_row.items() if k not in pk_cols}
                if not set_vals:
                    continue
                stmt = stmt.values(**set_vals)
                restored += conn.execute(stmt).rowcount
            return restored

        if operation == "delete":
            for old_row in pre_image:
                conn.execute(table.insert().values(**old_row))
            return len(pre_image)

        raise RollbackError(f"Cannot reverse unknown operation: {operation!r}")

    # ------------------------------------------------------------------ #
    # Pre-image capture
    # ------------------------------------------------------------------ #

    @staticmethod
    def _capture_pre_image(
        conn: Any, table: Table, plan: CrudPlan
    ) -> list[dict[str, Any]]:
        if plan.operation is CrudOperation.CREATE:
            return []
        stmt = select(table)
        for f in (plan.filters or []):
            stmt = stmt.where(_apply_filter(table, f))
        result = conn.execute(stmt)
        col_names = list(result.keys())
        return [
            {col: _serialize_value(val) for col, val in zip(col_names, row)}
            for row in result.all()
        ]

    # ------------------------------------------------------------------ #
    # Snapshot persistence
    # ------------------------------------------------------------------ #

    def _save_snapshot(
        self,
        connection_id: str,
        plan: CrudPlan,
        pre_image: list[dict[str, Any]],
        pk_cols: list[str],
        inserted_pk: dict[str, Any],
    ) -> str:
        token = uuid.uuid4().hex
        snap: dict[str, Any] = {
            "rollback_token": token,
            "connection_id": connection_id,
            "schema_name": plan.schema_name,
            "table_name": plan.table_name,
            "operation": plan.operation.value,
            "pk_cols": pk_cols,
            "pre_image": pre_image,
            "inserted_pk": inserted_pk,
            "plan": plan.model_dump(mode="json"),
            "expires_at": time.time() + self._rollback_ttl,
        }
        path = self._snapshot_path(connection_id, token)
        path.write_text(json.dumps(snap, default=str), encoding="utf-8")
        return token

    def _load_snapshot(self, connection_id: str, rollback_token: str) -> dict[str, Any]:
        path = self._snapshot_path(connection_id, rollback_token)
        if not path.is_file():
            raise RollbackError(
                "Rollback snapshot not found. It may have expired or already been used."
            )
        snap = json.loads(path.read_text(encoding="utf-8"))
        if time.time() > snap.get("expires_at", 0):
            path.unlink(missing_ok=True)
            raise RollbackError("Rollback snapshot has expired.")
        if snap.get("connection_id") != connection_id:
            raise RollbackError("Rollback token does not match the connection.")
        return snap

    def _delete_snapshot(self, connection_id: str, rollback_token: str) -> None:
        self._snapshot_path(connection_id, rollback_token).unlink(missing_ok=True)

    def _snapshot_path(self, connection_id: str, token: str) -> Path:
        safe_conn = "".join(c for c in connection_id if c.isalnum() or c in "-_")
        return self._rollback_dir / f"{safe_conn}_{token}.json"

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _reflect(self, engine: Engine, plan: CrudPlan) -> Table:
        key = (id(engine), plan.schema_name, plan.table_name)
        with self._cache_lock:
            cached = self._table_cache.get(key)
        if cached is not None:
            return cached
        try:
            table = Table(
                plan.table_name,
                MetaData(),
                autoload_with=engine,
                schema=plan.schema_name,
            )
        except SQLAlchemyError as exc:
            raise CrudExecutionError(
                f"Could not reflect table '{plan.table_name}': {exc}"
            ) from exc
        with self._cache_lock:
            self._table_cache[key] = table
        return table

    @staticmethod
    def _get_pk_cols(table: Table) -> list[str]:
        return [col.name for col in table.primary_key.columns]

    def _is_rollback_supported(
        self,
        operation: CrudOperation,
        pre_image: list[dict[str, Any]],
        pk_cols: list[str],
    ) -> bool:
        if operation is CrudOperation.CREATE:
            return bool(pk_cols)
        if not pk_cols:
            return False
        return len(pre_image) <= self._max_rollback

    @staticmethod
    def _resolve_soft_delete_default(table: Table, column_name: str) -> Any:
        col = table.c[column_name]
        type_str = str(col.type).upper()
        if any(kw in type_str for kw in ("BOOL", "TINYINT")):
            return True
        if "INT" in type_str:
            return 1
        return datetime.now(timezone.utc).isoformat()
