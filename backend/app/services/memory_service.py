"""MemoryService — facade over SessionMemory (L1) and ConversationStore (L2).

Responsibilities:
  1. record_turn()          — store a turn after any successful API call
  2. get_context()          — retrieve full session context for display
  3. clear_session()        — wipe a session from all storage layers
  4. build_agent_context()  — format turns as agent planner conversation_history
  5. expire_old_sessions()  — delete turns older than session_ttl (TTL cleanup)

Table data is capped at max_table_rows rows before storage to prevent unbounded growth.
SQLite writes happen fire-and-forget via asyncio.ensure_future so they never
block the caller's response path.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.schemas.memory import (
    ConversationContext,
    ConversationTurn,
    MemoryClearResponse,
    TurnType,
)

logger = logging.getLogger(__name__)


class MemoryService:
    """Public API for the conversational memory system."""

    def __init__(
        self,
        store: Any,          # ConversationStore
        session_memory: Any, # SessionMemory
        context_builder: Any,# ContextBuilder
        max_turns_per_session: int = 20,
        max_table_rows: int = 50,
        session_ttl_seconds: float = 86400.0,
    ) -> None:
        self._store = store
        self._cache = session_memory
        self._builder = context_builder
        self._max_turns = max_turns_per_session
        self._max_table_rows = max_table_rows
        self._session_ttl = session_ttl_seconds

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def record_turn(
        self,
        session_id: str,
        user_sub: str,
        turn_type: TurnType | str,
        *,
        dataset_id: Optional[str] = None,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        table_data: Optional[list[dict]] = None,
        chart_spec: Optional[dict] = None,
        insights: Optional[dict] = None,
        anomalies: Optional[dict] = None,
        forecast: Optional[dict] = None,
        recommendations: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> ConversationTurn:
        """Append a turn to the session.

        L1 cache is updated synchronously; SQLite write is fire-and-forget.
        Returns the stored ConversationTurn.
        """
        if table_data and len(table_data) > self._max_table_rows:
            table_data = table_data[: self._max_table_rows]

        now = datetime.now(tz=timezone.utc).isoformat()
        turn_id = uuid.uuid4().hex
        turn_type_str = (
            turn_type.value if isinstance(turn_type, TurnType) else str(turn_type)
        )

        turn_dict: dict[str, Any] = {
            "turn_id": turn_id,
            "session_id": session_id,
            "user_sub": user_sub,
            "created_at": now,
            "turn_type": turn_type_str,
            "dataset_id": dataset_id,
            "question": question,
            "answer": answer,
            "table_data": table_data,
            "chart_spec": chart_spec,
            "insights": insights,
            "anomalies": anomalies,
            "forecast": forecast,
            "recommendations": recommendations,
            "metadata": metadata,
        }

        # L1 update (synchronous, in-process)
        existing = await self._cache.get_async(session_id, user_sub)
        updated = (existing + [turn_dict])[-self._max_turns :]
        await self._cache.put_async(session_id, user_sub, updated)

        # L2 write (fire-and-forget — never blocks the request path)
        asyncio.ensure_future(self._store.save_turn(turn_dict))

        return ConversationTurn.model_validate(turn_dict)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_context(self, session_id: str, user_sub: str) -> ConversationContext:
        """Return the full conversation context for a session."""
        turns_raw = await self._cache.get_async(session_id, user_sub)

        # L1 miss → hydrate from SQLite and repopulate cache
        if not turns_raw:
            turns_raw = await self._store.load_turns(
                session_id, user_sub, limit=self._max_turns
            )
            if turns_raw:
                await self._cache.put_async(session_id, user_sub, turns_raw)

        turns = [ConversationTurn.model_validate(t) for t in turns_raw]
        summary = self._builder.build_summary(turns_raw)
        datasets = self._builder.extract_dataset_ids(turns_raw)

        return ConversationContext(
            session_id=session_id,
            turn_count=len(turns),
            turns=turns,
            summary=summary,
            datasets_referenced=datasets,
            last_dataset_id=datasets[0] if datasets else None,
        )

    async def build_agent_context(self, session_id: str, user_sub: str) -> list[dict]:
        """Return conversation history in agent planner format.

        Each item: {"goal": str, "summary": str}
        """
        turns_raw = await self._cache.get_async(session_id, user_sub)
        if not turns_raw:
            turns_raw = await self._store.load_turns(
                session_id, user_sub, limit=self._max_turns
            )
        return self._builder.build_agent_context(turns_raw)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def clear_session(self, session_id: str, user_sub: str) -> MemoryClearResponse:
        """Remove all turns for a session from L1 cache, Redis, and SQLite."""
        self._cache.delete(session_id, user_sub)
        await self._cache.delete_async(session_id, user_sub)
        cleared = await self._store.clear_session(session_id, user_sub)
        return MemoryClearResponse(
            session_id=session_id,
            turns_cleared=cleared,
            message=f"Cleared {cleared} turn(s) from session.",
        )

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def expire_old_sessions(self) -> int:
        """Delete turns older than session_ttl_seconds. Returns count removed."""
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=self._session_ttl)
        return await self._store.expire_old_turns(cutoff.isoformat())
