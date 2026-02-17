"""
Fault-Tolerant Operations (9.1)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **SurfaceCodeStorageLayer** — Surface code integration at the storage layer
* **LogicalQubit** — Logical qubit abstraction over error-corrected physical qubits
* **MagicStateDistillery** — Magic state distillation for non-Clifford T gates
* **LatticeSurgeryEngine** — Lattice surgery operations for logical CNOT
* **ErrorBudgetTracker** — Per-query error budget tracking with automatic allocation
"""

import cirq
import logging
import math
import threading
import time
import uuid
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ======================================================================
#  Surface Code Storage Layer
# ======================================================================

class SurfaceCodeStorageLayer:
    """Wraps raw data qubits with surface code error correction.

    Maintains a registry of *patches* — rectangular arrays of
    ``cirq.GridQubit`` that encode one logical qubit each using a
    rotated surface code of distance *d*.
    """

    def __init__(self, code_distance: int = 3):
        if code_distance < 3 or code_distance % 2 == 0:
            raise ValueError("code_distance must be an odd integer >= 3")
        self._d = code_distance
        self._patches: Dict[str, Dict[str, Any]] = {}
        self._next_row_offset = 0
        self._lock = threading.RLock()
        logger.info("SurfaceCodeStorageLayer initialised (d=%d)", self._d)

    # -- patch management --------------------------------------------------

    def create_patch(self, name: str) -> Dict[str, Any]:
        """Allocate a rotated surface-code patch for one logical qubit.

        Returns:
            Dict with ``data_qubits``, ``x_ancillas``, ``z_ancillas``,
            ``syndrome_circuit``, ``code_distance``.
        """
        with self._lock:
            if name in self._patches:
                raise ValueError(f"Patch '{name}' already exists")

            d = self._d
            row_off = self._next_row_offset
            self._next_row_offset += 2 * d  # reserve space for data + ancilla rows
            data_qubits: List[cirq.GridQubit] = []
            x_ancillas: List[cirq.GridQubit] = []
            z_ancillas: List[cirq.GridQubit] = []

            for r in range(d):
                for c in range(d):
                    data_qubits.append(cirq.GridQubit(row_off + r, c))

            for r in range(d - 1):
                for c in range(d - 1):
                    if (r + c) % 2 == 0:
                        x_ancillas.append(cirq.GridQubit(row_off + r + d, c))
                    else:
                        z_ancillas.append(cirq.GridQubit(row_off + r + d, c))

            syndrome_circuit = self._build_syndrome_circuit(
                data_qubits, x_ancillas, z_ancillas, d,
            )

            patch = {
                "name": name,
                "code_distance": d,
                "data_qubits": data_qubits,
                "x_ancillas": x_ancillas,
                "z_ancillas": z_ancillas,
                "syndrome_circuit": syndrome_circuit,
                "created_at": time.time(),
            }
            self._patches[name] = patch
            logger.debug("Created surface-code patch '%s'", name)
            return patch

    def delete_patch(self, name: str) -> None:
        with self._lock:
            if name not in self._patches:
                raise KeyError(name)
            del self._patches[name]

    def get_patch(self, name: str) -> Dict[str, Any]:
        with self._lock:
            if name not in self._patches:
                raise KeyError(name)
            return dict(self._patches[name])

    def list_patches(self) -> List[str]:
        with self._lock:
            return list(self._patches.keys())

    def encode_logical_zero(self, name: str) -> cirq.Circuit:
        """Return a circuit that prepares |0_L> on the patch."""
        patch = self.get_patch(name)
        data = patch["data_qubits"]
        circuit = cirq.Circuit()
        # Logical |0> of the surface code — all data qubits in |0>
        # followed by one round of syndrome extraction to project.
        circuit += patch["syndrome_circuit"]
        return circuit

    def encode_logical_plus(self, name: str) -> cirq.Circuit:
        """Return a circuit that prepares |+_L> on the patch."""
        patch = self.get_patch(name)
        data = patch["data_qubits"]
        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*data))
        circuit += patch["syndrome_circuit"]
        return circuit

    def run_syndrome_round(self, name: str) -> cirq.Circuit:
        """Return a single syndrome-extraction round for the named patch."""
        return self.get_patch(name)["syndrome_circuit"]

    def decode_syndrome(
        self,
        syndrome_bits: List[int],
        stabiliser_type: str = "X",
    ) -> List[Tuple[int, str]]:
        """Greedy minimum-weight perfect matching decoder.

        Args:
            syndrome_bits: Binary syndrome vector.
            stabiliser_type: ``'X'`` or ``'Z'``.

        Returns:
            List of ``(qubit_index, correction_type)`` pairs.
        """
        corrections: List[Tuple[int, str]] = []
        defects = [i for i, b in enumerate(syndrome_bits) if b]
        while len(defects) >= 2:
            a, b = defects.pop(0), defects.pop(0)
            correction = "Z" if stabiliser_type == "X" else "X"
            for idx in range(a, b + 1):
                corrections.append((idx, correction))
        return corrections

    # -- internal ----------------------------------------------------------

    @staticmethod
    def _build_syndrome_circuit(
        data: List[cirq.GridQubit],
        x_anc: List[cirq.GridQubit],
        z_anc: List[cirq.GridQubit],
        d: int,
    ) -> cirq.Circuit:
        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*x_anc))
        for i, anc in enumerate(x_anc):
            neighbours = [data[min(i, len(data) - 1)],
                          data[min(i + 1, len(data) - 1)]]
            for nb in neighbours:
                circuit.append(cirq.CNOT(anc, nb))
        circuit.append(cirq.H.on_each(*x_anc))

        for i, anc in enumerate(z_anc):
            neighbours = [data[min(i, len(data) - 1)],
                          data[min(i + 1, len(data) - 1)]]
            for nb in neighbours:
                circuit.append(cirq.CNOT(nb, anc))

        all_anc = x_anc + z_anc
        if all_anc:
            circuit.append(cirq.measure(*all_anc, key="surface_syndrome"))
        return circuit


