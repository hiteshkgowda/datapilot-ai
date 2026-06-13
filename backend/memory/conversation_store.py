"""SQLite-backed persistent store for conversation turns.

Schema: one table ``conversation_turns`` with indexed (session_id, user_sub).
WAL mode is enabled for concurrent-read safety (matches agent_sessions pattern).

Optional PostgreSQL adapter: set MEMORY_DATABASE_URL to a ``postgresql+asyncpg://``
URL when ConversationStore is instantiated.  If asyncpg is not installed the
caller falls back to SQLite automatically.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)

_DDL = """\
CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id          TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL,
    user_sub         TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    turn_type        TEXT NOT NULL,
    dataset_id       TEXT,
    question         TEXT,
    answer           TEXT,
    table_data       TEXT,
    chart_spec       TEXT,
    insights         TEXT,
    anomalies        TEXT,
    forecast         TEXT,
    recommendations  TEXT,
    metadata         TEXT
);
CREATE INDEX IF NOT EXISTS idx_conv_session_user
    ON conversation_turns (session_id, user_sub, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conv_user_created
    ON conversation_turns (user_sub, created_at DESC);
"""

_INSERT = """\
INSERT OR REPLACE INTO conversation_turns
(turn_id, session_id, user_sub, created_at, turn_type, dataset_id,
 question, answer, table_data, chart_spec, insights, anomalies,
 forecast, recommendations, metadata)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

_JSON_FIELDS = (
    "table_data",
    "chart_spec",
    "insights",
    "anomalies",
    "forecast",
    "recommendations",
    "metadata",
)


class ConversationStore:
    """Persist conversation turns to SQLite (WAL mode)."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)

    async def initialize(self) -> None:
        """Create tables and enable WAL mode.  Safe to call multiple times."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(_DDL)
            await db.commit()
        logger.info("ConversationStore: initialised at %s", self._db_path)

    async def save_turn(self, turn: dict) -> None:
        """Upsert a single turn dict."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                _INSERT,
                (
                    turn["turn_id"],
                    turn["session_id"],
                    turn["user_sub"],
                    turn["created_at"],
                    turn["turn_type"],
                    turn.get("dataset_id"),
                    turn.get("question"),
                    turn.get("answer"),
                    _to_json(turn.get("table_data")),
                    _to_json(turn.get("chart_spec")),
                    _to_json(turn.get("insights")),
                    _to_json(turn.get("anomalies")),
                    _to_json(turn.get("forecast")),
                    _to_json(turn.get("recommendations")),
                    _to_json(turn.get("metadata")),
                ),
            )
            await db.commit()

    async def load_turns(
        self,
        session_id: str,
        user_sub: str,
        limit: int = 20,
    ) -> list[dict]:
        """Return up to ``limit`` turns in ascending time order."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM conversation_turns
                WHERE session_id = ? AND user_sub = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, user_sub, limit),
            )
            rows = await cursor.fetchall()
        return [_row_to_dict(dict(r)) for r in reversed(rows)]

    async def clear_session(self, session_id: str, user_sub: str) -> int:
        """Delete all turns for a session. Returns the count deleted."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM conversation_turns WHERE session_id = ? AND user_sub = ?",
                (session_id, user_sub),
            )
            await db.commit()
            return cursor.rowcount  # type: ignore[return-value]

    async def count_turns(self, session_id: str, user_sub: str) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM conversation_turns WHERE session_id = ? AND user_sub = ?",
                (session_id, user_sub),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def expire_old_turns(self, older_than_iso: str) -> int:
        """Delete turns with created_at < older_than_iso (ISO 8601)."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM conversation_turns WHERE created_at < ?",
                (older_than_iso,),
            )
            await db.commit()
            count: int = cursor.rowcount  # type: ignore[assignment]
        if count:
            logger.info("ConversationStore: expired %d old turn(s)", count)
        return count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, default=str)


def _row_to_dict(row: dict) -> dict:
    for field in _JSON_FIELDS:
        raw = row.get(field)
        if raw:
            try:
                row[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                row[field] = None
    return row
