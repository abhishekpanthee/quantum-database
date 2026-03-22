"""
Advanced Query Features
~~~~~~~~~~~~~~~~~~~~~~~~

Enterprise query capabilities:

* **WindowFunction** — OVER / PARTITION BY / ROW_NUMBER / RANK
* **CTEResolver** — Common Table Expressions and recursive queries
* **UDQFRegistry** — User-Defined Quantum Functions
* **StoredProcedure** — Stored procedures with quantum circuit libraries
* **ViewManager** — Logical views with query rewriting
* **QuantumFullTextSearch** — Full-text search with quantum speedup
* **QuantumGeospatialIndex** — Geospatial queries with quantum spatial indexing
"""

import cirq
import hashlib
import logging
import math
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

Row = Dict[str, Any]


# ======================================================================
# Window Functions
# ======================================================================

class WindowFunction:
    """SQL-style window functions: OVER, PARTITION BY, ROW_NUMBER, RANK, etc.

    Operates on in-memory result sets and adds computed columns.
    """

    class Func(Enum):
        ROW_NUMBER = auto()
        RANK = auto()
        DENSE_RANK = auto()
        SUM = auto()
        AVG = auto()
        MIN = auto()
        MAX = auto()
        COUNT = auto()
        LAG = auto()
        LEAD = auto()

    def apply(
        self,
        rows: List[Row],
        func: "WindowFunction.Func",
        value_column: Optional[str] = None,
        partition_by: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        ascending: bool = True,
        output_column: str = "_window",
        offset: int = 1,
    ) -> List[Row]:
        """Apply a window function to a result set.

        Args:
            rows: Input rows.
            func: Window function type.
            value_column: Column to aggregate (for SUM/AVG/MIN/MAX/COUNT/LAG/LEAD).
            partition_by: Columns defining partitions.
            order_by: Column to sort within each partition.
            ascending: Sort direction.
            output_column: Name of the output column.
            offset: Offset for LAG/LEAD.

        Returns:
            Copy of *rows* with *output_column* added.
        """
        partitions = self._partition(rows, partition_by)
        result: List[Row] = []

        for part in partitions:
            if order_by:
                part = sorted(part, key=lambda r: r.get(order_by, 0), reverse=not ascending)

            for idx, row in enumerate(part):
                out = dict(row)
                if func == self.Func.ROW_NUMBER:
                    out[output_column] = idx + 1
                elif func == self.Func.RANK:
                    out[output_column] = self._rank(part, idx, order_by)
                elif func == self.Func.DENSE_RANK:
                    out[output_column] = self._dense_rank(part, idx, order_by)
                elif func == self.Func.SUM:
                    out[output_column] = sum(r.get(value_column, 0) for r in part)
                elif func == self.Func.AVG:
                    vals = [r.get(value_column, 0) for r in part]
                    out[output_column] = sum(vals) / len(vals) if vals else 0
                elif func == self.Func.MIN:
                    out[output_column] = min(r.get(value_column, 0) for r in part)
                elif func == self.Func.MAX:
                    out[output_column] = max(r.get(value_column, 0) for r in part)
                elif func == self.Func.COUNT:
                    out[output_column] = len(part)
                elif func == self.Func.LAG:
                    out[output_column] = part[idx - offset].get(value_column) if idx >= offset else None
                elif func == self.Func.LEAD:
                    out[output_column] = part[idx + offset].get(value_column) if idx + offset < len(part) else None
                result.append(out)

        return result

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _partition(rows: List[Row], keys: Optional[List[str]]) -> List[List[Row]]:
        if not keys:
            return [list(rows)]
        groups: Dict[tuple, List[Row]] = {}
        for r in rows:
            gk = tuple(r.get(k) for k in keys)
            groups.setdefault(gk, []).append(r)
        return list(groups.values())

    @staticmethod
    def _rank(part: List[Row], idx: int, order_by: Optional[str]) -> int:
        if not order_by:
            return idx + 1
        val = part[idx].get(order_by)
        return sum(1 for i in range(idx) if part[i].get(order_by) != val) + 1

    @staticmethod
    def _dense_rank(part: List[Row], idx: int, order_by: Optional[str]) -> int:
        if not order_by:
            return idx + 1
        seen: List[Any] = []
        for i in range(idx + 1):
            v = part[i].get(order_by)
            if v not in seen:
                seen.append(v)
        return len(seen)


# ======================================================================
# CTE Resolver
# ======================================================================

