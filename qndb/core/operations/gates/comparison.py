"""Comparison gates: equality, inequality, greater-than, less-than, swap test."""

import cirq
import logging
from typing import List

logger = logging.getLogger(__name__)


class ComparisonGates:
    """Quantum circuits for comparing qubit registers."""

    def create_equality_test(
        self,
        qubits1: List[cirq.Qid],
        qubits2: List[cirq.Qid],
        output_qubit: cirq.Qid,
    ) -> cirq.Circuit:
        """Test equality between two qubit registers.

        After execution *output_qubit* is |1> iff registers are equal.

        Args:
            qubits1: First register.
            qubits2: Second register.
            output_qubit: Result qubit.

        Returns:
            Equality test circuit.
        """
        if len(qubits1) != len(qubits2):
            raise ValueError("Qubit registers must be the same size")

        n = len(qubits1)
        eq_circuit = cirq.Circuit()
        ancillas = [cirq.NamedQubit(f'_eq_anc_{i}') for i in range(n)]

        for i, (q1, q2) in enumerate(zip(qubits1, qubits2)):
            eq_circuit.append(cirq.CNOT(q1, ancillas[i]))
            eq_circuit.append(cirq.CNOT(q2, ancillas[i]))

        eq_circuit.append(cirq.X.on_each(*ancillas))
        if len(ancillas) == 1:
            eq_circuit.append(cirq.CNOT(ancillas[0], output_qubit))
        else:
            eq_circuit.append(cirq.X(output_qubit).controlled_by(*ancillas))
        eq_circuit.append(cirq.X.on_each(*ancillas))

        for i, (q1, q2) in enumerate(zip(qubits1, qubits2)):
            eq_circuit.append(cirq.CNOT(q2, ancillas[i]))
            eq_circuit.append(cirq.CNOT(q1, ancillas[i]))

        return eq_circuit

    def create_not_equal(
        self,
        qubits1: List[cirq.Qid],
        qubits2: List[cirq.Qid],
        output_qubit: cirq.Qid,
    ) -> cirq.Circuit:
        """Test inequality — complement of :meth:`create_equality_test`."""
        circuit = self.create_equality_test(qubits1, qubits2, output_qubit)
        circuit.append(cirq.X(output_qubit))
        return circuit

    def create_comparator(
        self,
        qubits_a: List[cirq.Qid],
        qubits_b: List[cirq.Qid],
        output_qubit: cirq.Qid,
    ) -> cirq.Circuit:
        """Compare two registers — *output_qubit* is |1> if A >= B.

        Args:
            qubits_a: First register.
            qubits_b: Second register.
            output_qubit: Result qubit.

        Returns:
            Comparator circuit.
        """
        if len(qubits_a) != len(qubits_b):
            raise ValueError("Qubit registers must be the same size")

        comp_circuit = cirq.Circuit()
        n = len(qubits_a)
        temp_qubits = [cirq.NamedQubit(f'_cmp_tmp_{i}') for i in range(n)]

        for i in range(n - 1, -1, -1):
            comp_circuit.append(cirq.X(qubits_b[i]))
            comp_circuit.append(cirq.TOFFOLI(qubits_a[i], qubits_b[i], temp_qubits[i]))
            comp_circuit.append(cirq.X(qubits_b[i]))

            if i == n - 1:
                comp_circuit.append(cirq.CNOT(temp_qubits[i], output_qubit))
            else:
                equal_bits_control = temp_qubits[i + 1:n]
                if equal_bits_control:
                    comp_circuit.append(cirq.X.on_each(*equal_bits_control))
                    comp_circuit.append(
                        cirq.X(output_qubit).controlled_by(temp_qubits[i], *equal_bits_control)
                    )
                    comp_circuit.append(cirq.X.on_each(*equal_bits_control))

            comp_circuit.append(cirq.CNOT(qubits_a[i], temp_qubits[i]))
            comp_circuit.append(cirq.CNOT(qubits_b[i], temp_qubits[i]))
            comp_circuit.append(cirq.X(temp_qubits[i]))

        return comp_circuit

    def create_greater_than_equal(
        self,
        qubits_a: List[cirq.Qid],
        qubits_b: List[cirq.Qid],
        output_qubit: cirq.Qid,
    ) -> cirq.Circuit:
        """Alias for :meth:`create_comparator` (A >= B)."""
        return self.create_comparator(qubits_a, qubits_b, output_qubit)

    def create_less_than(
        self,
        qubits_a: List[cirq.Qid],
        qubits_b: List[cirq.Qid],
        output_qubit: cirq.Qid,
    ) -> cirq.Circuit:
        """Test A < B (complement of A >= B)."""
        circuit = self.create_comparator(qubits_a, qubits_b, output_qubit)
        circuit.append(cirq.X(output_qubit))
        return circuit

    def create_swap_test(
        self,
        qubits_a: List[cirq.Qid],
        qubits_b: List[cirq.Qid],
        control_qubit: cirq.Qid,
    ) -> cirq.Circuit:
        """SWAP test to measure similarity between quantum states.

        Args:
            qubits_a: First register.
            qubits_b: Second register.
            control_qubit: Control qubit.

        Returns:
            SWAP test circuit.
        """
        if len(qubits_a) != len(qubits_b):
            raise ValueError("Qubit registers must be the same size for SWAP test")

        swap_circuit = cirq.Circuit()
        swap_circuit.append(cirq.H(control_qubit))
        for a, b in zip(qubits_a, qubits_b):
            swap_circuit.append(cirq.SWAP(a, b).controlled_by(control_qubit))
        swap_circuit.append(cirq.H(control_qubit))
        return swap_circuit
