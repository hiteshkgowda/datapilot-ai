"""A small, thread-safe, bounded LRU cache.

Used to cache parsed DataFrames and derived schemas keyed by the immutable
dataset id. Deliberately in-process and dependency-free (no Redis, no external
store): entries are bounded so memory cannot grow without limit.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Generic, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """A fixed-capacity cache that evicts the least-recently-used entry.

    All operations are guarded by a lock, so the cache is safe to share across
    threads (e.g. requests offloaded to the threadpool).
    """

    def __init__(self, max_entries: int) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1.")
        self._max_entries = max_entries
        self._store: "OrderedDict[K, V]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: K) -> Optional[V]:
        """Return the cached value for ``key`` or ``None``, marking it as used."""
        with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    def put(self, key: K, value: V) -> None:
        """Insert/update ``key`` and evict the oldest entry if over capacity."""
        with self._lock:
            self._store[key] = value
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


class TTLCache(Generic[K, V]):
    """A bounded cache whose entries expire after a fixed time-to-live.

    Suitable for mutable sources (e.g. database tables) where stale data must
    not be served indefinitely. Thread-safe.
    """

    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive.")
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1.")
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: "OrderedDict[K, tuple[float, V]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: K) -> Optional[V]:
        """Return the cached value if present and not expired, else ``None``."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def put(self, key: K, value: V) -> None:
        """Insert ``key`` with a fresh TTL, evicting the oldest if over capacity."""
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._store.clear()