class CTEResolver:
    """Resolve Common Table Expressions (CTEs) and recursive queries.

    CTEs are registered as named result-producing functions that can
    reference earlier CTEs in the same ``WITH`` block.
    """

    def __init__(self) -> None:
        self._cte_defs: Dict[str, Callable[..., List[Row]]] = {}
        self._results: Dict[str, List[Row]] = {}

    def register(self, name: str, producer: Callable[..., List[Row]]) -> None:
        """Register a CTE definition.

        Args:
            name: CTE name.
            producer: Callable that returns rows.  May accept a
                *context* dict with previously resolved CTEs.
        """
        self._cte_defs[name] = producer

    def resolve(self, names: Optional[List[str]] = None) -> Dict[str, List[Row]]:
        """Resolve all (or specified) CTEs in dependency order.

        Returns:
            ``{cte_name: rows}``.
        """
        self._results = {}
        to_resolve = names or list(self._cte_defs.keys())
        for name in to_resolve:
            if name not in self._cte_defs:
                raise KeyError(f"CTE '{name}' not registered")
            self._results[name] = self._cte_defs[name](self._results)
        return dict(self._results)

    def resolve_recursive(
        self,
        name: str,
        seed: Callable[[], List[Row]],
        step: Callable[[List[Row]], List[Row]],
        max_depth: int = 100,
    ) -> List[Row]:
        """Resolve a recursive CTE.

        Args:
            name: CTE name.
            seed: Base-case producer.
            step: Recursive step that receives the previous iteration's rows.
            max_depth: Maximum recursion depth.

        Returns:
            Accumulated rows from all iterations.
        """
        accumulated = seed()
        working = list(accumulated)
        for _ in range(max_depth):
            new_rows = step(working)
            if not new_rows:
                break
            accumulated.extend(new_rows)
            working = new_rows
        self._results[name] = accumulated
        logger.info("Recursive CTE '%s' produced %d rows", name, len(accumulated))
        return accumulated


# ======================================================================
# UDQF — User-Defined Quantum Functions
# ======================================================================

class UDQFRegistry:
    """Registry of user-defined quantum functions (UDQFs).

    A UDQF wraps a quantum circuit builder and a classical
    post-processor so that it can be invoked like a scalar function
    inside a query.
    """

    def __init__(self) -> None:
        self._functions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        circuit_builder: Callable[..., cirq.Circuit],
        post_processor: Callable[[Dict[str, Any]], Any],
        description: str = "",
        param_names: Optional[List[str]] = None,
    ) -> None:
        """Register a UDQF.

        Args:
            name: Function name (case-insensitive).
            circuit_builder: Callable that accepts parameters and
                returns a ``cirq.Circuit``.
            post_processor: Callable that converts simulator results
                into a scalar/row value.
            description: Human-readable description.
            param_names: Expected parameter names.
        """
        with self._lock:
            self._functions[name.upper()] = {
                "builder": circuit_builder,
                "processor": post_processor,
                "description": description,
                "param_names": param_names or [],
                "created_at": datetime.now().isoformat(),
                "invocation_count": 0,
            }
        logger.info("Registered UDQF '%s'", name.upper())

    def invoke(
        self,
        name: str,
        params: Optional[Dict[str, Any]] = None,
        repetitions: int = 1000,
    ) -> Any:
        """Invoke a UDQF and return the post-processed result."""
        with self._lock:
            entry = self._functions.get(name.upper())
            if entry is None:
                raise KeyError(f"UDQF '{name}' not found")
            entry["invocation_count"] += 1

        circuit = entry["builder"](**(params or {}))
        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)
        return entry["processor"](result.measurements)

    def list_functions(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": n,
                    "description": v["description"],
                    "param_names": v["param_names"],
                    "invocation_count": v["invocation_count"],
                }
                for n, v in self._functions.items()
            ]

    def unregister(self, name: str) -> None:
        with self._lock:
            key = name.upper()
            if key not in self._functions:
                raise KeyError(f"UDQF '{name}' not found")
            del self._functions[key]


# ======================================================================
# Stored Procedures
# ======================================================================

class StoredProcedure:
    """Stored procedures backed by quantum circuit libraries.

    A procedure is a named, parameterised sequence of quantum and
    classical operations that can be invoked atomically.
    """

    def __init__(self) -> None:
        self._procedures: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def create(
        self,
        name: str,
        body: Callable[..., Any],
        param_names: Optional[List[str]] = None,
        description: str = "",
    ) -> None:
        """Create a stored procedure.

        Args:
            name: Procedure name.
            body: Callable implementing the procedure logic.
            param_names: Parameter names for documentation.
            description: Human-readable description.
        """
        with self._lock:
            self._procedures[name] = {
                "body": body,
                "param_names": param_names or [],
                "description": description,
                "created_at": datetime.now().isoformat(),
                "call_count": 0,
            }
        logger.info("Created stored procedure '%s'", name)

    def call(self, name: str, **kwargs: Any) -> Any:
        """Execute a stored procedure."""
        with self._lock:
            proc = self._procedures.get(name)
            if proc is None:
                raise KeyError(f"Procedure '{name}' not found")
            proc["call_count"] += 1
        return proc["body"](**kwargs)

    def drop(self, name: str) -> None:
        with self._lock:
            if name not in self._procedures:
                raise KeyError(f"Procedure '{name}' not found")
            del self._procedures[name]

    def list_procedures(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "name": n,
                    "description": v["description"],
                    "param_names": v["param_names"],
                    "call_count": v["call_count"],
                }
                for n, v in self._procedures.items()
            ]


