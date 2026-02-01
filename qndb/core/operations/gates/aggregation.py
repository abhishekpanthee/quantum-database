"""Aggregation gates: COUNT, SUM, AVG over qubit registers."""

import cirq
import numpy as np
import logging
from typing import List, Optional

from qndb.core.operations.gates.transforms import TransformGates

logger = logging.getLogger(__name__)

_transforms = TransformGates()


class AggregationGates:
    """Quantum circuits for database aggregation functions."""

    def create_quantum_count(
        self,
        flag_qubits: List[cirq.Qid],
        count_qubits: List[cirq.Qid],
    ) -> cirq.Circuit:
        """Compute Hamming weight (COUNT of |1> flags) into *count_qubits*.

        Args:
            flag_qubits: Input flags (each |1> = one match).
            count_qubits: Output register for the binary count.

        Returns:
            COUNT circuit.
        """
        circuit = cirq.Circuit()
        n_count = len(count_qubits)

        for flag in flag_qubits:
            for i in range(n_count - 1, -1, -1):
                controls = [flag] + list(count_qubits[i + 1:])
                if len(controls) == 1:
                    circuit.append(cirq.CNOT(controls[0], count_qubits[i]))
                else:
                    circuit.append(cirq.X(count_qubits[i]).controlled_by(*controls))

        return circuit

    def create_quantum_sum(
        self,
        value_registers: List[List[cirq.Qid]],
        sum_qubits: List[cirq.Qid],
    ) -> cirq.Circuit:
        """Accumulate binary-encoded values via QFT-based addition.

        Args:
            value_registers: Qubit registers to sum.
            sum_qubits: Accumulator register.

        Returns:
            SUM circuit.
        """
        circuit = cirq.Circuit()
        n_sum = len(sum_qubits)

        circuit += _transforms.create_qft(sum_qubits)

        for value_qubits in value_registers:
            for j, v_qubit in enumerate(value_qubits):
                for k in range(n_sum):
                    angle_exp = k - j
                    if angle_exp < 0:
                        continue
                    angle = 2 * np.pi / (2 ** (angle_exp + 1))
                    circuit.append(cirq.CZ(v_qubit, sum_qubits[k]) ** (angle / np.pi))

        circuit += _transforms.create_qft(sum_qubits, inverse=True)
        return circuit

    def create_quantum_avg(
        self,
        value_registers: List[List[cirq.Qid]],
        sum_qubits: List[cirq.Qid],
        count_qubits: List[cirq.Qid],
        flag_qubits: Optional[List[cirq.Qid]] = None,
    ) -> cirq.Circuit:
        """Compute SUM and COUNT in parallel so AVG = SUM / COUNT classically.

        Args:
            value_registers: Registers holding values to average.
            sum_qubits: Accumulator for the sum.
            count_qubits: Register to hold the count.
            flag_qubits: Per-row flags; if None all rows are counted.

        Returns:
            Combined SUM + COUNT circuit.
        """
        circuit = cirq.Circuit()
        circuit += self.create_quantum_sum(value_registers, sum_qubits)

        if flag_qubits is not None:
            circuit += self.create_quantum_count(flag_qubits, count_qubits)
        else:
            tmp_flags = [cirq.NamedQubit(f"_avg_flag_{i}") for i in range(len(value_registers))]
            circuit.append(cirq.X.on_each(*tmp_flags))
            circuit += self.create_quantum_count(tmp_flags, count_qubits)

        return circuit
