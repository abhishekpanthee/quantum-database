"""Transform gates: QFT, phase estimation."""

import cirq
import numpy as np
import logging
from typing import List

logger = logging.getLogger(__name__)


class TransformGates:
    """Quantum Fourier Transform and related unitary circuits."""

    def create_qft(self, qubits: List[cirq.Qid], inverse: bool = False) -> cirq.Circuit:
        """Create a Quantum Fourier Transform circuit.

        Args:
            qubits: Qubits to transform.
            inverse: If True, build the inverse QFT.

        Returns:
            QFT (or inverse QFT) circuit.
        """
        n = len(qubits)
        qft_circuit = cirq.Circuit()

        if inverse:
            qubits_rev = list(reversed(qubits))
            for i in range(n):
                for j in range(i):
                    angle = -2 * np.pi / (2 ** (i - j + 1))
                    qft_circuit.append(cirq.CZ(qubits_rev[j], qubits_rev[i]) ** (angle / np.pi))
                qft_circuit.append(cirq.H(qubits_rev[i]))
        else:
            for i in range(n):
                qft_circuit.append(cirq.H(qubits[i]))
                for j in range(i + 1, n):
                    angle = 2 * np.pi / (2 ** (j - i + 1))
                    qft_circuit.append(cirq.CZ(qubits[i], qubits[j]) ** (angle / np.pi))

        return qft_circuit

    def create_phase_estimation_circuit(
        self,
        target_qubits: List[cirq.Qid],
        phase_qubits: List[cirq.Qid],
        unitary_circuit: cirq.Circuit,
    ) -> cirq.Circuit:
        """Quantum Phase Estimation circuit.

        Args:
            target_qubits: Target qubits for the unitary.
            phase_qubits: Qubits to store the estimated phase.
            unitary_circuit: Circuit implementing the unitary whose phase to estimate.

        Returns:
            QPE circuit.
        """
        qpe_circuit = cirq.Circuit()
        qpe_circuit.append(cirq.H.on_each(*phase_qubits))

        for i, phase_qubit in enumerate(phase_qubits):
            power = 2 ** i
            for _ in range(power):
                for moment in unitary_circuit:
                    controlled_moment = cirq.Moment(
                        op.controlled_by(phase_qubit) for op in moment
                    )
                    qpe_circuit.append(controlled_moment)

        qpe_circuit += self.create_qft(phase_qubits, inverse=True)
        return qpe_circuit
