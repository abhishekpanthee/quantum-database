"""LRU plan cache keyed on normalised query text."""

import hashlib
import time
from typing import Dict, Tuple, Any, Optional


class PlanCache:
    """LRU plan cache keyed on normalised query text."""

    def __init__(self, capacity: int = 256):
        self._capacity = capacity
        self._cache: Dict[str, Tuple[Any, float, int]] = {}  # key → (plan, ts, hits)

    @staticmethod
    def _key(raw_query: str) -> str:
        return hashlib.md5(raw_query.strip().upper().encode()).hexdigest()

    def get(self, raw_query: str) -> Optional[Any]:
        k = self._key(raw_query)
        entry = self._cache.get(k)
        if entry is None:
            return None
        plan, ts, hits = entry
        self._cache[k] = (plan, ts, hits + 1)
        return plan

    def put(self, raw_query: str, plan: Any) -> None:
        k = self._key(raw_query)
        if len(self._cache) >= self._capacity:
            victim = min(self._cache, key=lambda x: self._cache[x][2])
            del self._cache[victim]
        self._cache[k] = (plan, time.time(), 0)

    def invalidate(self, raw_query: str) -> None:
        self._cache.pop(self._key(raw_query), None)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)
