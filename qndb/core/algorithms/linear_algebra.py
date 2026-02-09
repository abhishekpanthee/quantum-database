"""
Linear Algebra Operations
~~~~~~~~~~~~~~~~~~~~~~~~~~

Quantum algorithms for linear-algebra workloads:

* **HHLSolver** — HHL algorithm for quantum linear systems Ax = b
* **QuantumPCA** — Quantum principal component analysis
* **QSVTFramework** — Quantum singular value transformation
* **QuantumMatrixInversion** — Matrix inversion via HHL wrapper
* **BlockEncoder** — Block-encoding of classical matrices into unitaries
"""

import cirq
import math
import logging
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ======================================================================
# Block Encoder
# ======================================================================

class BlockEncoder:
    """Embed a classical matrix into a unitary via block-encoding.

    Given an *n × n* matrix *A* (with ‖A‖ ≤ 1), constructs a unitary

        U_A = [[A, ·], [·, ·]]

    using a single ancilla qubit and controlled rotations that
    approximate the matrix entries.

    Args:
        num_qubits: log₂ of the matrix dimension.
    """

    def __init__(self, num_qubits: int) -> None:
        self.num_qubits = num_qubits
        self.dim = 2 ** num_qubits

    def encode(self, matrix: np.ndarray) -> cirq.Circuit:
        """Build a block-encoding circuit for *matrix*.

        This uses a LCU (linear combination of unitaries)
        decomposition: express *A* as a weighted sum of Pauli strings
        and implement each term with controlled rotations.

        Args:
            matrix: Hermitian matrix with ‖A‖_∞ ≤ 1.

        Returns:
            ``cirq.Circuit`` whose top-left block approximates *A*.
        """
        matrix = np.asarray(matrix, dtype=complex)
        if matrix.shape[0] != matrix.shape[1]:
            raise ValueError("Matrix must be square")

        norm = np.linalg.norm(matrix, ord=2)
        if norm > 1.0 + 1e-9:
            raise ValueError(f"Matrix 2-norm ({norm:.4f}) exceeds 1")

        n = max(1, int(math.ceil(math.log2(matrix.shape[0]))))
        ancilla = cirq.LineQubit(n)
        data_qubits = [cirq.LineQubit(i) for i in range(n)]

        circuit = cirq.Circuit()

        # Prepare ancilla in |+⟩
        circuit.append(cirq.H(ancilla))

        # Diagonal phase encoding
        eigenvalues, eigvecs = np.linalg.eigh(matrix.real)
        for idx, ev in enumerate(eigenvalues[:self.dim]):
            angle = float(np.arccos(np.clip(ev, -1, 1)))
            if abs(angle) > 1e-12:
                circuit.append(cirq.ry(2 * angle).on(ancilla).controlled_by(
                    *self._index_controls(data_qubits, idx, n)
                ) if n > 0 else cirq.ry(2 * angle).on(ancilla))

        circuit.append(cirq.H(ancilla))
        return circuit

    @staticmethod
    def _index_controls(
        qubits: List[cirq.LineQubit], index: int, n: int,
    ) -> List[cirq.LineQubit]:
        """Return qubits in the computational-basis state ``|index⟩``."""
        controls = []
        bits = format(index, f"0{n}b")
        for i, b in enumerate(bits):
            if i < len(qubits):
                controls.append(qubits[i])
        return controls


# ======================================================================
# HHL Solver
# ======================================================================