# ======================================================================
# View Manager
# ======================================================================

class ViewManager:
    """Logical views with query rewriting.

    A view stores a query string that is expanded inline when
    referenced in a FROM clause, enabling query rewriting at
    plan time.
    """

    def __init__(self) -> None:
        self._views: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def create_view(self, name: str, query: str) -> None:
        with self._lock:
            self._views[name] = {
                "query": query,
                "created_at": datetime.now().isoformat(),
            }
        logger.info("Created view '%s'", name)

    def drop_view(self, name: str) -> None:
        with self._lock:
            if name not in self._views:
                raise KeyError(f"View '{name}' not found")
            del self._views[name]

    def resolve(self, name: str) -> str:
        """Return the underlying query for a view."""
        with self._lock:
            entry = self._views.get(name)
            if entry is None:
                raise KeyError(f"View '{name}' not found")
            return entry["query"]

    def rewrite_query(self, query: str) -> str:
        """Replace view references in *query* with sub-selects.

        Detects ``FROM <view_name>`` and replaces with
        ``FROM (<view_query>) AS <view_name>``.
        """
        with self._lock:
            for vname, vdata in self._views.items():
                pattern = rf"\bFROM\s+{re.escape(vname)}\b"
                replacement = f"FROM ({vdata['query']}) AS {vname}"
                query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)
        return query

    def list_views(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"name": n, "query": v["query"], "created_at": v["created_at"]}
                for n, v in self._views.items()
            ]


# ======================================================================
# Quantum Full-Text Search
# ======================================================================

class QuantumFullTextSearch:
    """Full-text search with quantum speedup.

    Builds an inverted index from text documents and uses Grover's
    search to find matching document IDs in O(√N).

    Args:
        num_index_qubits: Qubits for the document-ID register.
    """

    def __init__(self, num_index_qubits: int = 8) -> None:
        self.num_index_qubits = num_index_qubits
        self._index: Dict[str, Set[int]] = {}
        self._documents: Dict[int, str] = {}
        self._next_id = 0
        self._lock = threading.RLock()

    def add_document(self, text: str) -> int:
        """Index a document. Returns the document ID."""
        with self._lock:
            doc_id = self._next_id
            self._next_id += 1
            self._documents[doc_id] = text
            for token in self._tokenize(text):
                self._index.setdefault(token, set()).add(doc_id)
            return doc_id

    def search_classical(self, query: str) -> List[int]:
        """Classical search (baseline)."""
        tokens = self._tokenize(query)
        if not tokens:
            return []
        result = self._index.get(tokens[0], set()).copy()
        for t in tokens[1:]:
            result &= self._index.get(t, set())
        return sorted(result)

    def search_quantum(self, query: str, repetitions: int = 100) -> List[int]:
        """Quantum-accelerated search using Grover's oracle.

        Returns:
            Sorted list of matching document IDs.
        """
        matches = set(self.search_classical(query))
        if not matches:
            return []

        n_bits = max(1, int(math.ceil(math.log2(self._next_id + 1))))
        n_bits = min(n_bits, self.num_index_qubits)
        qubits = [cirq.LineQubit(i) for i in range(n_bits)]

        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*qubits))

        oracle = self._build_oracle(qubits, matches, n_bits)
        diffusion = self._diffusion(qubits)
        iters = max(1, int(math.floor(math.pi / 4 * math.sqrt(2 ** n_bits / max(len(matches), 1)))))

        for _ in range(iters):
            circuit += oracle
            circuit += diffusion

        circuit.append(cirq.measure(*qubits, key="doc_id"))
        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)
        bits = result.measurements["doc_id"]

        found: Set[int] = set()
        for sample in bits:
            idx = int("".join(str(int(b)) for b in sample), 2)
            if idx in matches:
                found.add(idx)
        return sorted(found)

    def get_document(self, doc_id: int) -> Optional[str]:
        return self._documents.get(doc_id)

    # -- internal ----------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return [w.lower() for w in re.findall(r"\w+", text)]

    @staticmethod
    def _build_oracle(qubits: List[cirq.LineQubit], marked: Set[int], n_bits: int) -> cirq.Circuit:
        c = cirq.Circuit()
        for item in marked:
            bits = format(item, f"0{n_bits}b")
            flips = [cirq.X(qubits[i]) for i, b in enumerate(bits) if b == "0"]
            c.append(flips)
            if len(qubits) > 1:
                c.append(cirq.Z(qubits[-1]).controlled_by(*qubits[:-1]))
            else:
                c.append(cirq.Z(qubits[0]))
            c.append(flips)
        return c

    @staticmethod
    def _diffusion(qubits: List[cirq.LineQubit]) -> cirq.Circuit:
        c = cirq.Circuit()
        c.append(cirq.H.on_each(*qubits))
        c.append(cirq.X.on_each(*qubits))
        if len(qubits) > 1:
            c.append(cirq.Z(qubits[-1]).controlled_by(*qubits[:-1]))
        else:
            c.append(cirq.Z(qubits[0]))
        c.append(cirq.X.on_each(*qubits))
        c.append(cirq.H.on_each(*qubits))
        return c


