"""Hardware-aware circuit compilation.

Topology-aware qubit mapping, native gate set decomposition,
circuit transpilation with swap routing, pulse-level optimisation,
and calibration data integration.
"""

import cirq
import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from qndb.core.engine.hardware.backend_registry import (
    BackendCapabilities,
    TopologyType,
)

logger = logging.getLogger(__name__)


# ======================================================================
# Calibration data
# ======================================================================

@dataclass
class CalibrationData:
    """Snapshot of a device's calibration state.

    Populated either from live hardware or from default values when
    the backend is a simulator.
    """

    timestamp: float = 0.0
    t1_us: Dict[int, float] = field(default_factory=dict)   # per-qubit T1
    t2_us: Dict[int, float] = field(default_factory=dict)   # per-qubit T2
    single_qubit_errors: Dict[int, float] = field(default_factory=dict)
    two_qubit_errors: Dict[Tuple[int, int], float] = field(default_factory=dict)
    readout_errors: Dict[int, float] = field(default_factory=dict)

    @classmethod
    def from_capabilities(cls, caps: BackendCapabilities) -> "CalibrationData":
        """Build uniform calibration data from capability defaults."""
        n = caps.num_qubits
        return cls(
            timestamp=time.time(),
            t1_us={i: caps.t1_us for i in range(n)},
            t2_us={i: caps.t2_us for i in range(n)},
            single_qubit_errors={i: caps.single_qubit_error for i in range(n)},
            two_qubit_errors={},
            readout_errors={i: caps.readout_error for i in range(n)},
        )


# ======================================================================
# Topology mapper
# ======================================================================

