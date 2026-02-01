"""Sorting gates: compare-and-swap, odd-even merge sorting network."""

import cirq
import logging
from typing import List

from qndb.core.operations.gates.comparison import ComparisonGates

logger = logging.getLogger(__name__)

_comparison = ComparisonGates()


class SortingGates:
    """Quantum sorting circuits using comparison networks."""

    def create_compare_and_swap(
        self,
        reg_a: List[cirq.Qid],
        reg_b: List[cirq.Qid],
    ) -> cirq.Circuit:
        """Compare two registers and swap if A > B.

        Args:
            reg_a: First value register.
            reg_b: Second value register.

        Returns:
            Conditional-swap circuit.
        """
        if len(reg_a) != len(reg_b):
            raise ValueError("Registers must be the same size")

        circuit = cirq.Circuit()
        cmp_qubit = cirq.NamedQubit("_cmp_swap")

        circuit += _comparison.create_comparator(reg_b, reg_a, cmp_qubit)
        circuit.append(cirq.X(cmp_qubit))

        for qa, qb in zip(reg_a, reg_b):
            circuit.append(cirq.SWAP(qa, qb).controlled_by(cmp_qubit))

        circuit.append(cirq.X(cmp_qubit))
        circuit += cirq.inverse(_comparison.create_comparator(reg_b, reg_a, cmp_qubit))

        return circuit

    def create_sorting_network(
        self,
        registers: List[List[cirq.Qid]],
    ) -> cirq.Circuit:
        """Batcher's odd-even merge sorting network.

        Each register represents one binary-encoded element. After execution
        the registers are sorted in ascending order.

        Args:
            registers: List of equal-width qubit registers.

        Returns:
            Sorting network circuit.
        """
        n = len(registers)
        circuit = cirq.Circuit()

        p = 1
        while p < n:
            k = p
            while k >= 1:
                for j in range(n):
                    partner = j ^ k
                    if partner > j and partner < n:
                        if (j & (2 * p)) == 0:
                            circuit += self.create_compare_and_swap(
                                registers[j], registers[partner]
                            )
                k //= 2
            p *= 2

        return circuit
