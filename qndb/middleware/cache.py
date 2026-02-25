"""
Middleware Cache Module

Thread-safe caching for quantum database operations with disk-backed
persistence, dependency-based invalidation, consistent hashing, probabilistic
result caching, and circuit deduplication.

Features:
 - RLock-protected QuantumResultCache and QueryCache
 - DiskBackedCache with SQLite backend
 - Dependency-based invalidation (track which tables a query touches)
 - ConsistentHashRing for distributed cache prep
 - Probabilistic cache: store measurement distributions
 - Circuit deduplication via structural hashing
"""

import time
import json
import hashlib
import math
import sqlite3
import threading
import os
from typing import Dict, Any, Optional, Tuple, List, Set
import numpy as np
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


# ======================================================================
# Thread-safe quantum result cache
# ======================================================================

class QuantumResultCache:
    """Thread-safe cache for quantum operation results."""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _generate_key(self, circuit_data: Any, params: Dict[str, Any]) -> str:
        clean_params: Dict[str, Any] = {}
        for k, v in params.items():
            if isinstance(v, np.ndarray):
                clean_params[k] = v.tolist()
            else:
                clean_params[k] = v
        combined = f"{circuit_data}:{json.dumps(clean_params, sort_keys=True)}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(self, circuit_data: Any, params: Dict[str, Any]) -> Optional[Any]:
        key = self._generate_key(circuit_data, params)
        with self._lock:
            if key in self._cache:
                result, ts = self._cache[key]
                if time.time() - ts <= self._ttl:
                    self._hits += 1
                    return result
                del self._cache[key]
            self._misses += 1
        return None

    def put(self, circuit_data: Any, params: Dict[str, Any], result: Any) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest = min(self._cache, key=lambda k: self._cache[k][1])
                del self._cache[oldest]
            key = self._generate_key(circuit_data, params)
            self._cache[key] = (result, time.time())

    def invalidate(self, pattern: Optional[str] = None) -> None:
        with self._lock:
            if pattern is None:
                self._cache.clear()
                return
            keys = [k for k in self._cache if pattern in k]
            for k in keys:
                del self._cache[k]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            active = sum(1 for _, ts in self._cache.values() if now - ts <= self._ttl)
            total = self._hits + self._misses
            return {
                "total_entries": len(self._cache),
                "active_entries": active,
                "expired_entries": len(self._cache) - active,
                "max_size": self._max_size,
                "ttl": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total else 0.0,
            }


# ======================================================================
# Query cache with dependency tracking
# ======================================================================

class QueryCache:
    """Thread-safe query cache with table-dependency tracking."""

    def __init__(self, max_size: int = 500, ttl: int = 1800):
        self._result_cache = QuantumResultCache(max_size, ttl)
        self._query_plans: Dict[str, str] = {}
        self._query_tables: Dict[str, Set[str]] = {}  # query_hash → {table_names}
        self._lock = threading.RLock()

    def _hash_query(self, query_string: str, query_params: Dict) -> str:
        data = f"{query_string}:{json.dumps(query_params, sort_keys=True)}"
        return hashlib.md5(data.encode()).hexdigest()

    def store_plan(self, query_string: str, query_params: Dict, plan_hash: str,
                   tables: Optional[Set[str]] = None) -> None:
        qh = self._hash_query(query_string, query_params)
        with self._lock:
            self._query_plans[qh] = plan_hash
            if tables:
                self._query_tables[qh] = tables

    def get_result(self, query_string: str, query_params: Dict) -> Optional[Any]:
        qh = self._hash_query(query_string, query_params)
        with self._lock:
            ph = self._query_plans.get(qh)
        if ph is not None:
            return self._result_cache.get(ph, query_params)
        return None

    def store_result(self, query_string: str, query_params: Dict,
                     plan_hash: str, result: Any,
                     tables: Optional[Set[str]] = None) -> None:
        qh = self._hash_query(query_string, query_params)
        with self._lock:
            self._query_plans[qh] = plan_hash
            if tables:
                self._query_tables[qh] = tables
        self._result_cache.put(plan_hash, query_params, result)

    def invalidate_query(self, query_string: str, query_params: Dict) -> None:
        qh = self._hash_query(query_string, query_params)
        with self._lock:
            ph = self._query_plans.pop(qh, None)
            self._query_tables.pop(qh, None)
        if ph:
            self._result_cache.invalidate(ph)

    def invalidate_by_table(self, table_name: str) -> None:
        """Invalidate all cached queries that depend on *table_name*."""
        with self._lock:
            to_remove: List[str] = []
            for qh, tables in self._query_tables.items():
                if table_name in tables:
                    to_remove.append(qh)
            # Fallback: also check query hash string
            for qh in list(self._query_plans):
                if table_name in qh and qh not in to_remove:
                    to_remove.append(qh)
            for qh in to_remove:
                ph = self._query_plans.pop(qh, None)
                self._query_tables.pop(qh, None)
                if ph:
                    self._result_cache.invalidate(ph)


# ======================================================================
# Disk-backed cache (SQLite)
# ======================================================================

