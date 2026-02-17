"""
Scalable Architecture (9.2)
~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **LogicalQubitManager** — Manage 10,000+ logical qubits across zones
* **MultiZoneProcessor** — Multi-zone quantum processor routing and scheduling
* **QuantumMemoryBank** — Long-lived qubit storage with coherence tracking
* **ModularQPUConnector** — Connect multiple QPUs into a unified fabric
* **PetabyteQuantumIndex** — Petabyte-scale data with quantum-accelerated indexing
"""

import cirq
import hashlib
import logging
import math
import threading
import time
import uuid
from collections import OrderedDict
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ======================================================================
#  Logical Qubit Manager (10,000+ logical qubits)
# ======================================================================

class LogicalQubitManager:
    """Registry and allocator for large-scale logical qubit pools.

    Tracks allocation state, coherence windows, and zone placement for
    up to tens of thousands of logical qubits.
    """

    class State(Enum):
        FREE = auto()
        ALLOCATED = auto()
        RESERVED = auto()
        ERROR = auto()

    def __init__(self, capacity: int = 10_000):
        self._capacity = capacity
        self._qubits: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        logger.info("LogicalQubitManager ready (capacity=%d)", capacity)

    def allocate(
        self,
        count: int = 1,
        zone: Optional[str] = None,
        label_prefix: str = "lq",
    ) -> List[str]:
        """Allocate *count* logical qubits.

        Returns:
            List of assigned logical-qubit IDs.

        Raises:
            RuntimeError: If capacity would be exceeded.
        """
        with self._lock:
            current_alloc = sum(
                1 for q in self._qubits.values()
                if q["state"] != self.State.FREE
            )
            if current_alloc + count > self._capacity:
                raise RuntimeError(
                    f"Cannot allocate {count}: would exceed capacity "
                    f"({current_alloc}/{self._capacity})"
                )
            ids: List[str] = []
            for i in range(count):
                qid = f"{label_prefix}_{uuid.uuid4().hex[:8]}"
                self._qubits[qid] = {
                    "state": self.State.ALLOCATED,
                    "zone": zone,
                    "allocated_at": time.time(),
                    "coherence_deadline": time.time() + 1.0,
                    "error_count": 0,
                }
                ids.append(qid)
            logger.debug("Allocated %d logical qubits in zone=%s", count, zone)
            return ids

    def release(self, qubit_ids: List[str]) -> int:
        """Release allocated logical qubits back to the free pool."""
        released = 0
        with self._lock:
            for qid in qubit_ids:
                if qid in self._qubits:
                    self._qubits[qid]["state"] = self.State.FREE
                    released += 1
        return released

    def mark_error(self, qubit_id: str, reason: str = "") -> None:
        with self._lock:
            q = self._qubits.get(qubit_id)
            if q is None:
                raise KeyError(qubit_id)
            q["state"] = self.State.ERROR
            q["error_count"] += 1
            logger.warning("Qubit %s marked ERROR: %s", qubit_id, reason)

    def reclaim_expired(self) -> int:
        """Reclaim qubits that have exceeded their coherence deadline."""
        reclaimed = 0
        now = time.time()
        with self._lock:
            for qid, q in self._qubits.items():
                if q["state"] == self.State.ALLOCATED and now > q["coherence_deadline"]:
                    q["state"] = self.State.FREE
                    reclaimed += 1
        return reclaimed

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            states = {}
            for q in self._qubits.values():
                name = q["state"].name
                states[name] = states.get(name, 0) + 1
            return {
                "capacity": self._capacity,
                "total_tracked": len(self._qubits),
                "by_state": states,
            }


# ======================================================================
#  Multi-Zone Processor
# ======================================================================

