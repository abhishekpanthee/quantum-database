"""Oracle circuit construction for pattern matching and database lookups."""

import cirq
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class OracleBuilder:
    """Builds quantum oracle circuits for pattern matching and key-value lookups."""

    def create_oracle(self, pattern: str, target_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """Create a quantum oracle that marks states matching *pattern*.

        Args:
            pattern: Binary string to match.
            target_qubits: Qubits to apply the oracle to.

        Returns:
            Oracle circuit.
        """
        if len(pattern) != len(target_qubits):
            raise ValueError("Pattern length must match number of qubits")

        oracle_circuit = cirq.Circuit()

        for i, bit in enumerate(pattern):
            if bit == '0':
                oracle_circuit.append(cirq.X(target_qubits[i]))

        if len(target_qubits) > 1:
            oracle_circuit.append(cirq.Z.controlled(len(target_qubits) - 1)(*target_qubits))
        else:
            oracle_circuit.append(cirq.Z(target_qubits[0]))

        for i, bit in enumerate(pattern):
            if bit == '0':
                oracle_circuit.append(cirq.X(target_qubits[i]))

        return oracle_circuit

    def create_amplitude_amplification(
        self,
        oracle_circuit: cirq.Circuit,
        target_qubits: List[cirq.Qid],
        iterations: int = 1,
    ) -> cirq.Circuit:
        """Create an amplitude amplification (Grover diffusion) circuit.

        Args:
            oracle_circuit: Oracle marking target states.
            target_qubits: Qubits to amplify.
            iterations: Number of Grover iterations.

        Returns:
            Amplitude amplification circuit.
        """
        amp_circuit = cirq.Circuit()
        amp_circuit.append(cirq.H.on_each(*target_qubits))

        for _ in range(iterations):
            amp_circuit += oracle_circuit

            amp_circuit.append(cirq.H.on_each(*target_qubits))
            amp_circuit.append(cirq.X.on_each(*target_qubits))

            if len(target_qubits) > 1:
                amp_circuit.append(cirq.Z.controlled(len(target_qubits) - 1)(*target_qubits))
            else:
                amp_circuit.append(cirq.Z(target_qubits[0]))

            amp_circuit.append(cirq.X.on_each(*target_qubits))
            amp_circuit.append(cirq.H.on_each(*target_qubits))

        return amp_circuit

    def create_database_query_gate(
        self,
        key_qubits: List[cirq.Qid],
        value_qubits: List[cirq.Qid],
        entries: Dict[str, str],
    ) -> cirq.Circuit:
        """Create a circuit for database key-value lookups.

        Args:
            key_qubits: Qubits for the key register.
            value_qubits: Qubits for the value register.
            entries: Database entries as ``{binary_key: binary_value}``.

        Returns:
            Query circuit.
        """
        if not entries:
            return cirq.Circuit()

        key_length = len(next(iter(entries.keys())))
        value_length = len(next(iter(entries.values())))

        if len(key_qubits) != key_length or len(value_qubits) != value_length:
            raise ValueError("Qubit register sizes do not match entry sizes")

        query_circuit = cirq.Circuit()

        for key_str, value_str in entries.items():
            controls: List[cirq.Qid] = []
            for i, bit in enumerate(key_str):
                if bit == '0':
                    query_circuit.append(cirq.X(key_qubits[i]))
                controls.append(key_qubits[i])

            for i, bit in enumerate(value_str):
                if bit == '1':
                    query_circuit.append(cirq.X(value_qubits[i]).controlled_by(*controls))

            for i, bit in enumerate(key_str):
                if bit == '0':
                    query_circuit.append(cirq.X(key_qubits[i]))

        return query_circuit