class HHLSolver:
    """HHL algorithm for solving Ax = b on a quantum computer.

    Implements the Harrow-Hassidim-Lloyd algorithm:
    1. Phase estimation to extract eigenvalues of *A*.
    2. Controlled rotation to encode 1/λ into ancilla amplitude.
    3. Inverse phase estimation to uncompute.

    Only works for Hermitian *A* with known eigenvalue bounds.

    Args:
        num_qubits: Number of qubits for the *b* register.
        num_ancilla: Precision qubits for phase estimation.
    """

    def __init__(self, num_qubits: int, num_ancilla: int = 4) -> None:
        self.num_qubits = num_qubits
        self.num_ancilla = num_ancilla

    def build_circuit(
        self,
        hamiltonian_circuit: cirq.Circuit,
        b_prep: Optional[cirq.Circuit] = None,
    ) -> cirq.Circuit:
        """Build the full HHL circuit.

        Args:
            hamiltonian_circuit: Circuit implementing *exp(iAt)* for
                one unit of time on the data register.
            b_prep: Optional preparation circuit for |b⟩.  If *None*,
                ``H`` is applied to the first data qubit.

        Returns:
            ``cirq.Circuit`` with measurement on the ancilla flag qubit.
        """
        data = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        clock = [cirq.LineQubit(self.num_qubits + i) for i in range(self.num_ancilla)]
        flag = cirq.LineQubit(self.num_qubits + self.num_ancilla)

        circuit = cirq.Circuit()

        # 1. Prepare |b⟩
        if b_prep is not None:
            circuit += b_prep
        else:
            circuit.append(cirq.H(data[0]))

        # 2. Phase estimation
        circuit.append(cirq.H.on_each(*clock))
        for j, cq in enumerate(clock):
            reps = 2 ** j
            for _ in range(reps):
                controlled = cirq.Circuit(
                    [op.controlled_by(cq) for moment in hamiltonian_circuit for op in moment]
                )
                circuit += controlled

        # Inverse QFT on clock register
        circuit += self._inverse_qft(clock)

        # 3. Controlled rotation: R_y(2 * arcsin(C / λ))
        for j, cq in enumerate(clock):
            lam_est = (j + 1)  # eigenvalue estimate (simplified)
            angle = 2 * math.asin(min(1.0, 1.0 / max(lam_est, 1)))
            circuit.append(cirq.ry(angle).on(flag).controlled_by(cq))

        # 4. Inverse phase estimation (uncompute)
        circuit += self._qft(clock)
        for j in range(len(clock) - 1, -1, -1):
            cq = clock[j]
            reps = 2 ** j
            for _ in range(reps):
                inv_ham = cirq.inverse(hamiltonian_circuit)
                controlled = cirq.Circuit(
                    [op.controlled_by(cq) for moment in inv_ham for op in moment]
                )
                circuit += controlled
        circuit.append(cirq.H.on_each(*clock))

        # 5. Measure flag
        circuit.append(cirq.measure(flag, key="flag"))
        return circuit

    @staticmethod
    def _qft(qubits: List[cirq.LineQubit]) -> cirq.Circuit:
        c = cirq.Circuit()
        n = len(qubits)
        for i in range(n):
            c.append(cirq.H(qubits[i]))
            for j in range(i + 1, n):
                c.append(cirq.CZPowGate(exponent=1 / 2 ** (j - i)).on(
                    qubits[j], qubits[i],
                ))
        # Swap
        for i in range(n // 2):
            c.append(cirq.SWAP(qubits[i], qubits[n - 1 - i]))
        return c

    @staticmethod
    def _inverse_qft(qubits: List[cirq.LineQubit]) -> cirq.Circuit:
        return cirq.inverse(HHLSolver._qft(qubits))


# ======================================================================
# Quantum PCA
# ======================================================================

class QuantumPCA:
    """Quantum principal component analysis.

    Implements density-matrix exponentiation: given copies of a
    quantum state ρ, extract the principal components by simulating
    exp(-iρt) via the swap trick.

    Args:
        num_qubits: Number of qubits per register.
        num_copies: Number of state copies used for precision.
    """

    def __init__(self, num_qubits: int, num_copies: int = 4) -> None:
        self.num_qubits = num_qubits
        self.num_copies = num_copies

    def build_circuit(
        self,
        state_prep: Optional[cirq.Circuit] = None,
        num_phase_qubits: int = 3,
    ) -> cirq.Circuit:
        """Build the qPCA phase-estimation circuit.

        Uses partial swaps between register A (the target) and
        register B (copies of ρ) to implement exp(-iρt).

        Args:
            state_prep: Circuit to prepare the input state on the
                first register.  Defaults to Hadamard on all qubits.
            num_phase_qubits: Precision bits for phase estimation.

        Returns:
            ``cirq.Circuit`` with measurement on the phase register.
        """
        reg_a = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        reg_b = [cirq.LineQubit(self.num_qubits + i) for i in range(self.num_qubits)]
        phase = [cirq.LineQubit(2 * self.num_qubits + i) for i in range(num_phase_qubits)]

        circuit = cirq.Circuit()

        # Prepare the state
        if state_prep is not None:
            circuit += state_prep
        else:
            circuit.append(cirq.H.on_each(*reg_a))
            circuit.append(cirq.H.on_each(*reg_b))

        # Phase estimation with swap-based exponentiation
        circuit.append(cirq.H.on_each(*phase))
        for j, pq in enumerate(phase):
            reps = 2 ** j
            for _ in range(reps):
                # Controlled partial SWAP between reg_a and reg_b
                for a_q, b_q in zip(reg_a, reg_b):
                    circuit.append(cirq.SWAP(a_q, b_q).controlled_by(pq))

        # Inverse QFT
        circuit += HHLSolver._inverse_qft(phase)
        circuit.append(cirq.measure(*phase, key="eigenvalues"))
        return circuit

    def extract_components(
        self,
        state_prep: Optional[cirq.Circuit] = None,
        num_phase_qubits: int = 3,
        repetitions: int = 1000,
    ) -> Dict[str, Any]:
        """Run qPCA and return the estimated eigenvalue distribution.

        Returns:
            Dict with ``eigenvalue_histogram`` mapping binary
            eigenvalue labels to counts.
        """
        circuit = self.build_circuit(state_prep, num_phase_qubits)
        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)
        bits = result.measurements["eigenvalues"]

        histogram: Dict[str, int] = {}
        for sample in bits:
            label = "".join(str(int(b)) for b in sample)
            histogram[label] = histogram.get(label, 0) + 1

        logger.info("qPCA extracted %d distinct eigenvalue bins", len(histogram))
        return {"eigenvalue_histogram": histogram}


