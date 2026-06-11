"""Database connection management and schema discovery.

Owns saved connections (credentials encrypted at rest), pooled SQLAlchemy
engines, connectivity tests, and inspector-based schema discovery. This service
never returns secrets and never builds SQL from raw user strings.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.crypto import CredentialCipher
from app.core.exceptions import (
    ConnectionNotFoundError,
    DatabaseError,
    ValidationError,
)
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionMetadata,
    ConnectionTestResult,
    DbType,
    TableColumn,
    TableInfo,
)

# Schemas that hold engine internals, not user data.
_SCHEMA_DENYLIST = frozenset(
    {
        "information_schema",
        "pg_catalog",
        "pg_toast",
        "performance_schema",
        "mysql",
        "sys",
    }
)

_DRIVERS = {
    DbType.POSTGRESQL: "postgresql+psycopg",
    DbType.MYSQL: "mysql+pymysql",
}


class _StoredConnection(BaseModel):
    """On-disk connection record (password stored encrypted)."""

    id: str
    name: str
    db_type: DbType
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password_encrypted: Optional[str] = None
    created_at: datetime
    # Phase A1 — empty for connections created before auth was added
    owner_sub: str = ""


class ConnectionService:
    """Manage database connections, engines and schema discovery."""

    def __init__(self, settings: Settings, cipher: CredentialCipher) -> None:
        self._dir = settings.connections_dir
        self._cipher = cipher
        self._pool_size = settings.db_pool_size
        self._connect_timeout = settings.db_connect_timeout_seconds
        self._dir.mkdir(parents=True, exist_ok=True)
        self._engines: dict[str, Engine] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    def create_connection(self, request: ConnectionCreate, owner_sub: str = "") -> ConnectionMetadata:
        """Validate and persist a new connection."""
        self._validate_create(request)

        password_encrypted: Optional[str] = None
        if request.password:
            # Encryption availability is enforced in _validate_create.
            password_encrypted = self._cipher.encrypt(request.password)

        record = _StoredConnection(
            id=uuid.uuid4().hex,
            name=request.name,
            db_type=request.db_type,
            host=request.host,
            port=request.port,
            database=request.database,
            username=request.username,
            password_encrypted=password_encrypted,
            created_at=datetime.now(timezone.utc),
            owner_sub=owner_sub,
        )
        path = self._dir / f"{record.id}.json"
        path.write_text(record.model_dump_json(), encoding="utf-8")
        return self._to_metadata(record)

    def list_connections(self, owner_sub: str = "") -> list[ConnectionMetadata]:
        """Return connections visible to ``owner_sub``, newest first.

        Connections with ``owner_sub=""`` (created before auth) are visible to
        all authenticated users to avoid losing pre-migration data.
        """
        records: list[_StoredConnection] = []
        for path in self._dir.glob("*.json"):
            try:
                record = _StoredConnection(**json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            if owner_sub and record.owner_sub and record.owner_sub != owner_sub:
                continue
            records.append(record)
        records.sort(key=lambda r: r.created_at, reverse=True)
        return [self._to_metadata(r) for r in records]

    def delete_connection(self, connection_id: str) -> None:
        """Delete a connection and dispose its engine."""
        path = self._dir / f"{connection_id}.json"
        if not path.is_file():
            raise ConnectionNotFoundError(
                f"Connection '{connection_id}' was not found."
            )
        with self._lock:
            engine = self._engines.pop(connection_id, None)
        if engine is not None:
            engine.dispose()
        path.unlink()

    # ------------------------------------------------------------------ #
    # Connectivity & engines
    # ------------------------------------------------------------------ #
    def test_connection(self, connection_id: str) -> ConnectionTestResult:
        """Open a connection and run a trivial query."""
        try:
            engine = self.get_engine(connection_id)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except ConnectionNotFoundError:
            raise
        except (SQLAlchemyError, Exception) as exc:  # driver import errors too
            return ConnectionTestResult(status="error", message=str(exc))
        return ConnectionTestResult(status="ok", message="Connection successful.")

    def get_engine(self, connection_id: str) -> Engine:
        """Return a cached engine for a connection, creating it if needed."""
        with self._lock:
            engine = self._engines.get(connection_id)
            if engine is None:
                engine = self._create_engine(self._read_record(connection_id))
                self._engines[connection_id] = engine
            return engine

    def dispose_all(self) -> None:
        """Dispose every cached engine (called on application shutdown)."""
        with self._lock:
            for engine in self._engines.values():
                engine.dispose()
            self._engines.clear()

    # ------------------------------------------------------------------ #
    # Schema discovery
    # ------------------------------------------------------------------ #
    def list_tables(self, connection_id: str) -> list[TableInfo]:
        """Discover user tables across non-system schemas."""
        engine = self.get_engine(connection_id)
        try:
            inspector = inspect(engine)
            schemas = inspector.get_schema_names() or [None]
            tables: list[TableInfo] = []
            for schema in schemas:
                if schema in _SCHEMA_DENYLIST:
                    continue
                for name in inspector.get_table_names(schema=schema):
                    tables.append(TableInfo(schema_name=schema, name=name))
            return tables
        except SQLAlchemyError as exc:
            raise DatabaseError("Failed to list tables.") from exc

    def describe_table(
        self, connection_id: str, schema: Optional[str], table: str
    ) -> list[TableColumn]:
        """Return the columns of a table with a numeric flag."""
        engine = self.get_engine(connection_id)
        try:
            inspector = inspect(engine)
            columns = inspector.get_columns(table, schema=schema)
        except SQLAlchemyError as exc:
            raise ValidationError(
                f"Table '{table}' could not be inspected."
            ) from exc
        if not columns:
            raise ValidationError(f"Table '{table}' has no columns or was not found.")
        return [
            TableColumn(
                name=str(column["name"]),
                data_type=str(column["type"]),
                is_numeric=self._is_numeric(column["type"]),
            )
            for column in columns
        ]

    def estimate_row_count(
        self, connection_id: str, schema: Optional[str], table: str
    ) -> Optional[int]:
        """Return COUNT(*) for a table, or None if it cannot be determined."""
        engine = self.get_engine(connection_id)
        try:
            reflected = Table(table, MetaData(), autoload_with=engine, schema=schema)
            with engine.connect() as connection:
                result = connection.execute(
                    select(func.count()).select_from(reflected)
                )
                return int(result.scalar_one())
        except (SQLAlchemyError, ValueError):
            return None

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _validate_create(self, request: ConnectionCreate) -> None:
        if request.db_type is DbType.SQLITE:
            if not request.database:
                raise ValidationError("SQLite requires a 'database' file path.")
        else:
            missing = [
                field
                for field, value in (
                    ("host", request.host),
                    ("database", request.database),
                    ("username", request.username),
                )
                if not value
            ]
            if missing:
                raise ValidationError(
                    f"{request.db_type.value} requires: {', '.join(missing)}."
                )
        if request.password and not self._cipher.available:
            raise ValidationError(
                "A password was provided but no DB_ENCRYPTION_KEY is configured."
            )

    def _read_record(self, connection_id: str) -> _StoredConnection:
        path = self._dir / f"{connection_id}.json"
        if not path.is_file():
            raise ConnectionNotFoundError(
                f"Connection '{connection_id}' was not found."
            )
        return _StoredConnection(**json.loads(path.read_text(encoding="utf-8")))

    def _create_engine(self, record: _StoredConnection) -> Engine:
        url = self._build_url(record)
        kwargs: dict = {"pool_pre_ping": True}
        if record.db_type is DbType.SQLITE:
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["pool_size"] = self._pool_size
            kwargs["connect_args"] = {"connect_timeout": self._connect_timeout}
        try:
            return create_engine(url, **kwargs)
        except SQLAlchemyError as exc:
            raise DatabaseError("Failed to create database engine.") from exc

    def _build_url(self, record: _StoredConnection) -> URL:
        if record.db_type is DbType.SQLITE:
            return URL.create("sqlite", database=record.database)
        password = (
            self._cipher.decrypt(record.password_encrypted)
            if record.password_encrypted
            else None
        )
        return URL.create(
            _DRIVERS[record.db_type],
            username=record.username,
            password=password,
            host=record.host,
            port=record.port,
            database=record.database,
        )

    @staticmethod
    def _is_numeric(sql_type: object) -> bool:
        """Best-effort check that a SQL column type maps to a number."""
        try:
            python_type = sql_type.python_type  # type: ignore[attr-defined]
        except (NotImplementedError, AttributeError):
            return False
        return python_type in (int, float, complex, Decimal)

    @staticmethod
    def _to_metadata(record: _StoredConnection) -> ConnectionMetadata:
        return ConnectionMetadata(
            id=record.id,
            name=record.name,
            db_type=record.db_type,
            host=record.host,
            port=record.port,
            database=record.database,
            username=record.username,
            created_at=record.created_at,
        )