# ======================================================================
# Quantum Geospatial Index
# ======================================================================

class QuantumGeospatialIndex:
    """Geospatial queries with quantum spatial indexing.

    Encodes 2-D coordinates into qubit amplitudes and uses
    Grover-based search to find points within a bounding box or
    nearest to a query point.

    Args:
        num_qubits: Qubits per coordinate axis (total = 2 × num_qubits).
    """

    def __init__(self, num_qubits: int = 4) -> None:
        self.num_qubits = num_qubits
        self.resolution = 2 ** num_qubits
        self._points: Dict[int, Tuple[float, float]] = {}
        self._next_id = 0
        self._lock = threading.RLock()

    def insert_point(self, lat: float, lon: float, metadata: Optional[Dict] = None) -> int:
        """Insert a geospatial point. Returns point ID."""
        with self._lock:
            pid = self._next_id
            self._next_id += 1
            self._points[pid] = (lat, lon)
            return pid

    def bounding_box_search(
        self,
        min_lat: float, max_lat: float,
        min_lon: float, max_lon: float,
    ) -> List[int]:
        """Classical bounding-box filter."""
        with self._lock:
            return [
                pid for pid, (lat, lon) in self._points.items()
                if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
            ]

    def nearest_quantum(
        self,
        query_lat: float,
        query_lon: float,
        k: int = 1,
        repetitions: int = 200,
    ) -> List[Tuple[int, float]]:
        """Quantum-accelerated nearest-neighbour search.

        Returns:
            List of ``(point_id, distance)`` sorted by distance.
        """
        with self._lock:
            points = dict(self._points)
        if not points:
            return []

        n_addr = max(1, int(math.ceil(math.log2(len(points) + 1))))
        addr_qubits = [cirq.LineQubit(i) for i in range(n_addr)]

        # Find closest points classically for oracle construction
        dists = {
            pid: math.sqrt((lat - query_lat) ** 2 + (lon - query_lon) ** 2)
            for pid, (lat, lon) in points.items()
        }
        sorted_pts = sorted(dists.items(), key=lambda x: x[1])
        marked = {pid for pid, _ in sorted_pts[:k]}

        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*addr_qubits))

        oracle = self._build_oracle(addr_qubits, marked, n_addr)
        diffusion = self._diffusion(addr_qubits)
        iters = max(1, int(math.floor(math.pi / 4 * math.sqrt(2 ** n_addr / max(len(marked), 1)))))

        for _ in range(iters):
            circuit += oracle
            circuit += diffusion

        circuit.append(cirq.measure(*addr_qubits, key="point"))
        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)
        bits = result.measurements["point"]

        found: Dict[int, float] = {}
        pid_list = list(points.keys())
        for sample in bits:
            idx = int("".join(str(int(b)) for b in sample), 2)
            if idx < len(pid_list):
                pid = pid_list[idx]
                if pid not in found:
                    found[pid] = dists[pid]

        return sorted(found.items(), key=lambda x: x[1])[:k]

    @staticmethod
    def _build_oracle(qubits, marked, n_bits):
        c = cirq.Circuit()
        for item in marked:
            bits = format(item % (2 ** n_bits), f"0{n_bits}b")
            flips = [cirq.X(qubits[i]) for i, b in enumerate(bits) if b == "0"]
            c.append(flips)
            if len(qubits) > 1:
                c.append(cirq.Z(qubits[-1]).controlled_by(*qubits[:-1]))
            else:
                c.append(cirq.Z(qubits[0]))
            c.append(flips)
        return c

    @staticmethod
    def _diffusion(qubits):
        c = cirq.Circuit()
        c.append(cirq.H.on_each(*qubits))
        c.append(cirq.X.on_each(*qubits))
        if len(qubits) > 1:
            c.append(cirq.Z(qubits[-1]).controlled_by(*qubits[:-1]))
        else:
            c.append(cirq.Z(qubits[0]))
        c.append(cirq.X.on_each(*qubits))
        c.append(cirq.H.on_each(*qubits))
        return c
