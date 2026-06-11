"""Audit logging for CRUD operations.

Defines the AuditLogger protocol so alternative backends (database, cloud
logging) can be swapped in without touching service code.  The default
JsonlAuditLogger writes one JSON line per operation to a per-connection flat
file under ``crud_audit_dir``.
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.schemas.crud import AuditEntry


def new_audit_id() -> str:
    return uuid.uuid4().hex


@runtime_checkable
class AuditLogger(Protocol):
    """Abstraction over the CRUD audit log backend."""

    def log(self, connection_id: str, entry: AuditEntry) -> None:
        """Append one entry to the log for ``connection_id``."""
        ...

    def get_entries(self, connection_id: str, limit: int = 50) -> list[AuditEntry]:
        """Return the last ``limit`` entries for ``connection_id``, newest first."""
        ...


class JsonlAuditLogger:
    """Append-only JSON Lines audit logger backed by per-connection flat files.

    Each connection gets its own ``<connection_id>.jsonl`` file.  Writes are
    protected by a per-file threading.Lock so concurrent FastAPI requests do
    not interleave lines.
    """

    def __init__(self, audit_dir: Path) -> None:
        self._dir = audit_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # AuditLogger protocol
    # ------------------------------------------------------------------ #

    def log(self, connection_id: str, entry: AuditEntry) -> None:
        path = self._path(connection_id)
        lock = self._get_lock(connection_id)
        line = entry.model_dump_json() + "\n"
        with lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)

    def get_entries(self, connection_id: str, limit: int = 50) -> list[AuditEntry]:
        path = self._path(connection_id)
        if not path.is_file():
            return []
        lock = self._get_lock(connection_id)
        with lock:
            raw = path.read_text(encoding="utf-8")
        entries: list[AuditEntry] = []
        for line in reversed(raw.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(AuditEntry(**json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
            if len(entries) >= limit:
                break
        return entries

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _path(self, connection_id: str) -> Path:
        safe = "".join(c for c in connection_id if c.isalnum() or c in "-_")
        return self._dir / f"{safe}.jsonl"

    def _get_lock(self, connection_id: str) -> threading.Lock:
        with self._meta_lock:
            if connection_id not in self._locks:
                self._locks[connection_id] = threading.Lock()
            return self._locks[connection_id]