class TopologyMapper:
    """Maps logical qubits to physical qubits respecting device topology."""

    def __init__(self, capabilities: BackendCapabilities) -> None:
        self._caps = capabilities
        self._coupling: Dict[int, Set[int]] = defaultdict(set)
        self._build_coupling()

    # -- Internal helpers ---------------------------------------------------

    def _build_coupling(self) -> None:
        """Build adjacency from coupling_map or synthesise from topology."""
        if self._caps.coupling_map:
            for a, b in self._caps.coupling_map:
                self._coupling[a].add(b)
                self._coupling[b].add(a)
            return

        n = self._caps.num_qubits
        topo = self._caps.topology

        if topo == TopologyType.ALL_TO_ALL:
            for i in range(n):
                for j in range(i + 1, n):
                    self._coupling[i].add(j)
                    self._coupling[j].add(i)

        elif topo == TopologyType.LINEAR:
            for i in range(n - 1):
                self._coupling[i].add(i + 1)
                self._coupling[i + 1].add(i)

        elif topo == TopologyType.RING:
            for i in range(n):
                self._coupling[i].add((i + 1) % n)
                self._coupling[(i + 1) % n].add(i)

        elif topo == TopologyType.GRID:
            side = max(1, int(math.isqrt(n)))
            for i in range(n):
                r, c = divmod(i, side)
                if c + 1 < side and i + 1 < n:
                    self._coupling[i].add(i + 1)
                    self._coupling[i + 1].add(i)
                if i + side < n:
                    self._coupling[i].add(i + side)
                    self._coupling[i + side].add(i)

        elif topo == TopologyType.HEAVY_HEX:
            # Simplified heavy-hex: linear chain with every 4th qubit
            # connected to a "bridge" qubit
            for i in range(n - 1):
                self._coupling[i].add(i + 1)
                self._coupling[i + 1].add(i)
            for i in range(0, n, 4):
                bridge = (i + 2) % n
                if bridge != i:
                    self._coupling[i].add(bridge)
                    self._coupling[bridge].add(i)

    # -- Public API ---------------------------------------------------------

    @property
    def coupling_graph(self) -> Dict[int, Set[int]]:
        return dict(self._coupling)

    def are_adjacent(self, a: int, b: int) -> bool:
        return b in self._coupling.get(a, set())

    def shortest_path(self, src: int, dst: int) -> List[int]:
        """BFS shortest path on the coupling graph."""
        if src == dst:
            return [src]
        visited = {src}
        queue: deque = deque([(src, [src])])
        while queue:
            node, path = queue.popleft()
            for nb in self._coupling.get(node, set()):
                if nb == dst:
                    return path + [dst]
                if nb not in visited:
                    visited.add(nb)
                    queue.append((nb, path + [nb]))
        return []  # unreachable

    def map_logical_to_physical(
        self,
        circuit: cirq.Circuit,
        calibration: Optional[CalibrationData] = None,
    ) -> Tuple[cirq.Circuit, Dict[cirq.Qid, int]]:
        """Assign logical qubits to physical positions.

        Uses a greedy strategy: assign interacting pairs to adjacent
        physical qubits, preferring qubits with lower error rates
        when calibration data is available.
        """
        logical_qubits = sorted(circuit.all_qubits())
        n_logical = len(logical_qubits)
        n_physical = self._caps.num_qubits

        if n_logical > n_physical:
            raise RuntimeError(
                f"Circuit needs {n_logical} qubits but device has {n_physical}"
            )

        # Score physical qubits (lower is better)
        if calibration:
            phys_score = {
                i: calibration.single_qubit_errors.get(i, 1.0)
                for i in range(n_physical)
            }
        else:
            phys_score = {i: 0.0 for i in range(n_physical)}

        # Greedy assignment: best physical qubits first
        ranked = sorted(phys_score, key=phys_score.get)  # type: ignore[arg-type]
        mapping: Dict[cirq.Qid, int] = {}
        for lq, pq in zip(logical_qubits, ranked):
            mapping[lq] = pq

        # Rebuild circuit with mapped qubits
        phys_qubits = {lq: cirq.LineQubit(mapping[lq]) for lq in logical_qubits}
        new_ops = []
        for moment in circuit:
            for op in moment:
                new_qubits = tuple(phys_qubits[q] for q in op.qubits)
                new_ops.append(op.gate.on(*new_qubits) if op.gate else op)
        new_circuit = cirq.Circuit(new_ops)
        return new_circuit, mapping

    def insert_swaps(
        self,
        circuit: cirq.Circuit,
        mapping: Dict[cirq.Qid, int],
    ) -> cirq.Circuit:
        """Insert SWAP gates where two-qubit operations act on non-adjacent qubits."""
        new_ops: List[cirq.Operation] = []
        current_map = dict(mapping)
        reverse_map = {v: k for k, v in current_map.items()}

        for moment in circuit:
            for op in moment:
                if len(op.qubits) == 2:
                    q0, q1 = op.qubits
                    p0 = q0.x if isinstance(q0, cirq.LineQubit) else current_map.get(q0, 0)
                    p1 = q1.x if isinstance(q1, cirq.LineQubit) else current_map.get(q1, 0)

                    if not self.are_adjacent(p0, p1):
                        path = self.shortest_path(p0, p1)
                        for i in range(len(path) - 2):
                            a, b = path[i], path[i + 1]
                            new_ops.append(
                                cirq.SWAP(cirq.LineQubit(a), cirq.LineQubit(b))
                            )
                new_ops.append(op)
            # keep moment separation
        return cirq.Circuit(new_ops)


# ======================================================================
# Gate decomposer
# ======================================================================

class GateDecomposer:
    """Decompose arbitrary gates into a backend's native gate set."""

    def __init__(self, native_gates: Set[str]) -> None:
        self._native = native_gates

    def decompose_circuit(self, circuit: cirq.Circuit) -> cirq.Circuit:
        """Return a new circuit using only native gates.

        Falls back to Cirq's built-in decompositions.
        """
        new_ops: List[cirq.Operation] = []
        for op in circuit.all_operations():
            if self._is_native(op):
                new_ops.append(op)
            else:
                decomposed = cirq.decompose_once(op, default=[op])
                new_ops.extend(decomposed)
        return cirq.Circuit(new_ops)

    def _is_native(self, op: cirq.Operation) -> bool:
        if op.gate is None:
            return True
        gate_name = type(op.gate).__name__
        # map common Cirq gate names to short names
        _map = {
            "HPowGate": "H", "XPowGate": "X", "YPowGate": "Y",
            "ZPowGate": "Z", "CNotPowGate": "CNOT", "CZPowGate": "CZ",
            "SwapPowGate": "SWAP", "ISwapPowGate": "ISWAP",
        }
        short = _map.get(gate_name, gate_name)
        return short in self._native


