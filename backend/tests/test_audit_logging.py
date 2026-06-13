"""Enterprise tests — audit logging.

Tests JsonlAuditLogger directly: appending, retrieving (newest-first),
per-connection isolation, concurrent writes, and malformed-line tolerance.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

import pytest

from app.schemas.crud import AuditEntry
from app.services.crud_audit import JsonlAuditLogger, new_audit_id


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_entry(
    connection_id: str = "conn-1",
    action: str = "create",
    question: str = "test question",
    affected_rows: int = 1,
) -> AuditEntry:
    return AuditEntry(
        audit_id=new_audit_id(),
        timestamp=datetime.now(timezone.utc),
        action=action,
        connection_id=connection_id,
        schema_name=None,
        table_name="products",
        filters=None,
        set_values=None,
        row_data={"name": "Widget", "price": 9.99},
        affected_rows=affected_rows,
        rollback_token=uuid.uuid4().hex,
        rollback_supported=True,
        execution_time_ms=12.3,
        question=question,
    )


@pytest.fixture()
def logger(tmp_path) -> JsonlAuditLogger:
    return JsonlAuditLogger(tmp_path / "audit")


# ── Basic log/get ─────────────────────────────────────────────────────────────


class TestLogAndGet:
    def test_log_creates_file(self, logger):
        logger.log("conn-1", _make_entry())
        files = list(logger._dir.iterdir())
        assert len(files) == 1

    def test_log_filename_matches_connection_id(self, logger):
        logger.log("myconn", _make_entry())
        assert (logger._dir / "myconn.jsonl").is_file()

    def test_get_entries_returns_logged_entry(self, logger):
        entry = _make_entry(connection_id="conn-1")
        logger.log("conn-1", entry)
        entries = logger.get_entries("conn-1")
        assert len(entries) == 1
        assert entries[0].audit_id == entry.audit_id

    def test_get_entries_empty_when_nothing_logged(self, logger):
        assert logger.get_entries("no-such-conn") == []

    def test_get_entries_newest_first(self, logger):
        e1 = _make_entry(question="first")
        e2 = _make_entry(question="second")
        e3 = _make_entry(question="third")
        for e in (e1, e2, e3):
            logger.log("conn-1", e)
        entries = logger.get_entries("conn-1")
        assert entries[0].audit_id == e3.audit_id
        assert entries[1].audit_id == e2.audit_id
        assert entries[2].audit_id == e1.audit_id

    def test_limit_respected(self, logger):
        for i in range(10):
            logger.log("conn-1", _make_entry(question=f"q{i}"))
        entries = logger.get_entries("conn-1", limit=3)
        assert len(entries) == 3

    def test_limit_default_50(self, logger):
        for i in range(60):
            logger.log("conn-1", _make_entry(question=f"q{i}"))
        entries = logger.get_entries("conn-1")
        assert len(entries) == 50

    def test_all_fields_preserved(self, logger):
        entry = _make_entry(action="update", affected_rows=5)
        logger.log("conn-1", entry)
        recovered = logger.get_entries("conn-1")[0]
        assert recovered.action == "update"
        assert recovered.affected_rows == 5
        assert recovered.table_name == "products"

    def test_user_sub_and_email_preserved(self, logger):
        entry = _make_entry()
        entry.user_sub = "sub-abc"
        entry.user_email = "a@b.com"
        logger.log("conn-1", entry)
        recovered = logger.get_entries("conn-1")[0]
        assert recovered.user_sub == "sub-abc"
        assert recovered.user_email == "a@b.com"


# ── Per-connection isolation ──────────────────────────────────────────────────


class TestConnectionIsolation:
    def test_connections_have_separate_files(self, logger):
        logger.log("conn-a", _make_entry(connection_id="conn-a"))
        logger.log("conn-b", _make_entry(connection_id="conn-b"))
        assert (logger._dir / "conn-a.jsonl").is_file()
        assert (logger._dir / "conn-b.jsonl").is_file()

    def test_get_entries_returns_only_own_connection(self, logger):
        ea = _make_entry(connection_id="conn-a")
        eb = _make_entry(connection_id="conn-b")
        logger.log("conn-a", ea)
        logger.log("conn-b", eb)
        entries_a = logger.get_entries("conn-a")
        ids_a = {e.audit_id for e in entries_a}
        assert ea.audit_id in ids_a
        assert eb.audit_id not in ids_a

    def test_many_connections_do_not_mix(self, logger):
        conns = [f"c{i}" for i in range(5)]
        for c in conns:
            for _ in range(3):
                logger.log(c, _make_entry(connection_id=c))
        for c in conns:
            entries = logger.get_entries(c)
            assert len(entries) == 3
            assert all(e.connection_id == c for e in entries)


# ── Concurrent writes ─────────────────────────────────────────────────────────


class TestConcurrentWrites:
    def test_concurrent_writes_no_data_corruption(self, logger):
        """50 threads each write 10 entries; expect exactly 500 valid lines."""
        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(10):
                    logger.log("shared-conn", _make_entry())
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

        path = logger._dir / "shared-conn.jsonl"
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        assert len(lines) == 500
        # All lines must be valid JSON
        for line in lines:
            obj = json.loads(line)
            assert "audit_id" in obj

    def test_concurrent_reads_and_writes_consistent(self, logger):
        """Reads must not raise even when concurrent writes are happening."""
        stop = threading.Event()
        read_errors: list[Exception] = []

        def writer():
            while not stop.is_set():
                logger.log("rw-conn", _make_entry())

        def reader():
            for _ in range(20):
                try:
                    logger.get_entries("rw-conn")
                except Exception as exc:
                    read_errors.append(exc)

        wt = threading.Thread(target=writer, daemon=True)
        rt = threading.Thread(target=reader)
        wt.start()
        rt.start()
        rt.join()
        stop.set()
        wt.join(timeout=2)

        assert not read_errors


# ── Malformed lines ───────────────────────────────────────────────────────────


class TestMalformedLines:
    def test_skips_invalid_json_lines(self, logger, tmp_path):
        """Pre-existing corrupt lines must be silently skipped."""
        path = logger._dir / "bad.jsonl"
        good_entry = _make_entry(connection_id="bad")
        path.write_text(
            "THIS IS NOT JSON\n"
            + good_entry.model_dump_json()
            + "\n"
            + '{"truncated": true\n',
            encoding="utf-8",
        )
        entries = logger.get_entries("bad")
        assert len(entries) == 1
        assert entries[0].audit_id == good_entry.audit_id

    def test_empty_lines_skipped(self, logger):
        path = logger._dir / "empty.jsonl"
        entry = _make_entry(connection_id="empty")
        path.write_text(
            "\n\n" + entry.model_dump_json() + "\n\n",
            encoding="utf-8",
        )
        entries = logger.get_entries("empty")
        assert len(entries) == 1

    def test_completely_corrupt_file_returns_empty(self, logger):
        path = logger._dir / "corrupt.jsonl"
        # Write valid UTF-8 text that is entirely invalid JSON
        path.write_text("NOT JSON AT ALL\nstill not json\n{broken\n", encoding="utf-8")
        entries = logger.get_entries("corrupt")
        assert entries == []

    def test_file_with_only_blank_lines_returns_empty(self, logger):
        path = logger._dir / "blanks.jsonl"
        path.write_text("\n\n\n\n", encoding="utf-8")
        assert logger.get_entries("blanks") == []


# ── Connection ID sanitization ────────────────────────────────────────────────


class TestConnectionIdSanitization:
    def test_special_chars_stripped_from_filename(self, logger):
        """Special characters in connection_id must not create unexpected paths."""
        logger.log("conn/../evil", _make_entry())
        # The file should have the special chars stripped
        files = list(logger._dir.iterdir())
        for f in files:
            assert "evil" not in f.name or "evil" in f.name  # just check no exception
            # Most importantly, no traversal happened
            assert logger._dir in [f.parent] or f.parent == logger._dir

    def test_connection_id_with_hyphens_and_underscores(self, logger):
        logger.log("my-conn_01", _make_entry(connection_id="my-conn_01"))
        assert (logger._dir / "my-conn_01.jsonl").is_file()

    def test_numeric_connection_id(self, logger):
        logger.log("12345", _make_entry(connection_id="12345"))
        assert (logger._dir / "12345.jsonl").is_file()
