"""Orchestrator for safe AI-assisted CRUD operations (Phase 7).

Wires together planner → validator → executor, enforces confirmation
requirements, and resolves dataset_id / connection_id routing.
"""

from __future__ import annotations

from typing import Optional

from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import (
    ConfirmationError,
    ConnectionNotFoundError,
    LLMError,
    ValidationError,
)
from app.schemas.crud import (
    AuditListResponse,
    CrudExecuteRequest,
    CrudExecuteResponse,
    CrudOperation,
    CrudPreviewResponse,
    CrudPlan,
    CrudRequest,
    RollbackRequest,
    RollbackResponse,
)
from app.services.connection_service import ConnectionService
from app.services.crud_audit import AuditLogger
from app.services.crud_executor import CrudExecutor
from app.services.crud_planner import CrudPlanner
from app.services.crud_validator import CrudValidator
from app.services.dataset_service import DatasetService

_ALWAYS_CONFIRM = frozenset(
    {CrudOperation.DELETE, CrudOperation.BULK_UPDATE, CrudOperation.SOFT_DELETE}
)


class CrudService:
    def __init__(
        self,
        planner: CrudPlanner,
        validator: CrudValidator,
        executor: CrudExecutor,
        audit_logger: AuditLogger,
        connection_service: ConnectionService,
        dataset_service: DatasetService,
    ) -> None:
        self._planner = planner
        self._validator = validator
        self._executor = executor
        self._audit = audit_logger
        self._connections = connection_service
        self._datasets = dataset_service

    # ------------------------------------------------------------------ #
    # Preview
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Ownership helpers
    # ------------------------------------------------------------------ #

    def _assert_conn_owner(self, connection_id: str, owner_sub: str) -> None:
        """Raise ValidationError (as 404) when the caller doesn't own the connection.

        Returns immediately when ``owner_sub`` is empty (pre-auth / admin path)
        or when the connection has no recorded owner (pre-auth record).
        """
        try:
            record = self._connections._read_record(connection_id)
        except ConnectionNotFoundError:
            raise ValidationError(f"Connection '{connection_id}' not found.")
        if owner_sub and record.owner_sub and record.owner_sub != owner_sub:
            raise ValidationError(f"Connection '{connection_id}' not found.")

    # ------------------------------------------------------------------ #
    # Preview
    # ------------------------------------------------------------------ #

    async def preview(self, request: CrudRequest, user_sub: str = "") -> CrudPreviewResponse:
        connection_id, schema_name, table_name = self._resolve(request, owner_sub=user_sub)
        engine = self._connections.get_engine(connection_id)

        # Build column schema dict for the LLM prompt
        columns = self._connections.describe_table(connection_id, schema_name, table_name)
        schema = {c.name: c.data_type for c in columns}

        # LLM generates a structured plan — never raw SQL
        raw = await self._planner.generate_crud_plan(request.question, schema, table_name)
        try:
            plan = CrudPlan(**raw)
        except PydanticValidationError as exc:
            raise LLMError(f"LLM returned an invalid plan structure: {exc}") from exc

        # Deterministic validation against the live schema
        preview, warnings = self._validator.validate_and_preview(
            plan, connection_id, engine, override_row_limit=False
        )

        pk_cols = self._validator._get_pk_columns(engine, plan)
        rollback_supported = bool(pk_cols)
        req_confirm = self._validator.requires_confirmation(plan, preview.total_count)
        token: Optional[str] = (
            self._validator.issue_token(connection_id, plan, user_sub=user_sub)
            if req_confirm else None
        )

        return CrudPreviewResponse(
            connection_id=connection_id,
            plan=plan,
            preview=preview,
            affected_row_count=preview.total_count,
            requires_confirmation=req_confirm,
            confirmation_token=token,
            rollback_supported=rollback_supported,
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    # Execute
    # ------------------------------------------------------------------ #

    async def execute(
        self,
        request: CrudExecuteRequest,
        user_sub: str = "",
        user_email: str = "",
    ) -> CrudExecuteResponse:
        # Ownership gate — connection_id is a direct field on CrudExecuteRequest.
        self._assert_conn_owner(request.connection_id, user_sub)

        # Destructive operations always require a confirmation token
        if request.plan.operation in _ALWAYS_CONFIRM:
            if not request.confirmation_token:
                raise ConfirmationError(
                    f"Operation '{request.plan.operation.value}' requires a confirmation "
                    "token. Call /crud/preview first and include the returned token."
                )
        # Verify any supplied token — user_sub binding prevents cross-user reuse
        if request.confirmation_token:
            self._validator.verify_token(
                request.confirmation_token, request.connection_id, request.plan,
                user_sub=user_sub,
            )

        engine = self._connections.get_engine(request.connection_id)
        # Re-validate in case the client submitted an altered plan
        self._validator.validate_and_preview(
            request.plan,
            request.connection_id,
            engine,
            override_row_limit=request.override_row_limit,
        )

        return self._executor.execute(
            plan=request.plan,
            connection_id=request.connection_id,
            engine=engine,
            audit_logger=self._audit,
            question=request.question,
            user_sub=user_sub,
            user_email=user_email,
        )

    # ------------------------------------------------------------------ #
    # Rollback
    # ------------------------------------------------------------------ #

    def rollback(self, request: RollbackRequest, user_sub: str = "") -> RollbackResponse:
        self._assert_conn_owner(request.connection_id, user_sub)
        engine = self._connections.get_engine(request.connection_id)
        return self._executor.rollback(
            connection_id=request.connection_id,
            rollback_token=request.rollback_token,
            engine=engine,
            audit_logger=self._audit,
        )

    # ------------------------------------------------------------------ #
    # Audit
    # ------------------------------------------------------------------ #

    def get_audit(self, connection_id: str, user_sub: str = "", limit: int = 50) -> AuditListResponse:
        self._assert_conn_owner(connection_id, user_sub)
        entries = self._audit.get_entries(connection_id, limit=limit)
        return AuditListResponse(
            connection_id=connection_id,
            count=len(entries),
            entries=entries,
        )

    # ------------------------------------------------------------------ #
    # Routing helpers
    # ------------------------------------------------------------------ #

    def _resolve(self, request: CrudRequest, owner_sub: str = "") -> tuple[str, Optional[str], str]:
        """Return (connection_id, schema_name, table_name) from the request.

        Ownership is enforced here for both routing paths so callers never need
        to repeat the check:
        - dataset_id path: verifies the caller owns the dataset before reading
          its embedded connection_id.
        - connection_id path: verifies the caller owns the connection directly.
        """
        if request.dataset_id:
            meta = self._datasets.get_metadata(request.dataset_id)
            if owner_sub and meta.owner_sub and meta.owner_sub != owner_sub:
                raise ValidationError(f"Dataset '{request.dataset_id}' not found.")
            from app.schemas.dataset import DatasetSource
            if meta.source is DatasetSource.FILE:
                raise ValidationError(
                    "CRUD operations are not available for file-based datasets. "
                    "Register a database table first."
                )
            if not meta.connection_id or not meta.table_name:
                raise ValidationError(
                    f"Dataset '{request.dataset_id}' is missing connection or table info."
                )
            # Also verify the embedded connection is owned by this user.
            self._assert_conn_owner(meta.connection_id, owner_sub)
            return meta.connection_id, meta.db_schema, meta.table_name

        if request.connection_id and request.table_name:
            self._assert_conn_owner(request.connection_id, owner_sub)
            return request.connection_id, request.schema_name, request.table_name

        raise ValidationError(
            "Provide either 'dataset_id' or both 'connection_id' and 'table_name'."
        )