# ======================================================================
#  Logical Qubit
# ======================================================================

class LogicalQubit:
    """Abstraction that maps logical operations to error-corrected physical circuits.

    Wraps a ``SurfaceCodeStorageLayer`` patch and exposes Clifford+T logical
    gate methods that each return a ``cirq.Circuit``.
    """

    class GateType(Enum):
        X = auto()
        Z = auto()
        H = auto()
        S = auto()
        T = auto()
        CNOT = auto()
        MEASURE = auto()

    def __init__(
        self,
        logical_id: str,
        storage_layer: SurfaceCodeStorageLayer,
        patch_name: Optional[str] = None,
    ):
        self.logical_id = logical_id
        self._storage = storage_layer
        self._patch_name = patch_name or f"patch_{logical_id}"
        if self._patch_name not in self._storage.list_patches():
            self._storage.create_patch(self._patch_name)
        self._gate_log: List[Dict[str, Any]] = []
        logger.debug("LogicalQubit '%s' ready (patch=%s)", logical_id, self._patch_name)

    @property
    def patch(self) -> Dict[str, Any]:
        return self._storage.get_patch(self._patch_name)

    @property
    def data_qubits(self) -> List[cirq.GridQubit]:
        return self.patch["data_qubits"]

    def logical_x(self) -> cirq.Circuit:
        """Transversal logical X — X on an entire row."""
        d = self.patch["code_distance"]
        row = [cirq.GridQubit(0, c) for c in range(d)]
        circuit = cirq.Circuit(cirq.X.on_each(*row))
        self._record("X")
        return circuit

    def logical_z(self) -> cirq.Circuit:
        """Transversal logical Z — Z on an entire column."""
        d = self.patch["code_distance"]
        col = [cirq.GridQubit(r, 0) for r in range(d)]
        circuit = cirq.Circuit(cirq.Z.on_each(*col))
        self._record("Z")
        return circuit

    def logical_h(self) -> cirq.Circuit:
        """Transversal H — H on every data qubit + lattice rotation."""
        data = self.data_qubits
        circuit = cirq.Circuit(cirq.H.on_each(*data))
        self._record("H")
        return circuit

    def logical_s(self) -> cirq.Circuit:
        """Transversal S gate on all data qubits."""
        data = self.data_qubits
        circuit = cirq.Circuit(cirq.S.on_each(*data))
        self._record("S")
        return circuit

    def logical_t(self, distillery: "MagicStateDistillery") -> cirq.Circuit:
        """Logical T via magic state injection.

        Requires a ``MagicStateDistillery`` to supply the |T> state.
        """
        magic_circuit = distillery.distill()
        circuit = cirq.Circuit()
        circuit += magic_circuit
        data = self.data_qubits
        circuit.append(cirq.T.on_each(*data[:1]))
        self._record("T")
        return circuit

    def logical_measure(self, key: Optional[str] = None) -> cirq.Circuit:
        """Measure logical qubit in computational basis."""
        k = key or f"logical_{self.logical_id}"
        data = self.data_qubits
        circuit = cirq.Circuit(cirq.measure(*data, key=k))
        self._record("MEASURE")
        return circuit

    def syndrome_round(self) -> cirq.Circuit:
        return self._storage.run_syndrome_round(self._patch_name)

    def gate_history(self) -> List[Dict[str, Any]]:
        return list(self._gate_log)

    def _record(self, gate: str) -> None:
        self._gate_log.append({"gate": gate, "time": time.time()})


