"""Schemas for database connections and schema discovery (Phase 5)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DbType(str, Enum):
    """Supported database engines."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"


class ConnectionCreate(BaseModel):
    """Request to create a database connection.

    For SQLite, ``database`` is the file path. For PostgreSQL/MySQL, ``host``,
    ``database`` and ``username`` are required; ``password`` is optional.
    """

    name: str = Field(..., min_length=1, description="Human-readable name.")
    db_type: DbType = Field(..., description="Database engine.")
    host: Optional[str] = Field(default=None, description="Server host.")
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    database: Optional[str] = Field(
        default=None, description="Database name, or SQLite file path."
    )
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)


class ConnectionMetadata(BaseModel):
    """Stored connection, as returned by the API (never includes a password)."""

    id: str
    name: str
    db_type: DbType
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    created_at: datetime


class ConnectionTestResult(BaseModel):
    """Outcome of a connectivity test."""

    status: str = Field(..., description="'ok' on success.")
    message: str


class TableInfo(BaseModel):
    """A discovered table."""

    schema_name: Optional[str] = Field(default=None, description="Schema/namespace.")
    name: str = Field(..., description="Table name.")


class TableListResponse(BaseModel):
    """Result of schema discovery."""

    count: int = Field(..., ge=0)
    tables: list[TableInfo] = Field(default_factory=list)


class TableColumn(BaseModel):
    """A discovered column."""

    name: str
    data_type: str
    is_numeric: bool


class RegisterTableRequest(BaseModel):
    """Request to register a table as an analyzable dataset."""

    schema_name: Optional[str] = Field(default=None, description="Schema/namespace.")
    table: str = Field(..., min_length=1, description="Table name.")
    name: Optional[str] = Field(
        default=None, description="Optional dataset display name."
    )
    row_limit: Optional[int] = Field(
        default=None, ge=1, description="Optional override for max rows loaded."
    )
