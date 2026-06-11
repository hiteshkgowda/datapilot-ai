"""Tests for the connection service and credential encryption (SQLite-based)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.core.crypto import CredentialCipher
from app.core.exceptions import DataAssistantError, ValidationError
from app.schemas.connection import ConnectionCreate, DbType
from app.services.connection_service import ConnectionService


def _sqlite_db(tmp_path):
    """Create a small SQLite database file and return its path."""
    db_path = tmp_path / "sample.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sales (region TEXT, amount INTEGER)"))
        conn.execute(
            text(
                "INSERT INTO sales (region, amount) VALUES "
                "('North', 100), ('South', 50), ('North', 30)"
            )
        )
    engine.dispose()
    return db_path


def _service(tmp_path, key=None):
    settings = Settings(connections_dir=tmp_path / "connections")
    return ConnectionService(settings, CredentialCipher(key))


# --------------------------------------------------------------------------- #
# Credential encryption
# --------------------------------------------------------------------------- #
def test_cipher_round_trip():
    cipher = CredentialCipher(CredentialCipher.generate_key())
    token = cipher.encrypt("s3cret")
    assert token != "s3cret"
    assert cipher.decrypt(token) == "s3cret"


def test_cipher_refuses_without_key():
    cipher = CredentialCipher(None)
    assert cipher.available is False
    with pytest.raises(DataAssistantError):
        cipher.encrypt("nope")


def test_password_without_key_is_rejected(tmp_path):
    service = _service(tmp_path, key=None)
    request = ConnectionCreate(
        name="pg",
        db_type=DbType.POSTGRESQL,
        host="localhost",
        database="db",
        username="u",
        password="secret",
    )
    with pytest.raises(ValidationError):
        service.create_connection(request)


def test_password_is_encrypted_at_rest(tmp_path):
    service = _service(tmp_path, key=CredentialCipher.generate_key())
    meta = service.create_connection(
        ConnectionCreate(
            name="pg",
            db_type=DbType.POSTGRESQL,
            host="localhost",
            database="db",
            username="u",
            password="secret",
        )
    )
    # The response must not expose a password.
    assert not hasattr(meta, "password")
    # The persisted file must store an encrypted (not plaintext) password.
    stored = json.loads(
        (tmp_path / "connections" / f"{meta.id}.json").read_text()
    )
    assert stored["password_encrypted"] not in (None, "secret")


# --------------------------------------------------------------------------- #
# Connectivity & discovery (SQLite)
# --------------------------------------------------------------------------- #
def test_sqlite_test_connection_and_discovery(tmp_path):
    service = _service(tmp_path)
    db_path = _sqlite_db(tmp_path)
    meta = service.create_connection(
        ConnectionCreate(name="local", db_type=DbType.SQLITE, database=str(db_path))
    )

    assert service.test_connection(meta.id).status == "ok"

    tables = service.list_tables(meta.id)
    sales = next(t for t in tables if t.name == "sales")

    columns = {c.name: c for c in service.describe_table(meta.id, sales.schema_name, "sales")}
    assert columns["amount"].is_numeric is True
    assert columns["region"].is_numeric is False

    assert service.estimate_row_count(meta.id, sales.schema_name, "sales") == 3

    service.dispose_all()