# ======================================================================
#  Magic State Distillery
# ======================================================================

class MagicStateDistillery:
    """Prepares high-fidelity |T> magic states via distillation.

    Uses the 15-to-1 distillation protocol by default.
    """

    class Protocol(Enum):
        FIFTEEN_TO_ONE = auto()
        TWENTY_TO_FOUR = auto()

    def __init__(
        self,
        protocol: "MagicStateDistillery.Protocol" = None,
        num_raw: int = 15,
        target_fidelity: float = 0.9999,
    ):
        self.protocol = protocol or self.Protocol.FIFTEEN_TO_ONE
        self._num_raw = num_raw
        self._target_fidelity = target_fidelity
        self._distill_count = 0
        self._lock = threading.RLock()
        logger.info(
            "MagicStateDistillery ready (protocol=%s, raw=%d, target_fidelity=%.4f)",
            self.protocol.name, self._num_raw, self._target_fidelity,
        )

    def distill(self) -> cirq.Circuit:
        """Build a single distillation round circuit.

        Returns:
            ``cirq.Circuit`` implementing the protocol.
        """
        with self._lock:
            self._distill_count += 1
            if self.protocol == self.Protocol.FIFTEEN_TO_ONE:
                return self._fifteen_to_one()
            return self._twenty_to_four()

    def distill_batch(self, count: int) -> List[cirq.Circuit]:
        """Distill *count* magic states."""
        return [self.distill() for _ in range(count)]

    def estimate_overhead(self) -> Dict[str, Any]:
        """Return resource estimates for one distillation round."""
        if self.protocol == self.Protocol.FIFTEEN_TO_ONE:
            physical_qubits = self._num_raw
            output_states = 1
            success_prob = 1 - 35 * (1e-3) ** 3  # third-order suppression
        else:
            physical_qubits = 20
            output_states = 4
            success_prob = 0.95
        return {
            "protocol": self.protocol.name,
            "physical_qubits": physical_qubits,
            "output_states": output_states,
            "success_probability": round(success_prob, 6),
            "target_fidelity": self._target_fidelity,
            "distillations_performed": self._distill_count,
        }

    # -- internal ----------------------------------------------------------

    def _fifteen_to_one(self) -> cirq.Circuit:
        qubits = [cirq.LineQubit(i) for i in range(self._num_raw)]
        circuit = cirq.Circuit()
        # Prepare |+> on all raw qubits
        circuit.append(cirq.H.on_each(*qubits))
        # Apply T to each
        circuit.append(cirq.T.on_each(*qubits))
        # Parity checks via CNOTs to ancilla-like roles
        for i in range(1, len(qubits)):
            circuit.append(cirq.CNOT(qubits[0], qubits[i]))
        # Measure verification qubits
        circuit.append(cirq.measure(*qubits[1:], key="distill_verify"))
        return circuit

    def _twenty_to_four(self) -> cirq.Circuit:
        qubits = [cirq.LineQubit(i) for i in range(20)]
        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*qubits))
        circuit.append(cirq.T.on_each(*qubits))
        for i in range(4):
            for j in range(4):
                circuit.append(cirq.CNOT(qubits[i], qubits[4 + i * 4 + j]))
        circuit.append(cirq.measure(*qubits[4:], key="distill_verify"))
        return circuit