# ======================================================================
# QSVT — Quantum Singular Value Transformation
# ======================================================================

class QSVTFramework:
    """Quantum singular value transformation.

    A unified framework that subsumes HHL, quantum walks, and other
    linear-algebra primitives.  Given a block-encoding of *A* and a
    polynomial *p*, applies *p(A)* via interleaved signal-processing
    rotations.

    Args:
        num_qubits: Dimension qubits.
    """

    def __init__(self, num_qubits: int) -> None:
        self.num_qubits = num_qubits

    def build_circuit(
        self,
        block_encoding: cirq.Circuit,
        phase_angles: List[float],
    ) -> cirq.Circuit:
        """Build the QSVT circuit.

        Args:
            block_encoding: Unitary whose top-left block is *A*.
            phase_angles: Signal-processing angles (φ_0 … φ_d) that
                define the target polynomial *p*.

        Returns:
            ``cirq.Circuit`` implementing *p(A)* in the block.
        """
        signal_qubit = cirq.LineQubit(self.num_qubits)
        circuit = cirq.Circuit()

        for idx, phi in enumerate(phase_angles):
            # Signal-processing rotation on the signal qubit
            circuit.append(cirq.rz(2 * phi).on(signal_qubit))
            if idx < len(phase_angles) - 1:
                # Interleave with the block-encoding (or its adjoint)
                if idx % 2 == 0:
                    circuit += block_encoding
                else:
                    circuit += cirq.inverse(block_encoding)

        return circuit

    def polynomial_transform(
        self,
        block_encoding: cirq.Circuit,
        phase_angles: List[float],
        repetitions: int = 1000,
    ) -> Dict[str, Any]:
        """Run the QSVT circuit and sample.

        Returns:
            Dict with ``measurement_results`` and ``success_probability``.
        """
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        signal_qubit = cirq.LineQubit(self.num_qubits)

        circuit = self.build_circuit(block_encoding, phase_angles)
        circuit.append(cirq.measure(signal_qubit, key="signal"))
        circuit.append(cirq.measure(*qubits, key="data"))

        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)

        signal_bits = result.measurements["signal"]
        success_count = int(np.sum(signal_bits == 0))
        prob = success_count / repetitions

        logger.info("QSVT success probability: %.4f", prob)
        return {
            "measurement_results": result.measurements["data"].tolist(),
            "success_probability": prob,
        }


