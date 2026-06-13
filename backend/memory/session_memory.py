"""L1 in-process cache + optional Redis L2 for conversation sessions.

Key design:
  - L1: TTLCache (in-process, expires after ttl_seconds)
  - L2: Redis (optional; activated when REDIS_URL is set and redis package installed)

Cache keys are scoped as "{user_sub}:{session_id}" to prevent cross-user access.
On cache miss L2 is consulted and the result is promoted to L1.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.core.cache import TTLCache

logger = logging.getLogger(__name__)


class SessionMemory:
    """Fast in-process cache for recent conversation turns."""

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        max_sessions: int = 100,
        redis_url: Optional[str] = None,
        redis_ttl_seconds: float = 86400.0,
    ) -> None:
        self._cache: TTLCache[str, list[dict]] = TTLCache(
            ttl_seconds=ttl_seconds, max_entries=max_sessions
        )
        self._redis: Any = None
        self._redis_ttl = int(redis_ttl_seconds)

        if redis_url:
            try:
                import redis.asyncio as aioredis  # noqa: PLC0415

                self._redis = aioredis.from_url(redis_url, decode_responses=True)
                logger.info("SessionMemory: Redis backend enabled at %s", redis_url)
            except ImportError:
                logger.warning(
                    "REDIS_URL is set but the 'redis' package is not installed. "
                    "Falling back to in-process cache only. "
                    "Install with: pip install 'redis[asyncio]'"
                )

    # ------------------------------------------------------------------
    # Key helpers
    # ------------------------------------------------------------------

    def _l1_key(self, session_id: str, user_sub: str) -> str:
        return f"{user_sub}:{session_id}"

    def _l2_key(self, session_id: str, user_sub: str) -> str:
        return f"uda:memory:{user_sub}:{session_id}"

    # ------------------------------------------------------------------
    # Synchronous (L1 only) — for use in non-async helpers
    # ------------------------------------------------------------------

    def get(self, session_id: str, user_sub: str) -> list[dict]:
        """Return L1-cached turns or empty list."""
        return self._cache.get(self._l1_key(session_id, user_sub)) or []

    def put(self, session_id: str, user_sub: str, turns: list[dict]) -> None:
        """Store turns in L1 cache."""
        self._cache.put(self._l1_key(session_id, user_sub), turns)

    def delete(self, session_id: str, user_sub: str) -> int:
        """Clear L1 cache entry. Returns prior count."""
        existing = self._cache.get(self._l1_key(session_id, user_sub)) or []
        count = len(existing)
        self._cache.put(self._l1_key(session_id, user_sub), [])
        return count

    # ------------------------------------------------------------------
    # Async (L1 + optional Redis)
    # ------------------------------------------------------------------

    async def get_async(self, session_id: str, user_sub: str) -> list[dict]:
        """Return turns from L1, promoting from Redis on L1 miss."""
        cached = self._cache.get(self._l1_key(session_id, user_sub))
        if cached is not None:
            return cached

        if self._redis:
            try:
                raw = await self._redis.get(self._l2_key(session_id, user_sub))
                if raw:
                    turns: list[dict] = json.loads(raw)
                    self._cache.put(self._l1_key(session_id, user_sub), turns)
                    return turns
            except Exception as exc:
                logger.warning("Redis get failed (using empty): %s", exc)

        return []

    async def put_async(self, session_id: str, user_sub: str, turns: list[dict]) -> None:
        """Write turns to L1 and (if available) Redis."""
        self._cache.put(self._l1_key(session_id, user_sub), turns)

        if self._redis:
            try:
                await self._redis.setex(
                    self._l2_key(session_id, user_sub),
                    self._redis_ttl,
                    json.dumps(turns, default=str),
                )
            except Exception as exc:
                logger.warning("Redis put failed (L1 still updated): %s", exc)

    async def delete_async(self, session_id: str, user_sub: str) -> None:
        """Remove from L1 and Redis."""
        self._cache.put(self._l1_key(session_id, user_sub), [])

        if self._redis:
            try:
                await self._redis.delete(self._l2_key(session_id, user_sub))
            except Exception as exc:
                logger.warning("Redis delete failed: %s", exc)