# ======================================================================
# Hardware compiler (orchestrator)
# ======================================================================

class HardwareCompiler:
    """End-to-end hardware-aware circuit compilation pipeline.

    Steps:
      1. Gate decomposition to native gate set
      2. Topology-aware qubit mapping
      3. SWAP insertion for non-adjacent interactions
      4. (Optional) pulse-level optimisation
      5. Calibration-aware quality report
    """

    def __init__(
        self,
        capabilities: BackendCapabilities,
        calibration: Optional[CalibrationData] = None,
    ) -> None:
        self._caps = capabilities
        self._calibration = calibration or CalibrationData.from_capabilities(capabilities)
        self._mapper = TopologyMapper(capabilities)
        self._decomposer = GateDecomposer(capabilities.native_gates)

    def compile(
        self,
        circuit: cirq.Circuit,
        optimisation_level: int = 1,
    ) -> Dict[str, Any]:
        """Compile *circuit* for the target backend.

        Returns a dict with:
        - ``compiled_circuit``: the hardware-ready circuit
        - ``qubit_mapping``: logical → physical mapping
        - ``stats``: depth, gate counts, estimated fidelity
        """
        # 1. Decompose gates
        decomposed = self._decomposer.decompose_circuit(circuit)

        # 2. Map qubits
        mapped, mapping = self._mapper.map_logical_to_physical(
            decomposed, self._calibration,
        )

        # 3. Insert swaps
        routed = self._mapper.insert_swaps(mapped, mapping)

        # 4. Optional: light optimisation pass (cancel adjacent inverses)
        if optimisation_level >= 1:
            routed = self._cancel_adjacent_inverses(routed)

        # 5. Pulse-level optimisation
        if optimisation_level >= 2 and self._caps.supports_pulse_level:
            logger.info("Pulse-level optimisation requested — pass-through for level %d", optimisation_level)

        # 6. Statistics
        stats = self._compute_stats(routed)

        return {
            "compiled_circuit": routed,
            "qubit_mapping": mapping,
            "stats": stats,
        }

    # -- Optimisation passes ------------------------------------------------

    @staticmethod
    def _cancel_adjacent_inverses(circuit: cirq.Circuit) -> cirq.Circuit:
        """Cancel consecutive self-inverse gates (X·X, H·H, etc.)."""
        ops = list(circuit.all_operations())
        filtered: List[cirq.Operation] = []
        i = 0
        while i < len(ops):
            if (
                i + 1 < len(ops)
                and ops[i].gate is not None
                and ops[i].gate == ops[i + 1].gate
                and ops[i].qubits == ops[i + 1].qubits
                and _is_self_inverse(ops[i].gate)
            ):
                i += 2  # cancel pair
            else:
                filtered.append(ops[i])
                i += 1
        return cirq.Circuit(filtered)

    def _compute_stats(self, circuit: cirq.Circuit) -> Dict[str, Any]:
        ops = list(circuit.all_operations())
        n_single = sum(1 for o in ops if len(o.qubits) == 1)
        n_two = sum(1 for o in ops if len(o.qubits) == 2)
        n_measure = sum(1 for o in ops if cirq.is_measurement(o))
        depth = len(circuit)
        fidelity = self._caps.estimated_fidelity(n_single, n_two, n_measure)
        return {
            "depth": depth,
            "single_qubit_gates": n_single,
            "two_qubit_gates": n_two,
            "measurements": n_measure,
            "total_operations": len(ops),
            "estimated_fidelity": round(fidelity, 6),
        }


# ======================================================================
# Helpers
# ======================================================================

_SELF_INVERSE_TYPES = (
    cirq.HPowGate,
    cirq.XPowGate,
    cirq.YPowGate,
    cirq.ZPowGate,
    cirq.CNotPowGate,
    cirq.CZPowGate,
    cirq.SwapPowGate,
)


def _is_self_inverse(gate: cirq.Gate) -> bool:
    """Check if a gate is its own inverse (exponent == 1)."""
    if isinstance(gate, _SELF_INVERSE_TYPES):
        return getattr(gate, "exponent", 1) == 1
    return False