# ======================================================================
#  Lattice Surgery Engine
# ======================================================================

class LatticeSurgeryEngine:
    """Performs lattice-surgery-based logical CNOT between surface-code patches.

    Lattice surgery merges and splits adjacent code patches to implement
    logical multi-qubit gates without transversal operations.
    """

    class OperationType(Enum):
        MERGE_XX = auto()
        MERGE_ZZ = auto()
        SPLIT = auto()

    def __init__(self, storage_layer: SurfaceCodeStorageLayer):
        self._storage = storage_layer
        self._op_log: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        logger.info("LatticeSurgeryEngine initialised")

    def logical_cnot(
        self,
        control_patch: str,
        target_patch: str,
    ) -> cirq.Circuit:
        """Build a lattice-surgery logical CNOT between two patches.

        Steps:
            1. XX merge between control and ancilla
            2. ZZ merge between ancilla and target
            3. Split ancilla
            4. Corrections based on merge outcomes

        Returns:
            Combined ``cirq.Circuit``.
        """
        ctrl = self._storage.get_patch(control_patch)
        tgt = self._storage.get_patch(target_patch)
        d = ctrl["code_distance"]

        ancilla_qubits = [cirq.GridQubit(100, c) for c in range(d)]
        circuit = cirq.Circuit()

        # Step 1 — XX merge (control ↔ ancilla)
        xx_circuit = self._merge_xx(ctrl["data_qubits"], ancilla_qubits, d)
        circuit += xx_circuit

        # Step 2 — ZZ merge (ancilla ↔ target)
        zz_circuit = self._merge_zz(ancilla_qubits, tgt["data_qubits"], d)
        circuit += zz_circuit

        # Step 3 — Split ancilla (measure + correct)
        circuit.append(cirq.measure(*ancilla_qubits, key="surgery_ancilla"))

        # Conditional corrections (classically conditioned in real hardware)
        circuit.append(cirq.X.on_each(*tgt["data_qubits"][:1]))

        self._record_op("CNOT", control_patch, target_patch)
        return circuit

    def merge(
        self,
        patch_a: str,
        patch_b: str,
        merge_type: "LatticeSurgeryEngine.OperationType" = None,
    ) -> cirq.Circuit:
        """Generic merge of two patches."""
        merge_type = merge_type or self.OperationType.MERGE_ZZ
        a = self._storage.get_patch(patch_a)
        b = self._storage.get_patch(patch_b)
        d = a["code_distance"]
        if merge_type == self.OperationType.MERGE_XX:
            circuit = self._merge_xx(a["data_qubits"], b["data_qubits"], d)
        else:
            circuit = self._merge_zz(a["data_qubits"], b["data_qubits"], d)
        self._record_op(merge_type.name, patch_a, patch_b)
        return circuit

    def split(self, patch_name: str) -> cirq.Circuit:
        """Split a merged patch — measure boundary stabilisers."""
        patch = self._storage.get_patch(patch_name)
        data = patch["data_qubits"]
        circuit = cirq.Circuit(cirq.measure(*data, key=f"split_{patch_name}"))
        self._record_op("SPLIT", patch_name, None)
        return circuit

    def operation_log(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._op_log)

    # -- internal ----------------------------------------------------------

    def _merge_xx(
        self,
        left: List[cirq.GridQubit],
        right: List[cirq.GridQubit],
        d: int,
    ) -> cirq.Circuit:
        circuit = cirq.Circuit()
        boundary = min(d, len(left), len(right))
        for i in range(boundary):
            circuit.append(cirq.H(left[i]))
            circuit.append(cirq.CNOT(left[i], right[i]))
            circuit.append(cirq.H(left[i]))
        circuit.append(
            cirq.measure(*right[:boundary], key="merge_xx_result"),
        )
        return circuit

    def _merge_zz(
        self,
        left: List[cirq.GridQubit],
        right: List[cirq.GridQubit],
        d: int,
    ) -> cirq.Circuit:
        circuit = cirq.Circuit()
        boundary = min(d, len(left), len(right))
        for i in range(boundary):
            circuit.append(cirq.CNOT(left[i], right[i]))
        circuit.append(
            cirq.measure(*right[:boundary], key="merge_zz_result"),
        )
        return circuit

    def _record_op(self, op: str, a: str, b: Optional[str]) -> None:
        with self._lock:
            self._op_log.append({"op": op, "a": a, "b": b, "time": time.time()})