class MultiZoneProcessor:
    """Routes operations across multiple QPU zones.

    Each *zone* represents an independent quantum processing region with
    its own qubit pool.  The processor handles inter-zone communication
    via entanglement links.
    """

    def __init__(self):
        self._zones: Dict[str, Dict[str, Any]] = {}
        self._links: List[Tuple[str, str, float]] = []  # (zone_a, zone_b, fidelity)
        self._lock = threading.RLock()

    def add_zone(
        self,
        zone_id: str,
        qubit_capacity: int = 100,
        gate_set: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if zone_id in self._zones:
                raise ValueError(f"Zone '{zone_id}' already exists")
            zone = {
                "zone_id": zone_id,
                "qubit_capacity": qubit_capacity,
                "gate_set": gate_set or ["H", "CNOT", "T", "S", "X", "Z"],
                "allocated": 0,
                "circuits_run": 0,
                "created_at": time.time(),
            }
            self._zones[zone_id] = zone
            logger.debug("Added zone '%s' (capacity=%d)", zone_id, qubit_capacity)
            return zone

    def remove_zone(self, zone_id: str) -> None:
        with self._lock:
            if zone_id not in self._zones:
                raise KeyError(zone_id)
            del self._zones[zone_id]
            self._links = [(a, b, f) for a, b, f in self._links if a != zone_id and b != zone_id]

    def add_link(self, zone_a: str, zone_b: str, fidelity: float = 0.99) -> None:
        """Register an entanglement link between two zones."""
        with self._lock:
            for a, b, _ in self._links:
                if {a, b} == {zone_a, zone_b}:
                    raise ValueError("Link already exists")
            self._links.append((zone_a, zone_b, fidelity))

    def route_circuit(
        self,
        circuit: cirq.Circuit,
        preferred_zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Select the best zone for a circuit and track execution."""
        with self._lock:
            if not self._zones:
                raise RuntimeError("No zones available")
            n_qubits = len(circuit.all_qubits())

            if preferred_zone and preferred_zone in self._zones:
                zone = self._zones[preferred_zone]
                if zone["allocated"] + n_qubits <= zone["qubit_capacity"]:
                    zone["allocated"] += n_qubits
                    zone["circuits_run"] += 1
                    return {"zone": preferred_zone, "qubits_used": n_qubits}

            # Best-fit: zone with smallest remaining capacity that fits
            best = None
            best_remaining = float("inf")
            for zid, z in self._zones.items():
                remaining = z["qubit_capacity"] - z["allocated"]
                if remaining >= n_qubits and remaining < best_remaining:
                    best = zid
                    best_remaining = remaining
            if best is None:
                raise RuntimeError("No zone with sufficient capacity")
            self._zones[best]["allocated"] += n_qubits
            self._zones[best]["circuits_run"] += 1
            return {"zone": best, "qubits_used": n_qubits}

    def release_zone_qubits(self, zone_id: str, count: int) -> None:
        with self._lock:
            z = self._zones.get(zone_id)
            if z is None:
                raise KeyError(zone_id)
            z["allocated"] = max(0, z["allocated"] - count)

    def inter_zone_circuit(
        self,
        zone_a: str,
        zone_b: str,
        num_pairs: int = 1,
    ) -> cirq.Circuit:
        """Build an inter-zone entanglement circuit (Bell pairs)."""
        link_fidelity = None
        for a, b, f in self._links:
            if {a, b} == {zone_a, zone_b}:
                link_fidelity = f
                break
        if link_fidelity is None:
            raise ValueError(f"No link between '{zone_a}' and '{zone_b}'")

        circuit = cirq.Circuit()
        for i in range(num_pairs):
            qa = cirq.NamedQubit(f"{zone_a}_q{i}")
            qb = cirq.NamedQubit(f"{zone_b}_q{i}")
            circuit.append(cirq.H(qa))
            circuit.append(cirq.CNOT(qa, qb))
        circuit.append(
            cirq.measure(
                *[cirq.NamedQubit(f"{zone_a}_q{i}") for i in range(num_pairs)],
                key="inter_zone_bell",
            )
        )
        return circuit

    def zone_stats(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "zone_id": z["zone_id"],
                    "capacity": z["qubit_capacity"],
                    "allocated": z["allocated"],
                    "utilisation": z["allocated"] / max(z["qubit_capacity"], 1),
                    "circuits_run": z["circuits_run"],
                }
                for z in self._zones.values()
            ]

    def list_links(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{"a": a, "b": b, "fidelity": f} for a, b, f in self._links]


# ======================================================================
#  Quantum Memory Bank
# ======================================================================

class QuantumMemoryBank:
    """Long-lived qubit storage with coherence tracking and refresh.

    Each memory slot holds a state vector (amplitude list) and tracks its
    coherence half-life.  Slots whose fidelity drops below a threshold
    are automatically flagged for refresh.
    """

    def __init__(
        self,
        num_slots: int = 256,
        t1_microseconds: float = 1e6,
        t2_microseconds: float = 5e5,
    ):
        self._num_slots = num_slots
        self._t1 = t1_microseconds
        self._t2 = t2_microseconds
        self._slots: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        logger.info("QuantumMemoryBank ready (%d slots, T1=%.0f µs)", num_slots, t1_microseconds)

    def store(self, slot: int, amplitudes: np.ndarray, label: str = "") -> None:
        """Write a state vector into a memory slot."""
        if slot < 0 or slot >= self._num_slots:
            raise ValueError(f"Slot {slot} out of range [0, {self._num_slots})")
        with self._lock:
            self._slots[slot] = {
                "amplitudes": np.array(amplitudes, dtype=complex),
                "label": label,
                "stored_at": time.time(),
                "refresh_count": 0,
            }

    def load(self, slot: int) -> Optional[np.ndarray]:
        """Read a state vector.  Returns ``None`` if slot is empty."""
        with self._lock:
            entry = self._slots.get(slot)
            if entry is None:
                return None
            return entry["amplitudes"].copy()

    def fidelity(self, slot: int) -> float:
        """Estimated fidelity based on T2 decoherence since storage time."""
        with self._lock:
            entry = self._slots.get(slot)
            if entry is None:
                return 0.0
            elapsed = time.time() - entry["stored_at"]
            elapsed_us = elapsed * 1e6
            f = math.exp(-elapsed_us / self._t2)
            return max(0.0, min(1.0, f))

    def refresh(self, slot: int) -> float:
        """Refresh a slot to restore coherence.  Returns new fidelity."""
        with self._lock:
            entry = self._slots.get(slot)
            if entry is None:
                raise KeyError(f"Slot {slot} is empty")
            entry["stored_at"] = time.time()
            entry["refresh_count"] += 1
            return 1.0

    def evict(self, slot: int) -> None:
        with self._lock:
            self._slots.pop(slot, None)

    def slots_needing_refresh(self, threshold: float = 0.9) -> List[int]:
        results: List[int] = []
        with self._lock:
            for slot in self._slots:
                if self.fidelity(slot) < threshold:
                    results.append(slot)
        return results

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            occupied = len(self._slots)
            fidelities = [self.fidelity(s) for s in self._slots]
            return {
                "total_slots": self._num_slots,
                "occupied": occupied,
                "avg_fidelity": float(np.mean(fidelities)) if fidelities else 1.0,
                "min_fidelity": float(np.min(fidelities)) if fidelities else 1.0,
            }


# ======================================================================
#  Modular QPU Connector
# ======================================================================

class ModularQPUConnector:
    """Interconnects multiple QPU modules into a unified computing fabric.

    Each module exposes a qubit count and a set of native gates.  The
    connector handles qubit mapping and inter-module entanglement.
    """

    def __init__(self):
        self._modules: Dict[str, Dict[str, Any]] = {}
        self._connections: List[Tuple[str, str, float]] = []
        self._lock = threading.RLock()

    def register_module(
        self,
        module_id: str,
        num_qubits: int,
        native_gates: Optional[List[str]] = None,
    ) -> None:
        with self._lock:
            if module_id in self._modules:
                raise ValueError(f"Module '{module_id}' already registered")
            self._modules[module_id] = {
                "num_qubits": num_qubits,
                "native_gates": native_gates or ["H", "CNOT", "T"],
                "circuits_executed": 0,
                "registered_at": time.time(),
            }
            logger.debug("Registered QPU module '%s' (%d qubits)", module_id, num_qubits)

    def deregister_module(self, module_id: str) -> None:
        with self._lock:
            if module_id not in self._modules:
                raise KeyError(module_id)
            del self._modules[module_id]
            self._connections = [
                (a, b, f) for a, b, f in self._connections
                if a != module_id and b != module_id
            ]

    def connect_modules(
        self,
        mod_a: str,
        mod_b: str,
        fidelity: float = 0.98,
    ) -> None:
        """Establish an entanglement channel between two modules."""
        with self._lock:
            if mod_a not in self._modules or mod_b not in self._modules:
                raise KeyError("One or both modules not registered")
            self._connections.append((mod_a, mod_b, fidelity))

    def build_cross_module_bell(self, mod_a: str, mod_b: str) -> cirq.Circuit:
        """Create a Bell-pair circuit between two QPU modules."""
        connected = any(
            {a, b} == {mod_a, mod_b} for a, b, _ in self._connections
        )
        if not connected:
            raise ValueError(f"Modules '{mod_a}' and '{mod_b}' are not connected")
        qa = cirq.NamedQubit(f"{mod_a}_link")
        qb = cirq.NamedQubit(f"{mod_b}_link")
        circuit = cirq.Circuit()
        circuit.append(cirq.H(qa))
        circuit.append(cirq.CNOT(qa, qb))
        circuit.append(cirq.measure(qa, qb, key="cross_module_bell"))
        return circuit

    def aggregate_capacity(self) -> Dict[str, Any]:
        with self._lock:
            total = sum(m["num_qubits"] for m in self._modules.values())
            return {
                "module_count": len(self._modules),
                "total_qubits": total,
                "connections": len(self._connections),
            }

    def route_to_module(self, required_qubits: int) -> str:
        """Find the best module for the given qubit requirement."""
        with self._lock:
            best = None
            best_size = float("inf")
            for mid, m in self._modules.items():
                if m["num_qubits"] >= required_qubits and m["num_qubits"] < best_size:
                    best = mid
                    best_size = m["num_qubits"]
            if best is None:
                raise RuntimeError(f"No module with >= {required_qubits} qubits")
            self._modules[best]["circuits_executed"] += 1
            return best


# ======================================================================
#  Petabyte Quantum Index
# ======================================================================

class PetabyteQuantumIndex:
    """Quantum-accelerated index for petabyte-scale datasets.

    Uses quantum hashing and amplitude-encoded index lookups to achieve
    sub-linear search over massive key spaces.
    """

    def __init__(self, num_index_qubits: int = 20):
        self._n = num_index_qubits
        self._index: Dict[str, Any] = OrderedDict()
        self._lock = threading.RLock()
        logger.info("PetabyteQuantumIndex ready (index_qubits=%d)", num_index_qubits)

    def insert(self, key: str, value: Any) -> int:
        """Insert a key-value pair.  Returns the quantum hash bucket."""
        bucket = self._quantum_hash(key)
        with self._lock:
            self._index[key] = {"value": value, "bucket": bucket, "inserted_at": time.time()}
        return bucket

    def lookup(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._index.get(key)
            return entry["value"] if entry else None

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._index.pop(key, None) is not None

    def range_scan(self, prefix: str, limit: int = 100) -> List[Tuple[str, Any]]:
        """Classical prefix scan (fallback for non-quantum workloads)."""
        results: List[Tuple[str, Any]] = []
        with self._lock:
            for k, v in self._index.items():
                if k.startswith(prefix):
                    results.append((k, v["value"]))
                    if len(results) >= limit:
                        break
        return results

    def quantum_search_circuit(self, target_key: str) -> cirq.Circuit:
        """Build a Grover circuit that amplifies the target bucket.

        The caller can run this on real hardware for quadratic speedup.
        """
        bucket = self._quantum_hash(target_key)
        n = min(self._n, 14)  # cap for simulator practicality
        qubits = [cirq.LineQubit(i) for i in range(n)]
        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*qubits))

        oracle = self._build_oracle(qubits, bucket, n)
        diffusion = self._diffusion(qubits)
        iters = max(1, int(math.floor(math.pi / 4 * math.sqrt(2 ** n))))
        for _ in range(iters):
            circuit += oracle
            circuit += diffusion

        circuit.append(cirq.measure(*qubits, key="index_search"))
        return circuit

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_keys": len(self._index),
                "index_qubits": self._n,
                "addressable_space": 2 ** self._n,
            }

    # -- internal ----------------------------------------------------------

    def _quantum_hash(self, key: str) -> int:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return int(digest, 16) % (2 ** self._n)

    @staticmethod
    def _build_oracle(
        qubits: List[cirq.LineQubit],
        target: int,
        n: int,
    ) -> cirq.Circuit:
        c = cirq.Circuit()
        bits = format(target, f"0{n}b")
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
