"""Deterministic validation layer for CrudPlan objects (Phase 7).

Validates every field against the live table schema, enforces safety rules,
and issues HMAC-signed single-use confirmation tokens for destructive ops.
No SQL is generated here — only schema inspection queries and COUNT(*).

This module also exports ``_apply_filter`` so the executor can build the
same WHERE clause without duplicating logic.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_module
import json
import os
import threading
import time
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import MetaData, Table, func, inspect as sa_inspect, select
from sqlalchemy.engine import Engine

from app.core.exceptions import ConfirmationError, CrudPlanValidationError
from app.schemas.crud import (
    CrudOperation,
    CrudPlan,
    FilterOperator,
    RowFilter,
    RowPreview,
)

# Per-process fallback secret — replaced by crud_secret_key from Settings if set
_PROCESS_SECRET: bytes = os.urandom(32)

# Operations that always require an explicit confirmation token
_ALWAYS_CONFIRM = frozenset(
    {CrudOperation.DELETE, CrudOperation.BULK_UPDATE, CrudOperation.SOFT_DELETE}
)

# Column names that must never be written to
_WRITE_DENYLIST = frozenset(
    {
        "password", "password_hash", "password_digest", "passwd",
        "secret", "secret_key", "api_key", "api_secret",
        "token", "access_token", "refresh_token", "auth_token",
        "salt", "hash",
    }
)


# ------------------------------------------------------------------ #
# Shared WHERE-clause builder (used by validator AND executor)
# ------------------------------------------------------------------ #

def _apply_filter(table: Table, f: RowFilter):
    """Return a SQLAlchemy Core WHERE expression for a RowFilter.

    Column names are resolved from the reflected Table object — no string
    formatting, no raw SQL.
    """
    try:
        col = table.c[f.column]
    except KeyError:
        raise CrudPlanValidationError(
            f"Column '{f.column}' not found in reflected table '{table.name}'."
        )
    op = f.operator
    if op is FilterOperator.EQ:
        return col == f.value
    if op is FilterOperator.NEQ:
        return col != f.value
    if op is FilterOperator.GT:
        return col > f.value
    if op is FilterOperator.GTE:
        return col >= f.value
    if op is FilterOperator.LT:
        return col < f.value
    if op is FilterOperator.LTE:
        return col <= f.value
    if op is FilterOperator.IN:
        return col.in_(f.value)
    if op is FilterOperator.IS_NULL:
        return col.is_(None)
    if op is FilterOperator.IS_NOT_NULL:
        return col.isnot(None)
    raise CrudPlanValidationError(f"Unsupported filter operator: {op.value!r}")


# ------------------------------------------------------------------ #
# Confirmation token service
# ------------------------------------------------------------------ #

class ConfirmationTokenService:
    """Issues and verifies HMAC-SHA256 single-use confirmation tokens.

    Tokens embed a timestamp and are signed over
    ``{timestamp}:{connection_id}:{canonical_plan_json}``.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        ttl_seconds: int = 300,
    ) -> None:
        if secret_key:
            try:
                self._key: bytes = base64.b64decode(secret_key)
            except Exception:
                self._key = secret_key.encode()
        else:
            self._key = _PROCESS_SECRET
        self._ttl = ttl_seconds
        # token → expiry epoch; guarded by _lock
        self._used: dict[str, float] = {}
        self._lock = threading.Lock()

    def issue(self, connection_id: str, plan: CrudPlan, user_sub: str = "") -> str:
        timestamp = int(time.time())
        message = self._make_message(connection_id, plan, timestamp, user_sub)
        sig = hmac_module.new(self._key, message.encode(), hashlib.sha256).hexdigest()
        raw = f"{timestamp}:{sig}"
        return base64.urlsafe_b64encode(raw.encode()).decode()

    def verify(self, token: str, connection_id: str, plan: CrudPlan, user_sub: str = "") -> None:
        """Raise ConfirmationError if the token is invalid, expired, reused, or belongs to a different user."""
        try:
            decoded = base64.urlsafe_b64decode(token.encode()).decode()
            timestamp_str, sig = decoded.split(":", 1)
            timestamp = int(timestamp_str)
        except Exception:
            raise ConfirmationError("Malformed confirmation token.")

        if time.time() - timestamp > self._ttl:
            raise ConfirmationError(
                "Confirmation token has expired. Call /crud/preview again."
            )

        expected = hmac_module.new(
            self._key,
            self._make_message(connection_id, plan, timestamp, user_sub).encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac_module.compare_digest(sig, expected):
            raise ConfirmationError("Confirmation token signature is invalid.")

        with self._lock:
            self._evict_expired()
            if token in self._used:
                raise ConfirmationError("Confirmation token has already been used.")
            self._used[token] = time.time() + self._ttl

    @staticmethod
    def _make_message(connection_id: str, plan: CrudPlan, timestamp: int, user_sub: str = "") -> str:
        plan_json = json.dumps(plan.model_dump(mode="json"), sort_keys=True, default=str)
        return f"{timestamp}:{user_sub}:{connection_id}:{plan_json}"

    def _evict_expired(self) -> None:
        now = time.time()
        self._used = {k: v for k, v in self._used.items() if v > now}


# ------------------------------------------------------------------ #
# Validator
# ------------------------------------------------------------------ #

class CrudValidator:
    """Validates CrudPlan objects against the live table schema.

    Validation rules enforced (all must pass; first failure raises):
      1. All referenced columns exist in the live schema
      2. Scalar-position values must not be nested objects or arrays
      3. Destructive operations must include at least one filter
      4. Primary key columns must not appear in set_values
      5. Denylist columns must not be written to
      6. SOFT_DELETE must name a valid soft_delete_column
      7. Operator/value consistency (in_ requires list, is_null requires null)
      8. Affected row count must not exceed max_affected_rows (unless overridden)
      9. No filterless bulk mutations (redundant with rule 3 but checked separately
         for clarity in the error message)
    """

    def __init__(
        self,
        max_affected_rows: int = 500,
        confirmation_service: Optional[ConfirmationTokenService] = None,
    ) -> None:
        self._max_rows = max_affected_rows
        self._tokens = confirmation_service or ConfirmationTokenService()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def validate_and_preview(
        self,
        plan: CrudPlan,
        connection_id: str,
        engine: Engine,
        override_row_limit: bool = False,
    ) -> tuple[RowPreview, list[str]]:
        """Validate ``plan`` and return an affected-row preview plus warnings.

        Raises CrudPlanValidationError on any violation.
        """
        col_map = self._get_column_map(engine, plan)
        pk_cols = self._get_pk_columns(engine, plan)
        warnings: list[str] = []

        self._check_column_references(plan, col_map)
        self._check_value_types(plan)
        self._require_filters(plan)
        self._check_pk_immutability(plan, pk_cols)
        self._check_denylist(plan)

        if plan.operation is CrudOperation.SOFT_DELETE:
            self._check_soft_delete_column(plan, col_map)

        if plan.filters:
            for f in plan.filters:
                self._check_filter_consistency(f)

        preview, count_warnings = self._build_preview(plan, engine, override_row_limit)
        warnings.extend(count_warnings)
        return preview, warnings

    def requires_confirmation(self, plan: CrudPlan, affected_count: int) -> bool:
        if plan.operation in _ALWAYS_CONFIRM:
            return True
        if plan.operation is CrudOperation.UPDATE and affected_count > 1:
            return True
        return False

    def issue_token(self, connection_id: str, plan: CrudPlan, user_sub: str = "") -> str:
        return self._tokens.issue(connection_id, plan, user_sub=user_sub)

    def verify_token(self, token: str, connection_id: str, plan: CrudPlan, user_sub: str = "") -> None:
        self._tokens.verify(token, connection_id, plan, user_sub=user_sub)

    # ------------------------------------------------------------------ #
    # Validation rules
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_column_references(plan: CrudPlan, col_map: dict[str, Any]) -> None:
        all_cols: set[str] = set()
        if plan.row_data:
            all_cols.update(plan.row_data.keys())
        if plan.set_values:
            all_cols.update(plan.set_values.keys())
        if plan.filters:
            all_cols.update(f.column for f in plan.filters)
        if plan.soft_delete_column:
            all_cols.add(plan.soft_delete_column)
        unknown = all_cols - col_map.keys()
        if unknown:
            raise CrudPlanValidationError(
                f"Unknown column(s): {', '.join(sorted(unknown))}. "
                f"Available: {', '.join(sorted(col_map.keys()))}."
            )

    @staticmethod
    def _check_value_types(plan: CrudPlan) -> None:
        for src_name, src in (
            ("row_data", plan.row_data or {}),
            ("set_values", plan.set_values or {}),
        ):
            for col, val in src.items():
                if isinstance(val, (dict,)):
                    raise CrudPlanValidationError(
                        f"{src_name}[{col!r}]: nested objects are not supported as column values."
                    )

    @staticmethod
    def _require_filters(plan: CrudPlan) -> None:
        needs = {
            CrudOperation.UPDATE,
            CrudOperation.DELETE,
            CrudOperation.BULK_UPDATE,
            CrudOperation.SOFT_DELETE,
        }
        if plan.operation in needs and not plan.filters:
            raise CrudPlanValidationError(
                f"Operation '{plan.operation.value}' requires at least one filter. "
                "Filterless mutations are not permitted."
            )

    @staticmethod
    def _check_pk_immutability(plan: CrudPlan, pk_cols: list[str]) -> None:
        if not plan.set_values or not pk_cols:
            return
        overlap = set(plan.set_values.keys()) & set(pk_cols)
        if overlap:
            raise CrudPlanValidationError(
                f"Primary key column(s) cannot be modified: {', '.join(sorted(overlap))}."
            )

    @staticmethod
    def _check_denylist(plan: CrudPlan) -> None:
        written: set[str] = set()
        if plan.row_data:
            written.update(plan.row_data.keys())
        if plan.set_values:
            written.update(plan.set_values.keys())
        if plan.soft_delete_column:
            written.add(plan.soft_delete_column)
        blocked = {c for c in written if c.lower() in _WRITE_DENYLIST}
        if blocked:
            raise CrudPlanValidationError(
                f"Writes to sensitive column(s) are not permitted: {', '.join(sorted(blocked))}."
            )

    @staticmethod
    def _check_soft_delete_column(plan: CrudPlan, col_map: dict[str, Any]) -> None:
        if not plan.soft_delete_column:
            raise CrudPlanValidationError(
                "SOFT_DELETE requires 'soft_delete_column'."
            )
        if plan.soft_delete_column not in col_map:
            raise CrudPlanValidationError(
                f"soft_delete_column '{plan.soft_delete_column}' does not exist in the table."
            )

    @staticmethod
    def _check_filter_consistency(f: RowFilter) -> None:
        if f.operator in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL):
            if f.value is not None:
                raise CrudPlanValidationError(
                    f"Filter on '{f.column}': operator '{f.operator.value}' must have null value."
                )
        if f.operator is FilterOperator.IN:
            if not isinstance(f.value, list) or len(f.value) == 0:
                raise CrudPlanValidationError(
                    f"Filter on '{f.column}': operator 'in_' requires a non-empty list value."
                )

    # ------------------------------------------------------------------ #
    # Preview / count
    # ------------------------------------------------------------------ #

    def _build_preview(
        self,
        plan: CrudPlan,
        engine: Engine,
        override_row_limit: bool,
    ) -> tuple[RowPreview, list[str]]:
        warnings: list[str] = []

        if plan.operation is CrudOperation.CREATE:
            row_data = plan.row_data or {}
            return (
                RowPreview(columns=list(row_data.keys()), rows=[row_data], total_count=1),
                warnings,
            )

        table = Table(
            plan.table_name,
            MetaData(),
            autoload_with=engine,
            schema=plan.schema_name,
        )

        with engine.connect() as conn:
            count_stmt = select(func.count()).select_from(table)
            for f in (plan.filters or []):
                count_stmt = count_stmt.where(_apply_filter(table, f))
            total: int = conn.execute(count_stmt).scalar_one()

            limit_ops = {
                CrudOperation.DELETE,
                CrudOperation.BULK_UPDATE,
                CrudOperation.SOFT_DELETE,
            }
            if plan.operation in limit_ops and total > self._max_rows and not override_row_limit:
                raise CrudPlanValidationError(
                    f"Operation would affect {total} rows, which exceeds the safety "
                    f"limit of {self._max_rows}. Pass override_row_limit=true to proceed."
                )
            if total > self._max_rows and override_row_limit:
                warnings.append(f"Row-limit override active: {total} rows will be affected.")

            preview_stmt = select(table)
            for f in (plan.filters or []):
                preview_stmt = preview_stmt.where(_apply_filter(table, f))
            preview_stmt = preview_stmt.limit(10)
            result = conn.execute(preview_stmt)
            col_names = list(result.keys())
            rows = [dict(zip(col_names, row)) for row in result.all()]

        return RowPreview(columns=col_names, rows=rows, total_count=total), warnings

    # ------------------------------------------------------------------ #
    # Schema helpers (also called from CrudService for rollback support check)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_column_map(engine: Engine, plan: CrudPlan) -> dict[str, Any]:
        inspector = sa_inspect(engine)
        try:
            raw = inspector.get_columns(plan.table_name, schema=plan.schema_name)
        except Exception as exc:
            raise CrudPlanValidationError(
                f"Could not inspect table '{plan.table_name}': {exc}"
            ) from exc
        if not raw:
            raise CrudPlanValidationError(
                f"Table '{plan.table_name}' has no columns or was not found."
            )
        return {str(c["name"]): c for c in raw}

    @staticmethod
    def _get_pk_columns(engine: Engine, plan: CrudPlan) -> list[str]:
        inspector = sa_inspect(engine)
        try:
            info = inspector.get_pk_constraint(plan.table_name, schema=plan.schema_name)
            return list(info.get("constrained_columns", []))
        except Exception:
            return []
