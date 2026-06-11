"""Dataset service: validation, parsing, persistence and listing.

This is the single place that knows *how* datasets are stored. The API layer
depends only on this service's public methods, so swapping the filesystem for
PostgreSQL later (Phase 5) requires no route changes.

Storage layout (inside ``UPLOAD_DIR``):
    <id><ext>     -> the raw uploaded bytes
    <id>.json     -> serialized :class:`DatasetMetadata`
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pandas as pd

from app.core.cache import LRUCache, TTLCache
from app.core.config import Settings
from app.core.exceptions import (
    DatabaseError,
    DatasetNotFoundError,
    ParseError,
    ValidationError,
)
from app.schemas.connection import RegisterTableRequest
from app.schemas.dataset import (
    DatasetMetadata,
    DatasetPreview,
    DatasetSource,
    DbColumn,
    FileType,
)
from app.services.table_loader import TableLoader

if TYPE_CHECKING:
    from app.services.connection_service import ConnectionService

# Allowed extensions per file type, kept as constants to avoid magic strings.
CSV_EXTENSIONS: frozenset[str] = frozenset({".csv"})
EXCEL_EXTENSIONS: frozenset[str] = frozenset({".xlsx", ".xls"})


@dataclass(frozen=True)
class DatasetSchema:
    """Lightweight, cached description of a dataset's columns.

    Derived once per dataset and reused for plan validation and prompting,
    avoiding repeated ``dtypes``/``select_dtypes`` work.
    """

    column_names: tuple[str, ...]
    dtypes: dict[str, str]
    numeric_columns: frozenset[str]


class DatasetService:
    """Handle the lifecycle of uploaded datasets on the local filesystem."""

    def __init__(
        self,
        settings: Settings,
        connection_service: Optional["ConnectionService"] = None,
    ) -> None:
        self._upload_dir: Path = settings.upload_dir
        self._max_bytes: int = settings.max_upload_size_bytes
        self._connections = connection_service
        self._db_max_rows = settings.db_max_rows
        self._table_loader = TableLoader()
        # Ensure the storage directory exists up front.
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        # File frames are immutable (keyed by id) and use an LRU cache. Cached
        # frames are read-only and may be shared safely across threads.
        self._frame_cache: LRUCache[str, pd.DataFrame] = LRUCache(
            settings.dataframe_cache_max_entries
        )
        self._schema_cache: LRUCache[str, DatasetSchema] = LRUCache(
            settings.schema_cache_max_entries
        )
        # Table frames are mutable; they use a TTL cache (bounded staleness).
        self._table_frame_cache: TTLCache[str, pd.DataFrame] = TTLCache(
            ttl_seconds=settings.db_cache_ttl_seconds,
            max_entries=settings.dataframe_cache_max_entries,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def save_csv(self, filename: str, content: bytes, owner_sub: str = "") -> DatasetMetadata:
        """Validate, parse and persist a CSV upload."""
        self._validate_upload(filename, content, CSV_EXTENSIONS, FileType.CSV)
        try:
            frame = pd.read_csv(BytesIO(content))
        except Exception as exc:  # pandas raises a variety of error types
            raise ParseError(
                f"Could not parse CSV file '{filename}': {exc}"
            ) from exc
        return self._persist(filename, content, frame, FileType.CSV, owner_sub=owner_sub)

    def save_excel(self, filename: str, content: bytes, owner_sub: str = "") -> DatasetMetadata:
        """Validate, parse and persist an Excel upload (first sheet)."""
        self._validate_upload(filename, content, EXCEL_EXTENSIONS, FileType.EXCEL)
        try:
            frame = pd.read_excel(BytesIO(content))
        except Exception as exc:
            raise ParseError(
                f"Could not parse Excel file '{filename}': {exc}"
            ) from exc
        return self._persist(filename, content, frame, FileType.EXCEL, owner_sub=owner_sub)

    def list_datasets(self, owner_sub: str = "") -> list[DatasetMetadata]:
        """Return datasets visible to ``owner_sub``, newest first.

        When ``owner_sub`` is non-empty only datasets owned by that user are
        returned.  Pre-auth datasets (``owner_sub=""``) are visible to every
        authenticated user so existing data isn't silently lost after the auth
        migration.  Pass ``owner_sub=""`` to list all (admin / test use).
        """
        datasets: list[DatasetMetadata] = []
        for meta_path in self._upload_dir.glob("*.json"):
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
                meta = DatasetMetadata(**raw)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            # Include if: caller matches owner, OR dataset predates auth (owner_sub=="")
            if owner_sub and meta.owner_sub and meta.owner_sub != owner_sub:
                continue
            datasets.append(meta)
        datasets.sort(key=lambda meta: meta.created_at, reverse=True)
        return datasets

    def get_preview(self, dataset_id: str, limit: int = 10) -> DatasetPreview:
        """Return a preview of a stored dataset.

        Works for both CSV and Excel sources by dispatching on the stored
        :class:`FileType`.

        Raises:
            DatasetNotFoundError: if the dataset or its data file is missing.
            ParseError: if the stored file cannot be read.
        """
        frame, metadata = self.load_dataframe(dataset_id)

        # Serialize via JSON so NaN -> null and datetimes -> ISO strings,
        # keeping the payload valid for the API response.
        preview_rows: list[dict[str, object]] = json.loads(
            frame.head(limit).to_json(orient="records", date_format="iso")
        )

        return DatasetPreview(
            id=metadata.id,
            filename=metadata.filename,
            file_type=metadata.file_type,
            rows=int(frame.shape[0]),
            columns=int(frame.shape[1]),
            column_names=[str(column) for column in frame.columns],
            data_types={
                str(column): str(dtype)
                for column, dtype in frame.dtypes.items()
            },
            preview_row_count=len(preview_rows),
            preview_rows=preview_rows,
        )

    def load_dataframe(
        self, dataset_id: str
    ) -> tuple[pd.DataFrame, DatasetMetadata]:
        """Load a stored dataset into a DataFrame alongside its metadata.

        Reuses the existing storage helpers so callers (e.g. the analytics
        service) never duplicate file-resolution or parsing logic.

        Raises:
            DatasetNotFoundError: if the dataset or its data file is missing.
            ParseError: if the stored file cannot be read.
        """
        metadata = self._load_metadata(dataset_id)
        if metadata.source is DatasetSource.TABLE:
            frame = self._table_frame_cache.get(dataset_id)
            if frame is None:
                frame = self._load_table_frame(metadata)
                self._table_frame_cache.put(dataset_id, frame)
            return frame, metadata

        frame = self._frame_cache.get(dataset_id)
        if frame is None:
            data_path = self._resolve_data_path(dataset_id)
            frame = self._read_frame(data_path, metadata.file_type)
            self._frame_cache.put(dataset_id, frame)
        return frame, metadata

    def load_with_schema(
        self, dataset_id: str
    ) -> tuple[pd.DataFrame, DatasetSchema]:
        """Load a dataset's DataFrame together with its cached schema.

        The schema is derived once per dataset and reused thereafter.

        Raises:
            DatasetNotFoundError: if the dataset or its data file is missing.
            ParseError: if the stored file cannot be read.
        """
        frame, _metadata = self.load_dataframe(dataset_id)
        schema = self._schema_cache.get(dataset_id)
        if schema is None:
            schema = self._build_schema(frame)
            self._schema_cache.put(dataset_id, schema)
        return frame, schema

    def get_metadata(self, dataset_id: str) -> DatasetMetadata:
        """Return a dataset's metadata without loading its data."""
        return self._load_metadata(dataset_id)

    def get_schema(self, dataset_id: str) -> DatasetSchema:
        """Return a dataset's schema, without loading data when possible.

        Table datasets derive their schema from the column info stored at
        registration (no query). File datasets (and legacy tables lacking
        stored columns) fall back to loading and inspecting the frame.
        """
        cached = self._schema_cache.get(dataset_id)
        if cached is not None:
            return cached

        metadata = self._load_metadata(dataset_id)
        if metadata.source is DatasetSource.TABLE and metadata.db_columns:
            schema = DatasetSchema(
                column_names=tuple(c.name for c in metadata.db_columns),
                dtypes={c.name: c.data_type for c in metadata.db_columns},
                numeric_columns=frozenset(
                    c.name for c in metadata.db_columns if c.is_numeric
                ),
            )
            self._schema_cache.put(dataset_id, schema)
            return schema

        _frame, schema = self.load_with_schema(dataset_id)
        return schema

    def register_table(
        self, connection_id: str, request: RegisterTableRequest, owner_sub: str = ""
    ) -> DatasetMetadata:
        """Register a database table as an analyzable dataset.

        Discovers the table's columns and (when possible) its row count, then
        writes a dataset metadata sidecar with ``source=table``. No data is
        copied — the table is loaded on demand at query time.
        """
        if self._connections is None:
            raise DatabaseError("Database connections are not configured.")

        columns = self._connections.describe_table(
            connection_id, request.schema_name, request.table
        )
        estimated = self._connections.estimate_row_count(
            connection_id, request.schema_name, request.table
        )
        effective_limit = min(
            request.row_limit or self._db_max_rows, self._db_max_rows
        )
        if estimated is None:
            rows = effective_limit
            truncated: Optional[bool] = None
        else:
            rows = min(estimated, effective_limit)
            truncated = estimated > effective_limit

        dataset_id = uuid.uuid4().hex
        metadata = DatasetMetadata(
            id=dataset_id,
            filename=request.name or request.table,
            source=DatasetSource.TABLE,
            file_type=None,
            size_bytes=0,
            rows=rows,
            columns=len(columns),
            column_names=[column.name for column in columns],
            created_at=datetime.now(timezone.utc),
            connection_id=connection_id,
            db_schema=request.schema_name,
            table_name=request.table,
            row_limit=effective_limit,
            truncated=truncated,
            estimated_row_count=estimated,
            db_columns=[
                DbColumn(
                    name=column.name,
                    data_type=column.data_type,
                    is_numeric=column.is_numeric,
                )
                for column in columns
            ],
            owner_sub=owner_sub,
        )
        meta_path = self._upload_dir / f"{dataset_id}.json"
        meta_path.write_text(metadata.model_dump_json(), encoding="utf-8")
        return metadata

    def _load_table_frame(self, metadata: DatasetMetadata) -> pd.DataFrame:
        """Load a capped DataFrame for a table-backed dataset."""
        if self._connections is None or metadata.connection_id is None:
            raise DatabaseError("Database connections are not configured.")
        engine = self._connections.get_engine(metadata.connection_id)
        limit = metadata.row_limit or self._db_max_rows
        return self._table_loader.load(
            engine, metadata.db_schema, metadata.table_name, limit
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_schema(frame: pd.DataFrame) -> DatasetSchema:
        """Derive the column schema (names, dtypes, numeric set) from a frame."""
        dtypes = {str(column): str(dtype) for column, dtype in frame.dtypes.items()}
        numeric_columns = frozenset(
            str(column) for column in frame.select_dtypes(include="number").columns
        )
        return DatasetSchema(
            column_names=tuple(dtypes.keys()),
            dtypes=dtypes,
            numeric_columns=numeric_columns,
        )
    def _validate_upload(
        self,
        filename: str,
        content: bytes,
        allowed_extensions: frozenset[str],
        file_type: FileType,
    ) -> None:
        """Enforce business rules common to every upload."""
        if not filename:
            raise ValidationError("A filename is required.")

        extension = Path(filename).suffix.lower()
        if extension not in allowed_extensions:
            allowed = ", ".join(sorted(allowed_extensions))
            raise ValidationError(
                f"Invalid {file_type.value} file extension '{extension}'. "
                f"Allowed extensions: {allowed}."
            )

        if not content:
            raise ValidationError("The uploaded file is empty.")

        if len(content) > self._max_bytes:
            raise ValidationError(
                f"File exceeds the maximum allowed size of "
                f"{self._max_bytes} bytes."
            )

    def _persist(
        self,
        filename: str,
        content: bytes,
        frame: pd.DataFrame,
        file_type: FileType,
        owner_sub: str = "",
    ) -> DatasetMetadata:
        """Write the raw file plus its metadata sidecar and return metadata."""
        dataset_id = uuid.uuid4().hex
        extension = Path(filename).suffix.lower()

        data_path = self._upload_dir / f"{dataset_id}{extension}"
        data_path.write_bytes(content)

        metadata = DatasetMetadata(
            id=dataset_id,
            filename=filename,
            file_type=file_type,
            size_bytes=len(content),
            rows=int(frame.shape[0]),
            columns=int(frame.shape[1]),
            column_names=[str(column) for column in frame.columns],
            created_at=datetime.now(timezone.utc),
            owner_sub=owner_sub,
        )

        meta_path = self._upload_dir / f"{dataset_id}.json"
        meta_path.write_text(metadata.model_dump_json(), encoding="utf-8")

        return metadata

    def _load_metadata(self, dataset_id: str) -> DatasetMetadata:
        """Load the metadata sidecar for a dataset.

        Raises:
            DatasetNotFoundError: if the metadata file is missing.
            ParseError: if the metadata file exists but cannot be read.
        """
        meta_path = self._upload_dir / f"{dataset_id}.json"
        if not meta_path.is_file():
            raise DatasetNotFoundError(f"Dataset '{dataset_id}' was not found.")
        try:
            raw = json.loads(meta_path.read_text(encoding="utf-8"))
            return DatasetMetadata(**raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ParseError(
                f"Metadata for dataset '{dataset_id}' is unreadable: {exc}"
            ) from exc

    def _resolve_data_path(self, dataset_id: str) -> Path:
        """Locate the raw data file for a dataset (the non-JSON sibling)."""
        for path in self._upload_dir.glob(f"{dataset_id}.*"):
            if path.suffix.lower() != ".json" and path.is_file():
                return path
        raise DatasetNotFoundError(
            f"Data file for dataset '{dataset_id}' was not found."
        )

    def _read_frame(self, path: Path, file_type: FileType) -> pd.DataFrame:
        """Read a stored data file into a DataFrame based on its type."""
        try:
            if file_type is FileType.CSV:
                return pd.read_csv(path)
            return pd.read_excel(path)
        except Exception as exc:
            raise ParseError(
                f"Could not read dataset file '{path.name}': {exc}"
            ) from exc
