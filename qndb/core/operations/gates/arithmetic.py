"""Arithmetic gates: binary adder, incrementer."""

import cirq
import logging
from typing import List

logger = logging.getLogger(__name__)


class ArithmeticGates:
    """Quantum circuits for arithmetic operations on qubit registers."""

    def create_binary_adder(
        self,
        qubits_a: List[cirq.Qid],
        qubits_b: List[cirq.Qid],
        output_qubits: List[cirq.Qid],
    ) -> cirq.Circuit:
        """Ripple-carry binary adder.

        Args:
            qubits_a: First input register.
            qubits_b: Second input register.
            output_qubits: Output register (must be len(qubits_a) + 1).

        Returns:
            Adder circuit.
        """
        if len(qubits_a) != len(qubits_b) or len(output_qubits) < len(qubits_a) + 1:
            raise ValueError("Invalid qubit registers sizes for binary adder")

        adder_circuit = cirq.Circuit()
        carry_qubit = cirq.NamedQubit('_adder_carry')

        for i in range(len(qubits_a)):
            if i == 0:
                adder_circuit.append(cirq.CNOT(qubits_a[i], output_qubits[i]))
                adder_circuit.append(cirq.CNOT(qubits_b[i], output_qubits[i]))
                adder_circuit.append(cirq.CNOT(qubits_a[i], carry_qubit))
                adder_circuit.append(cirq.CNOT(qubits_b[i], carry_qubit))
                adder_circuit.append(cirq.TOFFOLI(qubits_a[i], qubits_b[i], carry_qubit))
            else:
                adder_circuit.append(cirq.CNOT(qubits_a[i], output_qubits[i]))
                adder_circuit.append(cirq.CNOT(qubits_b[i], output_qubits[i]))
                adder_circuit.append(cirq.CNOT(carry_qubit, output_qubits[i]))
                adder_circuit.append(cirq.TOFFOLI(qubits_a[i], qubits_b[i], output_qubits[i + 1]))
                adder_circuit.append(cirq.TOFFOLI(qubits_a[i], carry_qubit, output_qubits[i + 1]))
                adder_circuit.append(cirq.TOFFOLI(qubits_b[i], carry_qubit, output_qubits[i + 1]))
                adder_circuit.append(cirq.CNOT(carry_qubit, output_qubits[i + 1]))
                adder_circuit.append(cirq.CNOT(carry_qubit, output_qubits[i + 1]))

        adder_circuit.append(cirq.CNOT(carry_qubit, output_qubits[-1]))
        return adder_circuit

    def create_incrementer(self, qubits: List[cirq.Qid]) -> cirq.Circuit:
        """Increment a qubit register by 1.

        Args:
            qubits: Register to increment.

        Returns:
            Incrementer circuit.
        """
        inc_circuit = cirq.Circuit()

        for i in range(len(qubits) - 1, -1, -1):
            control_qubits = qubits[i + 1:] if i < len(qubits) - 1 else []
            if control_qubits:
                inc_circuit.append(cirq.X(qubits[i]).controlled_by(*control_qubits))
            else:
                inc_circuit.append(cirq.X(qubits[i]))

        return inc_circuit
