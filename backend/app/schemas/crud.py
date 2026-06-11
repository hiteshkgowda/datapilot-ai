"""Pydantic schemas for safe AI-assisted CRUD operations (Phase 7).

All plan objects use ``extra="forbid"`` so the LLM cannot inject unexpected
fields that would bypass validation silently.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class CrudOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BULK_UPDATE = "bulk_update"
    SOFT_DELETE = "soft_delete"


class FilterOperator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in_"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class RowFilter(BaseModel):
    model_config = {"extra": "forbid"}

    column: str = Field(..., min_length=1)
    operator: FilterOperator
    value: Any = None


class CrudPlan(BaseModel):
    """Structured mutation intent produced by the LLM planner.

    Never contains raw SQL. All fields are deterministically validated
    by CrudValidator before any DML reaches the database.
    """

    model_config = {"extra": "forbid"}

    operation: CrudOperation
    schema_name: Optional[str] = None
    table_name: str = Field(..., min_length=1)

    # CREATE only — key/value pairs for the new row
    row_data: Optional[dict[str, Any]] = None

    # UPDATE / BULK_UPDATE / DELETE / SOFT_DELETE — WHERE clause
    filters: Optional[list[RowFilter]] = None

    # UPDATE / BULK_UPDATE only — SET clause
    set_values: Optional[dict[str, Any]] = None

    # SOFT_DELETE only — column to stamp and optional value to use
    soft_delete_column: Optional[str] = None
    soft_delete_value: Optional[Any] = None  # None → executor resolves default


class CrudRequest(BaseModel):
    """Natural-language CRUD request from the client."""

    dataset_id: Optional[str] = Field(default=None, min_length=1)
    connection_id: Optional[str] = Field(default=None, min_length=1)
    schema_name: Optional[str] = None
    table_name: Optional[str] = Field(default=None, min_length=1)
    question: str = Field(..., min_length=1)


class CrudExecuteRequest(BaseModel):
    """Execute a CrudPlan returned by a previous /crud/preview call."""

    connection_id: str = Field(..., min_length=1)
    plan: CrudPlan
    confirmation_token: Optional[str] = None
    override_row_limit: bool = False
    question: str = ""


class RowPreview(BaseModel):
    """Rows that will be affected by the planned operation (read-only preview)."""

    columns: list[str]
    rows: list[dict[str, Any]]
    total_count: int


class CrudPreviewResponse(BaseModel):
    connection_id: str
    plan: CrudPlan
    preview: RowPreview
    affected_row_count: int
    requires_confirmation: bool
    confirmation_token: Optional[str] = None
    rollback_supported: bool
    warnings: list[str] = []


class CrudExecuteResponse(BaseModel):
    operation: CrudOperation
    table_name: str
    affected_rows: int
    rollback_token: Optional[str] = None
    rollback_supported: bool
    execution_time_ms: float
    audit_id: str


class RollbackRequest(BaseModel):
    connection_id: str = Field(..., min_length=1)
    rollback_token: str = Field(..., min_length=1)


class RollbackResponse(BaseModel):
    restored_rows: int
    execution_time_ms: float
    audit_id: str


class AuditEntry(BaseModel):
    audit_id: str
    timestamp: datetime
    action: str
    connection_id: str
    schema_name: Optional[str]
    table_name: str
    filters: Optional[list[dict[str, Any]]]
    set_values: Optional[dict[str, Any]]
    row_data: Optional[dict[str, Any]]
    affected_rows: int
    rollback_token: Optional[str]
    rollback_supported: bool
    execution_time_ms: float
    question: str
    # Phase A1 — who performed the operation (empty for pre-auth audit entries)
    user_sub: str = ""
    user_email: str = ""


class AuditListResponse(BaseModel):
    connection_id: str
    count: int
    entries: list[AuditEntry]