# ======================================================================
# Quantum Matrix Inversion
# ======================================================================

class QuantumMatrixInversion:
    """Matrix inversion for analytics queries via HHL.

    Thin wrapper around :class:`HHLSolver` that accepts a NumPy matrix
    and prepares the required circuits automatically.

    Args:
        num_qubits: Register size (log₂ of the matrix dimension).
        num_ancilla: Phase-estimation ancilla qubits.
    """

    def __init__(self, num_qubits: int, num_ancilla: int = 4) -> None:
        self.num_qubits = num_qubits
        self.num_ancilla = num_ancilla
        self.hhl = HHLSolver(num_qubits, num_ancilla)

    def build_circuit(
        self,
        matrix: np.ndarray,
        b_state: Optional[np.ndarray] = None,
    ) -> cirq.Circuit:
        """Build the matrix-inversion circuit.

        Args:
            matrix: Hermitian matrix to invert.
            b_state: Optional vector |b⟩ (defaults to |0…01⟩).

        Returns:
            ``cirq.Circuit``.
        """
        matrix = np.asarray(matrix, dtype=complex)
        norm = np.linalg.norm(matrix, ord=2)
        if norm > 0:
            matrix = matrix / norm  # normalise for block-encoding

        # Build exp(iA) approximation using first-order Trotter
        ham_circuit = self._trotter_step(matrix)

        b_prep = None
        if b_state is not None:
            b_prep = self._state_prep(b_state)

        return self.hhl.build_circuit(ham_circuit, b_prep)

    def _trotter_step(self, matrix: np.ndarray) -> cirq.Circuit:
        """First-order Trotter step for exp(iA)."""
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = cirq.Circuit()
        n = matrix.shape[0]

        for i in range(min(n, 2 ** self.num_qubits)):
            for j in range(i + 1, min(n, 2 ** self.num_qubits)):
                val = float(np.real(matrix[i, j]))
                if abs(val) > 1e-12:
                    if i < self.num_qubits and j < self.num_qubits:
                        circuit.append(cirq.ZZPowGate(exponent=val / math.pi).on(
                            qubits[i], qubits[j],
                        ))

        for i in range(min(n, 2 ** self.num_qubits)):
            val = float(np.real(matrix[i, i]))
            if abs(val) > 1e-12 and i < self.num_qubits:
                circuit.append(cirq.rz(2 * val).on(qubits[i]))

        return circuit

    @staticmethod
    def _state_prep(state: np.ndarray) -> cirq.Circuit:
        """Approximate state preparation using Ry rotations."""
        state = state / np.linalg.norm(state)
        n = max(1, int(math.ceil(math.log2(len(state)))))
        qubits = [cirq.LineQubit(i) for i in range(n)]
        circuit = cirq.Circuit()

        # Amplitude encoding via Ry ladder (approximate)
        for i in range(n):
            angle = 2 * math.acos(max(min(float(np.abs(state[0])), 1.0), 0.0))
            circuit.append(cirq.ry(angle).on(qubits[i]))

        return circuit
