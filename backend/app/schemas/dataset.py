"""Pydantic schemas describing datasets and API payloads.

These models are the contract between the service layer and the API layer.
Using them as FastAPI ``response_model`` values also drives the auto-generated
OpenAPI documentation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FileType(str, Enum):
    """Supported source file types for a dataset."""

    CSV = "csv"
    EXCEL = "excel"


class DatasetSource(str, Enum):
    """Where a dataset's data comes from."""

    FILE = "file"
    TABLE = "table"


class DbColumn(BaseModel):
    """A database column's discovered schema (stored for table datasets)."""

    name: str
    data_type: str
    is_numeric: bool


class DatasetMetadata(BaseModel):
    """Metadata describing a single dataset (uploaded file or database table)."""

    id: str = Field(..., description="Unique dataset identifier.")
    filename: str = Field(..., description="File name or table display name.")
    source: DatasetSource = Field(
        default=DatasetSource.FILE, description="Data source kind."
    )
    file_type: Optional[FileType] = Field(
        default=None, description="Source file type (file datasets only)."
    )
    size_bytes: int = Field(..., ge=0, description="Raw file size in bytes (0 for tables).")
    rows: int = Field(..., ge=0, description="Number of rows available for analysis.")
    columns: int = Field(..., ge=0, description="Number of columns.")
    column_names: list[str] = Field(
        default_factory=list, description="Ordered column names."
    )
    created_at: datetime = Field(..., description="UTC creation timestamp.")

    # Ownership (Phase A1) — empty string for datasets created before auth
    owner_sub: str = Field(
        default="", description="Google sub of the user who uploaded this dataset."
    )

    # Database-backed datasets only:
    connection_id: Optional[str] = Field(
        default=None, description="Source connection (table datasets)."
    )
    db_schema: Optional[str] = Field(
        default=None, description="Source schema/namespace (table datasets)."
    )
    table_name: Optional[str] = Field(
        default=None, description="Source table (table datasets)."
    )
    row_limit: Optional[int] = Field(
        default=None, description="Max rows loaded for analysis (table datasets)."
    )
    truncated: Optional[bool] = Field(
        default=None, description="Whether the table exceeds the row limit."
    )
    estimated_row_count: Optional[int] = Field(
        default=None, description="Estimated total rows in the table, if known."
    )
    db_columns: Optional[list[DbColumn]] = Field(
        default=None,
        description="Discovered column schema (table datasets), enabling "
        "validation without loading data.",
    )


class UploadResponse(BaseModel):
    """Returned after a successful upload."""

    message: str
    dataset: DatasetMetadata


class DatasetListResponse(BaseModel):
    """Returned when listing all stored datasets."""

    count: int = Field(..., ge=0)
    datasets: list[DatasetMetadata] = Field(default_factory=list)


class DatasetPreview(BaseModel):
    """A preview of a dataset: its shape, schema and first rows."""

    id: str = Field(..., description="Unique dataset identifier.")
    filename: str = Field(..., description="File name or table display name.")
    source: DatasetSource = Field(
        default=DatasetSource.FILE, description="Data source kind."
    )
    file_type: Optional[FileType] = Field(
        default=None, description="Source file type (file datasets only)."
    )
    rows: int = Field(..., ge=0, description="Total number of data rows.")
    columns: int = Field(..., ge=0, description="Total number of columns.")
    column_names: list[str] = Field(
        default_factory=list, description="Ordered column names."
    )
    data_types: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of column name to its pandas data type.",
    )
    preview_row_count: int = Field(
        ..., ge=0, description="Number of rows returned in the preview."
    )
    preview_rows: list[dict[str, Any]] = Field(
        default_factory=list, description="The first rows of the dataset."
    )