class DiskBackedCache:
    """Persistent cache backed by SQLite with LRU eviction."""

    def __init__(self, db_path: str = "cache.db", max_size: int = 10_000, ttl: int = 7200):
        self._db_path = db_path
        self._max_size = max_size
        self._ttl = ttl
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                created REAL,
                accessed REAL
            )
        """)
        self._conn.commit()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            cur = self._conn.execute("SELECT value, created FROM cache WHERE key=?", (key,))
            row = cur.fetchone()
            if row is None:
                return None
            val, created = row
            if time.time() - created > self._ttl:
                self._conn.execute("DELETE FROM cache WHERE key=?", (key,))
                self._conn.commit()
                return None
            self._conn.execute("UPDATE cache SET accessed=? WHERE key=?", (time.time(), key))
            self._conn.commit()
            return json.loads(val)

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            cnt = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            if cnt >= self._max_size:
                self._conn.execute(
                    "DELETE FROM cache WHERE key IN (SELECT key FROM cache ORDER BY accessed ASC LIMIT ?)",
                    (max(1, cnt - self._max_size + 1),),
                )
            now = time.time()
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, created, accessed) VALUES (?,?,?,?)",
                (key, json.dumps(value), now, now),
            )
            self._conn.commit()

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache WHERE key=?", (key,))
            self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM cache")
            self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


# ======================================================================
# Consistent hash ring (distributed cache prep)
# ======================================================================

class ConsistentHashRing:
    """Consistent hash ring for distributing cache entries across nodes."""

    def __init__(self, nodes: Optional[List[str]] = None, replicas: int = 128):
        self._replicas = replicas
        self._ring: Dict[int, str] = {}
        self._sorted_keys: List[int] = []
        for node in (nodes or []):
            self.add_node(node)

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: str) -> None:
        for i in range(self._replicas):
            h = self._hash(f"{node}:{i}")
            self._ring[h] = node
        self._sorted_keys = sorted(self._ring.keys())

    def remove_node(self, node: str) -> None:
        for i in range(self._replicas):
            h = self._hash(f"{node}:{i}")
            self._ring.pop(h, None)
        self._sorted_keys = sorted(self._ring.keys())

    def get_node(self, key: str) -> Optional[str]:
        if not self._ring:
            return None
        h = self._hash(key)
        for k in self._sorted_keys:
            if k >= h:
                return self._ring[k]
        return self._ring[self._sorted_keys[0]]


# ======================================================================
# Probabilistic cache (measurement distributions)
# ======================================================================

class ProbabilisticCache:
    """Cache that stores measurement distributions and reuses when confidence
    is sufficient, avoiding full re-execution."""

    def __init__(self, min_confidence: float = 0.90, max_distributions: int = 512):
        self._distributions: Dict[str, Dict[str, Any]] = {}
        self._min_confidence = min_confidence
        self._max = max_distributions
        self._lock = threading.RLock()

    @staticmethod
    def _key(circuit_hash: str) -> str:
        return circuit_hash

    def store(self, circuit_hash: str, counts: Dict[str, int], shots: int) -> None:
        dist = {s: c / shots for s, c in counts.items()}
        with self._lock:
            if len(self._distributions) >= self._max:
                oldest = next(iter(self._distributions))
                del self._distributions[oldest]
            self._distributions[self._key(circuit_hash)] = {
                "distribution": dist,
                "shots": shots,
                "timestamp": time.time(),
            }

    def sample(self, circuit_hash: str, n: int = 1) -> Optional[Dict[str, int]]:
        """Return synthetic counts sampled from cached distribution."""
        with self._lock:
            entry = self._distributions.get(self._key(circuit_hash))
        if entry is None:
            return None
        dist = entry["distribution"]
        if not dist:
            return None
        # confidence check: enough shots?
        if entry["shots"] < 100:
            return None
        states = list(dist.keys())
        probs = [dist[s] for s in states]
        rng = np.random.default_rng()
        indices = rng.choice(len(states), size=n, p=probs)
        result: Dict[str, int] = {}
        for idx in indices:
            s = states[idx]
            result[s] = result.get(s, 0) + 1
        return result


# ======================================================================
# Circuit deduplication
# ======================================================================

class CircuitDeduplicator:
    """Detect equivalent circuits by hashing their gate structure."""

    @staticmethod
    def structure_hash(circuit) -> str:
        """Hash a circuit's gate structure to detect equivalence."""
        parts: List[str] = []
        if hasattr(circuit, 'all_operations'):
            for op in circuit.all_operations():
                gate_name = str(type(op.gate).__name__) if hasattr(op, 'gate') else str(op)
                qubits = tuple(str(q) for q in op.qubits) if hasattr(op, 'qubits') else ()
                parts.append(f"{gate_name}({','.join(qubits)})")
        elif isinstance(circuit, (list, tuple)):
            parts = [str(g) for g in circuit]
        else:
            parts = [str(circuit)]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()


# ======================================================================
# cache_quantum_result decorator (kept backward-compatible)
# ======================================================================

def cache_quantum_result(func):
    """Decorator for caching results of quantum operations."""

    @lru_cache(maxsize=128)
    def cached_key(*args, **kwargs):
        parts = [str(a) for a in args]
        parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
        return hashlib.md5(":".join(parts).encode()).hexdigest()

    def wrapper(*args, **kwargs):
        key = cached_key(*args, **kwargs)
        if hasattr(wrapper, "_results") and key in wrapper._results:
            result, ts = wrapper._results[key]
            if time.time() - ts < 1800:
                return result
        result = func(*args, **kwargs)
        if not hasattr(wrapper, "_results"):
            wrapper._results = {}
        wrapper._results[key] = (result, time.time())
        return result

    def clear_cache():
        if hasattr(wrapper, "_results"):
            wrapper._results.clear()

    wrapper.clear_cache = clear_cache
    return wrapper