# ======================================================================
#  Error Budget Tracker
# ======================================================================

class ErrorBudgetTracker:
    """Tracks per-query error budgets and allocates error-correction resources.

    Each query is assigned a total error budget (probability target).  The
    tracker distributes the budget across gates and allocates additional
    syndrome rounds when the budget is at risk.
    """

    def __init__(self, default_budget: float = 1e-6):
        if not (0 < default_budget < 1):
            raise ValueError("default_budget must be in (0, 1)")
        self._default = default_budget
        self._queries: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        logger.info("ErrorBudgetTracker ready (default=%.2e)", default_budget)

    def register_query(
        self,
        query_id: Optional[str] = None,
        total_budget: Optional[float] = None,
    ) -> str:
        """Start tracking a new query.

        Returns:
            The assigned ``query_id``.
        """
        qid = query_id or str(uuid.uuid4())
        budget = total_budget if total_budget is not None else self._default
        with self._lock:
            self._queries[qid] = {
                "total_budget": budget,
                "spent": 0.0,
                "gates": [],
                "syndrome_rounds": 0,
                "created_at": time.time(),
            }
        return qid

    def record_gate(
        self,
        query_id: str,
        gate_name: str,
        error_rate: float,
    ) -> Dict[str, Any]:
        """Record an executed gate and debit from the query's budget.

        Returns:
            Dict with ``remaining``, ``over_budget`` flag, and
            ``recommended_syndrome_rounds``.
        """
        with self._lock:
            q = self._queries.get(query_id)
            if q is None:
                raise KeyError(f"Unknown query_id '{query_id}'")
            q["spent"] += error_rate
            q["gates"].append({"gate": gate_name, "error": error_rate, "time": time.time()})
            remaining = q["total_budget"] - q["spent"]
            over = remaining < 0
            # Recommend extra syndrome rounds proportional to overrun
            rec_rounds = 0
            if over:
                rec_rounds = max(1, int(math.ceil(-remaining / max(error_rate, 1e-15))))
                q["syndrome_rounds"] += rec_rounds
            return {
                "remaining": remaining,
                "over_budget": over,
                "recommended_syndrome_rounds": rec_rounds,
            }

    def allocate_correction(
        self,
        query_id: str,
        additional_rounds: int = 1,
    ) -> Dict[str, Any]:
        """Manually allocate additional syndrome-extraction rounds."""
        with self._lock:
            q = self._queries.get(query_id)
            if q is None:
                raise KeyError(query_id)
            q["syndrome_rounds"] += additional_rounds
            # Each round suppresses error by code-distance factor
            suppression = 0.1 ** additional_rounds
            q["spent"] *= suppression
            remaining = q["total_budget"] - q["spent"]
            return {"syndrome_rounds_total": q["syndrome_rounds"], "remaining": remaining}

    def query_status(self, query_id: str) -> Dict[str, Any]:
        with self._lock:
            q = self._queries.get(query_id)
            if q is None:
                raise KeyError(query_id)
            return {
                "query_id": query_id,
                "total_budget": q["total_budget"],
                "spent": q["spent"],
                "remaining": q["total_budget"] - q["spent"],
                "gate_count": len(q["gates"]),
                "syndrome_rounds": q["syndrome_rounds"],
                "over_budget": q["spent"] > q["total_budget"],
            }

    def summary(self) -> Dict[str, Any]:
        """Aggregate statistics across all tracked queries."""
        with self._lock:
            total = len(self._queries)
            over = sum(1 for q in self._queries.values() if q["spent"] > q["total_budget"])
            return {
                "tracked_queries": total,
                "over_budget_queries": over,
                "total_syndrome_rounds": sum(q["syndrome_rounds"] for q in self._queries.values()),
                "avg_budget_utilisation": (
                    np.mean([q["spent"] / q["total_budget"] for q in self._queries.values()])
                    if total else 0.0
                ),
            }
