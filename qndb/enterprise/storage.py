"""
Advanced Storage — Enterprise Storage Features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Columnar storage, quantum-native data types, compression,
materialized views, partitioning, and tiered storage.
"""

import hashlib
import json
import logging
import math
import os
import pickle
import threading
import time
from collections import OrderedDict
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple, Union

import cirq
import numpy as np

logger = logging.getLogger(__name__)


# ======================================================================
# Quantum-native data types
# ======================================================================

class QuantumDataType(Enum):
    """Column types that extend classical SQL with quantum semantics."""

    CLASSICAL_INT = auto()
    CLASSICAL_FLOAT = auto()
    CLASSICAL_STRING = auto()
    CLASSICAL_BOOL = auto()
    SUPERPOSITION = auto()        # column whose value is a superposition of basis states
    ENTANGLED = auto()            # row whose columns are entangled
    PROBABILITY_DIST = auto()     # stores measurement-probability distribution
    STATE_VECTOR = auto()         # full amplitude vector
    DENSITY_MATRIX = auto()       # density matrix ρ


# ======================================================================
# Columnar Storage
# ======================================================================

class ColumnarStorage:
    """Columnar storage format optimised for quantum encoding.

    Data is stored column-wise so that each column can be independently
    amplitude-encoded into qubits.  Metadata tracks column data types
    (including quantum-native types) and encoding parameters.

    Args:
        storage_dir: Root directory for column files.
    """

    def __init__(self, storage_dir: str = "quantum_columnar") -> None:
        self.storage_dir = storage_dir
        self._lock = threading.RLock()
        self._tables: Dict[str, Dict[str, Any]] = {}
        os.makedirs(storage_dir, exist_ok=True)

    # -- DDL ---------------------------------------------------------------

    def create_table(
        self,
        table_name: str,
        columns: Dict[str, QuantumDataType],
    ) -> None:
        """Create a new columnar table.

        Args:
            table_name: Unique table identifier.
            columns: ``{col_name: QuantumDataType}``.
        """
        with self._lock:
            if table_name in self._tables:
                raise ValueError(f"Table '{table_name}' already exists")
            table_dir = os.path.join(self.storage_dir, table_name)
            os.makedirs(table_dir, exist_ok=True)
            schema = {col: dtype.name for col, dtype in columns.items()}
            self._tables[table_name] = {
                "schema": schema,
                "row_count": 0,
                "created_at": datetime.now().isoformat(),
                "columns": {col: [] for col in columns},
            }
            self._save_table_metadata(table_name)
            logger.info("Created columnar table '%s' with %d columns",
                        table_name, len(columns))

    def drop_table(self, table_name: str) -> None:
        with self._lock:
            if table_name not in self._tables:
                raise KeyError(f"Table '{table_name}' not found")
            del self._tables[table_name]
            logger.info("Dropped table '%s'", table_name)

    # -- DML ---------------------------------------------------------------

    def insert_rows(self, table_name: str, rows: List[Dict[str, Any]]) -> int:
        """Insert rows into the table (column-wise storage).

        Returns:
            Number of rows inserted.
        """
        with self._lock:
            tbl = self._get_table(table_name)
            for row in rows:
                for col in tbl["schema"]:
                    tbl["columns"][col].append(row.get(col))
                tbl["row_count"] += 1
            self._save_table_metadata(table_name)
            return len(rows)

    def read_column(self, table_name: str, column: str) -> List[Any]:
        """Read an entire column (optimal for quantum amplitude encoding)."""
        with self._lock:
            tbl = self._get_table(table_name)
            if column not in tbl["columns"]:
                raise KeyError(f"Column '{column}' not in table '{table_name}'")
            return list(tbl["columns"][column])

    def scan_rows(
        self,
        table_name: str,
        columns: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Reconstruct rows from columnar data."""
        with self._lock:
            tbl = self._get_table(table_name)
            cols = columns or list(tbl["schema"].keys())
            n = tbl["row_count"] if limit is None else min(limit, tbl["row_count"])
            return [{c: tbl["columns"][c][i] for c in cols} for i in range(n)]

    # -- quantum-native helpers --------------------------------------------

    def store_superposition(
        self, table_name: str, column: str, amplitudes: np.ndarray,
    ) -> None:
        """Store a superposition column (state vector)."""
        with self._lock:
            tbl = self._get_table(table_name)
            if tbl["schema"].get(column) != QuantumDataType.SUPERPOSITION.name:
                raise TypeError(f"Column '{column}' is not SUPERPOSITION type")
            tbl["columns"][column].append(amplitudes.tolist())
            tbl["row_count"] = max(
                tbl["row_count"], max(len(v) for v in tbl["columns"].values())
            )

    def store_entangled_row(
        self, table_name: str, state_vector: np.ndarray, metadata: Optional[Dict] = None,
    ) -> None:
        """Store an entangled row whose columns are correlated."""
        with self._lock:
            tbl = self._get_table(table_name)
            for col in tbl["schema"]:
                dtype_name = tbl["schema"][col]
                if dtype_name == QuantumDataType.ENTANGLED.name:
                    tbl["columns"][col].append({
                        "state_vector": state_vector.tolist(),
                        "metadata": metadata or {},
                    })
                else:
                    tbl["columns"][col].append(None)
            tbl["row_count"] += 1

    # -- internal helpers --------------------------------------------------

    def _get_table(self, name: str) -> Dict[str, Any]:
        if name not in self._tables:
            raise KeyError(f"Table '{name}' not found")
        return self._tables[name]

    def _save_table_metadata(self, table_name: str) -> None:
        path = os.path.join(self.storage_dir, table_name, "meta.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        meta = {k: v for k, v in self._tables[table_name].items() if k != "columns"}
        with open(path, "w") as f:
            json.dump(meta, f, indent=2)

    def table_info(self, table_name: str) -> Dict[str, Any]:
        tbl = self._get_table(table_name)
        return {
            "table_name": table_name,
            "schema": dict(tbl["schema"]),
            "row_count": tbl["row_count"],
            "created_at": tbl.get("created_at"),
        }


# ======================================================================
# Quantum-aware column compression
# ======================================================================

class QuantumColumnCompressor:
    """Quantum-aware column compression.

    Exploits amplitude-encoding properties: a column of *N* classical
    values can be represented in ⌈log₂N⌉ qubits.  This class provides
    encode/decode helpers that measure the compression ratio.
    """

    def compress(self, data: List[float]) -> Dict[str, Any]:
        """Compress a numeric column via amplitude encoding.

        Returns:
            Dict with ``amplitudes``, ``num_qubits``, ``original_length``,
            ``compression_ratio``.
        """
        arr = np.asarray(data, dtype=float)
        n = len(arr)
        num_qubits = max(1, int(math.ceil(math.log2(n)))) if n > 1 else 1
        padded_len = 2 ** num_qubits
        padded = np.zeros(padded_len)
        padded[:n] = arr
        norm = float(np.linalg.norm(padded))
        if norm > 0:
            padded = padded / norm

        ratio = n / num_qubits if num_qubits else 1.0
        logger.debug("Compressed %d values → %d qubits (%.1f:1)", n, num_qubits, ratio)
        return {
            "amplitudes": padded.tolist(),
            "norm": norm,
            "num_qubits": num_qubits,
            "original_length": n,
            "compression_ratio": ratio,
        }

    def decompress(self, compressed: Dict[str, Any]) -> List[float]:
        """Reconstruct column data from compressed representation."""
        amps = np.asarray(compressed["amplitudes"])
        norm = compressed["norm"]
        n = compressed["original_length"]
        return (amps[:n] * norm).tolist()


# ======================================================================
# Materialized Views with circuit caching
# ======================================================================

class MaterializedViewManager:
    """Materialized views with automatic quantum circuit caching.

    A view stores a query definition plus its most recent result and
    the compiled quantum circuit, enabling instant replay without
    recompilation.

    Args:
        cache_ttl: Seconds before a cached result is considered stale.
    """

    def __init__(self, cache_ttl: int = 3600) -> None:
        self._views: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._cache_ttl = cache_ttl

    def create_view(
        self,
        name: str,
        query: str,
        source_tables: List[str],
        circuit: Optional[cirq.Circuit] = None,
        result: Optional[Any] = None,
    ) -> None:
        """Register a new materialized view."""
        with self._lock:
            self._views[name] = {
                "query": query,
                "source_tables": source_tables,
                "circuit": circuit,
                "result": result,
                "refreshed_at": time.time() if result else 0,
                "created_at": datetime.now().isoformat(),
            }
        logger.info("Created materialized view '%s'", name)

    def get_result(self, name: str) -> Optional[Any]:
        """Return cached result if still fresh, else *None*."""
        with self._lock:
            view = self._views.get(name)
            if view is None:
                raise KeyError(f"View '{name}' not found")
            if time.time() - view["refreshed_at"] <= self._cache_ttl:
                return view["result"]
        return None

    def refresh(
        self,
        name: str,
        new_result: Any,
        new_circuit: Optional[cirq.Circuit] = None,
    ) -> None:
        """Update the cached result and optional circuit."""
        with self._lock:
            view = self._views.get(name)
            if view is None:
                raise KeyError(f"View '{name}' not found")
            view["result"] = new_result
            view["refreshed_at"] = time.time()
            if new_circuit is not None:
                view["circuit"] = new_circuit
        logger.info("Refreshed materialized view '%s'", name)

    def invalidate_by_table(self, table_name: str) -> List[str]:
        """Invalidate all views that depend on *table_name*.

        Returns:
            Names of invalidated views.
        """
        invalidated = []
        with self._lock:
            for vname, vdata in self._views.items():
                if table_name in vdata["source_tables"]:
                    vdata["result"] = None
                    vdata["refreshed_at"] = 0
                    invalidated.append(vname)
        return invalidated

    def list_views(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": n,
                    "query": v["query"],
                    "source_tables": v["source_tables"],
                    "is_fresh": time.time() - v["refreshed_at"] <= self._cache_ttl,
                    "created_at": v["created_at"],
                }
                for n, v in self._views.items()
            ]


# ======================================================================
# Partitioning
# ======================================================================

class PartitionManager:
    """Partition manager for time-based, hash-based, and
    quantum-state-based partitioning.

    Partitions are logical shards of a table that can be pruned
    during query planning to avoid scanning irrelevant data.
    """

    class Strategy(Enum):
        TIME = auto()
        HASH = auto()
        QUANTUM_STATE = auto()

    def __init__(self) -> None:
        self._partitions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def create_partition(
        self,
        table_name: str,
        strategy: "PartitionManager.Strategy",
        key_column: str,
        num_partitions: int = 4,
    ) -> None:
        with self._lock:
            self._partitions[table_name] = {
                "strategy": strategy,
                "key_column": key_column,
                "num_partitions": num_partitions,
                "buckets": {i: [] for i in range(num_partitions)},
                "created_at": datetime.now().isoformat(),
            }
        logger.info("Partitioned '%s' by %s on '%s' (%d parts)",
                     table_name, strategy.name, key_column, num_partitions)

    def assign_partition(self, table_name: str, row: Dict[str, Any]) -> int:
        """Return the partition index for a row."""
        with self._lock:
            pinfo = self._partitions.get(table_name)
            if pinfo is None:
                raise KeyError(f"No partition config for '{table_name}'")

            key = row.get(pinfo["key_column"])
            n = pinfo["num_partitions"]

            if pinfo["strategy"] == self.Strategy.TIME:
                ts = self._to_timestamp(key)
                bucket = int(ts) % n
            elif pinfo["strategy"] == self.Strategy.HASH:
                h = int(hashlib.md5(str(key).encode()).hexdigest(), 16)
                bucket = h % n
            elif pinfo["strategy"] == self.Strategy.QUANTUM_STATE:
                if isinstance(key, (list, np.ndarray)):
                    h = int(hashlib.md5(np.asarray(key).tobytes()).hexdigest(), 16)
                else:
                    h = hash(key)
                bucket = abs(h) % n
            else:
                bucket = 0

            pinfo["buckets"][bucket].append(row)
            return bucket

    def prune_partitions(
        self, table_name: str, predicate: Callable[[int], bool],
    ) -> List[int]:
        """Return partition indices that satisfy *predicate*."""
        with self._lock:
            pinfo = self._partitions.get(table_name)
            if pinfo is None:
                return []
            return [i for i in range(pinfo["num_partitions"]) if predicate(i)]

    def get_partition_data(self, table_name: str, partition_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            pinfo = self._partitions.get(table_name)
            if pinfo is None:
                raise KeyError(f"No partition config for '{table_name}'")
            return list(pinfo["buckets"].get(partition_id, []))

    def partition_stats(self, table_name: str) -> Dict[str, Any]:
        with self._lock:
            pinfo = self._partitions.get(table_name)
            if pinfo is None:
                raise KeyError(f"No partition config for '{table_name}'")
            return {
                "table_name": table_name,
                "strategy": pinfo["strategy"].name,
                "key_column": pinfo["key_column"],
                "num_partitions": pinfo["num_partitions"],
                "bucket_sizes": {i: len(b) for i, b in pinfo["buckets"].items()},
            }

    @staticmethod
    def _to_timestamp(val: Any) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val).timestamp()
            except ValueError:
                return float(hash(val))
        return float(hash(val))


# ======================================================================
# Tiered Storage
# ======================================================================

class TieredStorageManager:
    """Tiered storage: hot → warm → cold.

    * **Hot** — quantum device / live simulator (lowest latency).
    * **Warm** — simulator cache / in-memory store.
    * **Cold** — classical disk / archive.

    Data migrates between tiers based on access frequency and
    configurable thresholds.
    """

    class Tier(Enum):
        HOT = auto()
        WARM = auto()
        COLD = auto()

    def __init__(
        self,
        hot_capacity: int = 100,
        warm_capacity: int = 1000,
        cold_dir: str = "quantum_cold_store",
        promote_threshold: int = 5,
        demote_seconds: float = 3600,
    ) -> None:
        self._hot: OrderedDict[str, Any] = OrderedDict()
        self._warm: OrderedDict[str, Any] = OrderedDict()
        self._cold_dir = cold_dir
        self._hot_cap = hot_capacity
        self._warm_cap = warm_capacity
        self._access_count: Dict[str, int] = {}
        self._last_access: Dict[str, float] = {}
        self._promote_threshold = promote_threshold
        self._demote_seconds = demote_seconds
        self._lock = threading.RLock()
        os.makedirs(cold_dir, exist_ok=True)

    def put(self, key: str, value: Any, tier: Optional["TieredStorageManager.Tier"] = None) -> None:
        """Store a value in the specified tier (default: WARM)."""
        tier = tier or self.Tier.WARM
        with self._lock:
            self._access_count[key] = self._access_count.get(key, 0)
            self._last_access[key] = time.time()
            if tier == self.Tier.HOT:
                self._put_hot(key, value)
            elif tier == self.Tier.WARM:
                self._put_warm(key, value)
            else:
                self._put_cold(key, value)

    def get(self, key: str) -> Optional[Any]:
        """Retrieve from the highest tier available, auto-promoting."""
        with self._lock:
            self._access_count[key] = self._access_count.get(key, 0) + 1
            self._last_access[key] = time.time()

            if key in self._hot:
                self._hot.move_to_end(key)
                return self._hot[key]
            if key in self._warm:
                self._warm.move_to_end(key)
                if self._access_count[key] >= self._promote_threshold:
                    self._put_hot(key, self._warm.pop(key))
                return self._hot.get(key) or self._warm.get(key)

            cold_path = os.path.join(self._cold_dir, f"{key}.pkl")
            if os.path.exists(cold_path):
                with open(cold_path, "rb") as f:
                    value = pickle.load(f)
                self._put_warm(key, value)
                return value
        return None

    def demote_stale(self) -> int:
        """Demote entries that haven't been accessed recently.

        Returns:
            Number of entries demoted.
        """
        now = time.time()
        demoted = 0
        with self._lock:
            for key in list(self._hot):
                if now - self._last_access.get(key, 0) > self._demote_seconds:
                    self._put_warm(key, self._hot.pop(key))
                    demoted += 1
            for key in list(self._warm):
                if now - self._last_access.get(key, 0) > 2 * self._demote_seconds:
                    self._put_cold(key, self._warm.pop(key))
                    demoted += 1
        if demoted:
            logger.info("Demoted %d stale entries", demoted)
        return demoted

    def tier_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "hot_count": len(self._hot),
                "hot_capacity": self._hot_cap,
                "warm_count": len(self._warm),
                "warm_capacity": self._warm_cap,
                "cold_count": len([
                    f for f in os.listdir(self._cold_dir) if f.endswith(".pkl")
                ]),
            }

    # -- internal ----------------------------------------------------------

    def _put_hot(self, key: str, value: Any) -> None:
        if len(self._hot) >= self._hot_cap:
            evicted_key, evicted_val = self._hot.popitem(last=False)
            self._put_warm(evicted_key, evicted_val)
        self._hot[key] = value

    def _put_warm(self, key: str, value: Any) -> None:
        if len(self._warm) >= self._warm_cap:
            evicted_key, evicted_val = self._warm.popitem(last=False)
            self._put_cold(evicted_key, evicted_val)
        self._warm[key] = value

    def _put_cold(self, key: str, value: Any) -> None:
        path = os.path.join(self._cold_dir, f"{key}.pkl")
        with open(path, "wb") as f:
            pickle.dump(value, f)
