"""Composite DatabaseGates facade.

Preserves the original single-class API by delegating to the focused
submodules.  All existing code that does::

    from qndb.core.operations.quantum_gates import DatabaseGates

continues to work unchanged.
"""

import cirq
import logging
from typing import Dict, List, Optional

from qndb.core.operations.gates.oracle import OracleBuilder
from qndb.core.operations.gates.comparison import ComparisonGates
from qndb.core.operations.gates.arithmetic import ArithmeticGates
from qndb.core.operations.gates.transforms import TransformGates
from qndb.core.operations.gates.aggregation import AggregationGates
from qndb.core.operations.gates.sorting import SortingGates

logger = logging.getLogger(__name__)


class DatabaseGates:
    """Provides custom quantum gates optimised for database operations.

    This is a thin facade that delegates to the focused gate modules
    in :mod:`qndb.core.operations.gates`.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._oracle = OracleBuilder()
        self._comparison = ComparisonGates()
        self._arithmetic = ArithmeticGates()
        self._transforms = TransformGates()
        self._aggregation = AggregationGates()
        self._sorting = SortingGates()

    # -- Oracle / amplitude amplification ----------------------------------

    def create_oracle(self, pattern: str, target_qubits: List[cirq.Qid]) -> cirq.Circuit:
        return self._oracle.create_oracle(pattern, target_qubits)

    def create_amplitude_amplification(self, oracle_circuit: cirq.Circuit,
                                       target_qubits: List[cirq.Qid],
                                       iterations: int = 1) -> cirq.Circuit:
        return self._oracle.create_amplitude_amplification(oracle_circuit, target_qubits, iterations)

    def create_database_query_gate(self, key_qubits: List[cirq.Qid],
                                   value_qubits: List[cirq.Qid],
                                   entries: Dict[str, str]) -> cirq.Circuit:
        return self._oracle.create_database_query_gate(key_qubits, value_qubits, entries)

    # -- Comparison --------------------------------------------------------

    def create_equality_test(self, qubits1: List[cirq.Qid],
                             qubits2: List[cirq.Qid],
                             output_qubit: cirq.Qid) -> cirq.Circuit:
        return self._comparison.create_equality_test(qubits1, qubits2, output_qubit)

    def create_not_equal(self, qubits1: List[cirq.Qid],
                         qubits2: List[cirq.Qid],
                         output_qubit: cirq.Qid) -> cirq.Circuit:
        return self._comparison.create_not_equal(qubits1, qubits2, output_qubit)

    def create_comparator(self, qubits_a: List[cirq.Qid],
                          qubits_b: List[cirq.Qid],
                          output_qubit: cirq.Qid) -> cirq.Circuit:
        return self._comparison.create_comparator(qubits_a, qubits_b, output_qubit)

    def create_greater_than_equal(self, qubits_a: List[cirq.Qid],
                                  qubits_b: List[cirq.Qid],
                                  output_qubit: cirq.Qid) -> cirq.Circuit:
        return self._comparison.create_greater_than_equal(qubits_a, qubits_b, output_qubit)

    def create_less_than(self, qubits_a: List[cirq.Qid],
                         qubits_b: List[cirq.Qid],
                         output_qubit: cirq.Qid) -> cirq.Circuit:
        return self._comparison.create_less_than(qubits_a, qubits_b, output_qubit)

    def create_swap_test(self, qubits_a: List[cirq.Qid],
                         qubits_b: List[cirq.Qid],
                         control_qubit: cirq.Qid) -> cirq.Circuit:
        return self._comparison.create_swap_test(qubits_a, qubits_b, control_qubit)

    # -- Arithmetic --------------------------------------------------------

    def create_binary_adder(self, qubits_a: List[cirq.Qid],
                            qubits_b: List[cirq.Qid],
                            output_qubits: List[cirq.Qid]) -> cirq.Circuit:
        return self._arithmetic.create_binary_adder(qubits_a, qubits_b, output_qubits)

    def create_incrementer(self, qubits: List[cirq.Qid]) -> cirq.Circuit:
        return self._arithmetic.create_incrementer(qubits)

    # -- Transforms --------------------------------------------------------

    def create_qft(self, qubits: List[cirq.Qid], inverse: bool = False) -> cirq.Circuit:
        return self._transforms.create_qft(qubits, inverse)

    def create_phase_estimation_circuit(self, target_qubits: List[cirq.Qid],
                                        phase_qubits: List[cirq.Qid],
                                        unitary_circuit: cirq.Circuit) -> cirq.Circuit:
        return self._transforms.create_phase_estimation_circuit(target_qubits, phase_qubits, unitary_circuit)

    # -- Aggregation -------------------------------------------------------

    def create_quantum_count(self, flag_qubits: List[cirq.Qid],
                             count_qubits: List[cirq.Qid]) -> cirq.Circuit:
        return self._aggregation.create_quantum_count(flag_qubits, count_qubits)

    def create_quantum_sum(self, value_registers: List[List[cirq.Qid]],
                           sum_qubits: List[cirq.Qid]) -> cirq.Circuit:
        return self._aggregation.create_quantum_sum(value_registers, sum_qubits)

    def create_quantum_avg(self, value_registers: List[List[cirq.Qid]],
                           sum_qubits: List[cirq.Qid],
                           count_qubits: List[cirq.Qid],
                           flag_qubits: Optional[List[cirq.Qid]] = None) -> cirq.Circuit:
        return self._aggregation.create_quantum_avg(value_registers, sum_qubits, count_qubits, flag_qubits)

    # -- Sorting -----------------------------------------------------------

    def create_compare_and_swap(self, reg_a: List[cirq.Qid],
                                reg_b: List[cirq.Qid]) -> cirq.Circuit:
        return self._sorting.create_compare_and_swap(reg_a, reg_b)

    def create_sorting_network(self, registers: List[List[cirq.Qid]]) -> cirq.Circuit:
        return self._sorting.create_sorting_network(registers)
