"""
Custom quantum gates implementation for quantum database operations.
"""

import cirq
import numpy as np
from typing import List, Dict, Tuple, Optional, Union, Sequence, Any
import logging


class DatabaseGates:
    """
    Provides custom quantum gates optimized for database operations.
    """
    
    def __init__(self):
        """Initialize the database gates library."""
        self.logger = logging.getLogger(__name__)
        
    def create_oracle(self, pattern: str, target_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Create a quantum oracle for pattern matching.
        
        Args:
            pattern (str): Binary pattern to match
            target_qubits (List[cirq.Qid]): Qubits to apply the oracle to
            
        Returns:
            cirq.Circuit: Oracle circuit
        """
        if len(pattern) != len(target_qubits):
            self.logger.error(f"Pattern length ({len(pattern)}) must match number of qubits ({len(target_qubits)})")
            raise ValueError("Pattern length must match number of qubits")
            
        oracle_circuit = cirq.Circuit()
        
        # Apply X gates to qubits that should be 0 in the pattern
        for i, bit in enumerate(pattern):
            if bit == '0':
                oracle_circuit.append(cirq.X(target_qubits[i]))
                
        # Multi-controlled Z gate to mark the target pattern
        if len(target_qubits) > 1:
            oracle_circuit.append(cirq.Z.controlled(len(target_qubits) - 1)(*target_qubits))
        else:
            oracle_circuit.append(cirq.Z(target_qubits[0]))
            
        # Undo the X gates
        for i, bit in enumerate(pattern):
            if bit == '0':
                oracle_circuit.append(cirq.X(target_qubits[i]))
                
        return oracle_circuit
    
    def create_amplitude_amplification(self, oracle_circuit: cirq.Circuit, 
                                      target_qubits: List[cirq.Qid],
                                      iterations: int = 1) -> cirq.Circuit:
        """
        Create a quantum amplitude amplification circuit.
        
        Args:
            oracle_circuit (cirq.Circuit): Oracle to mark target states
            target_qubits (List[cirq.Qid]): Qubits to apply amplitude amplification to
            iterations (int): Number of Grover iterations
            
        Returns:
            cirq.Circuit: Amplitude amplification circuit
        """
        # Create circuit for amplitude amplification
        amp_circuit = cirq.Circuit()
        
        # Initial superposition
        amp_circuit.append(cirq.H.on_each(*target_qubits))
        
        # Repeat the amplitude amplification steps
        for _ in range(iterations):
            # Oracle to mark target states
            amp_circuit += oracle_circuit
            
            # Diffusion operator (reflection about the average)
            amp_circuit.append(cirq.H.on_each(*target_qubits))
            amp_circuit.append(cirq.X.on_each(*target_qubits))
            
            # Multi-controlled Z gate
            if len(target_qubits) > 1:
                amp_circuit.append(cirq.Z.controlled(len(target_qubits) - 1)(*target_qubits))
            else:
                amp_circuit.append(cirq.Z(target_qubits[0]))
                
            # Undo X and H gates
            amp_circuit.append(cirq.X.on_each(*target_qubits))
            amp_circuit.append(cirq.H.on_each(*target_qubits))
            
        return amp_circuit
    
    def create_equality_test(self, qubits1: List[cirq.Qid], 
                           qubits2: List[cirq.Qid],
                           output_qubit: cirq.Qid) -> cirq.Circuit:
        """
        Create a quantum circuit that tests equality between two qubit registers.
        
        Args:
            qubits1 (List[cirq.Qid]): First qubit register
            qubits2 (List[cirq.Qid]): Second qubit register
            output_qubit (cirq.Qid): Output qubit (will be |1⟩ if equal)
            
        Returns:
            cirq.Circuit: Equality test circuit
        """
        if len(qubits1) != len(qubits2):
            self.logger.error("Qubit registers must be the same size for equality test")
            raise ValueError("Qubit registers must be the same size")
            
        # Initialize circuit
        eq_circuit = cirq.Circuit()
        
        # Prepare output qubit in |1⟩ state
        eq_circuit.append(cirq.X(output_qubit))
        
        # For each pair of qubits, apply CNOT to check if they're different
        for q1, q2 in zip(qubits1, qubits2):
            # Apply CNOT to check if qubits are different
            eq_circuit.append(cirq.CNOT(q1, q2))
            
            # If they're different, flip the output qubit
            eq_circuit.append(cirq.CNOT(q2, output_qubit))
            
            # Undo the first CNOT to restore qubits
            eq_circuit.append(cirq.CNOT(q1, q2))
            
        return eq_circuit
    
    def create_binary_adder(self, qubits_a: List[cirq.Qid], 
                          qubits_b: List[cirq.Qid],
                          output_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Create a quantum circuit for binary addition.
        
        Args:
            qubits_a (List[cirq.Qid]): First qubit register (input)
            qubits_b (List[cirq.Qid]): Second qubit register (input)
            output_qubits (List[cirq.Qid]): Output qubit register
            
        Returns:
            cirq.Circuit: Binary adder circuit
        """
        if len(qubits_a) != len(qubits_b) or len(output_qubits) < len(qubits_a) + 1:
            self.logger.error("Invalid qubit registers sizes for binary adder")
            raise ValueError("Invalid qubit registers sizes for binary adder")
            
        # Initialize circuit
        adder_circuit = cirq.Circuit()
        
        # We need one carry qubit
        carry_qubit = cirq.LineQubit(-1)  # Temporary qubit
        
        # Implement binary adder with ripple carry
        for i in range(len(qubits_a)):
            # Half adder for the first bit
            if i == 0:
                # XOR of input bits for sum bit
                adder_circuit.append(cirq.CNOT(qubits_a[i], output_qubits[i]))
                adder_circuit.append(cirq.CNOT(qubits_b[i], output_qubits[i]))
                
                # AND of input bits for carry bit
                adder_circuit.append(cirq.CNOT(qubits_a[i], carry_qubit))
                adder_circuit.append(cirq.CNOT(qubits_b[i], carry_qubit))
                adder_circuit.append(cirq.TOFFOLI(qubits_a[i], qubits_b[i], carry_qubit))
            else:
                # Full adder for subsequent bits
                # XOR three inputs for sum bit
                adder_circuit.append(cirq.CNOT(qubits_a[i], output_qubits[i]))
                adder_circuit.append(cirq.CNOT(qubits_b[i], output_qubits[i]))
                adder_circuit.append(cirq.CNOT(carry_qubit, output_qubits[i]))
                
                # Calculate new carry
                adder_circuit.append(cirq.TOFFOLI(qubits_a[i], qubits_b[i], output_qubits[i+1]))
                adder_circuit.append(cirq.TOFFOLI(qubits_a[i], carry_qubit, output_qubits[i+1]))
                adder_circuit.append(cirq.TOFFOLI(qubits_b[i], carry_qubit, output_qubits[i+1]))
                
                # Reset carry for next bit
                adder_circuit.append(cirq.CNOT(carry_qubit, output_qubits[i+1]))
                
                # Update carry qubit
                adder_circuit.append(cirq.CNOT(carry_qubit, output_qubits[i+1]))
                
        # Copy final carry to the most significant bit of output
        adder_circuit.append(cirq.CNOT(carry_qubit, output_qubits[-1]))
                
        return adder_circuit
    
    def create_comparator(self, qubits_a: List[cirq.Qid],
                        qubits_b: List[cirq.Qid],
                        output_qubit: cirq.Qid) -> cirq.Circuit:
        """
        Create a quantum circuit that compares two registers (A ≥ B).
        
        Args:
            qubits_a (List[cirq.Qid]): First qubit register
            qubits_b (List[cirq.Qid]): Second qubit register
            output_qubit (cirq.Qid): Output qubit (|1⟩ if A ≥ B)
            
        Returns:
            cirq.Circuit: Comparator circuit
        """
        if len(qubits_a) != len(qubits_b):
            self.logger.error("Qubit registers must be the same size for comparison")
            raise ValueError("Qubit registers must be the same size")
            
        # Initialize circuit
        comp_circuit = cirq.Circuit()
        
        n = len(qubits_a)
        
        # Create temporary qubits for intermediate results
        temp_qubits = [cirq.LineQubit(-(i+2)) for i in range(n)]
        
        # Start with output qubit in |0⟩ state
        
        # Working from most significant bit to least
        for i in range(n-1, -1, -1):
            # Check if A[i] is 1 and B[i] is 0
            comp_circuit.append(cirq.X(qubits_b[i]))
            comp_circuit.append(cirq.TOFFOLI(qubits_a[i], qubits_b[i], temp_qubits[i]))
            comp_circuit.append(cirq.X(qubits_b[i]))
            
            # If A[i] > B[i] and no previous bit has determined the result, set output to 1
            if i == n-1:
                comp_circuit.append(cirq.CNOT(temp_qubits[i], output_qubit))
            else:
                # If this bit has A > B and all more significant bits were equal, set output
                equal_bits_control = temp_qubits[i+1:n]
                if equal_bits_control:
                    comp_circuit.append(cirq.X.on_each(*equal_bits_control))
                    comp_circuit.append(
                        cirq.X(output_qubit).controlled_by(temp_qubits[i], *equal_bits_control)
                    )
                    comp_circuit.append(cirq.X.on_each(*equal_bits_control))
                
            # Check if A[i] equals B[i]
            comp_circuit.append(cirq.CNOT(qubits_a[i], temp_qubits[i]))
            comp_circuit.append(cirq.CNOT(qubits_b[i], temp_qubits[i]))
            comp_circuit.append(cirq.X(temp_qubits[i]))
                
        return comp_circuit
    
    def create_swap_test(self, qubits_a: List[cirq.Qid],
                       qubits_b: List[cirq.Qid],
                       control_qubit: cirq.Qid) -> cirq.Circuit:
        """
        Create a SWAP test circuit to measure similarity between quantum states.
        
        Args:
            qubits_a (List[cirq.Qid]): First qubit register
            qubits_b (List[cirq.Qid]): Second qubit register
            control_qubit (cirq.Qid): Control qubit
            
        Returns:
            cirq.Circuit: SWAP test circuit
        """
        if len(qubits_a) != len(qubits_b):
            self.logger.error("Qubit registers must be the same size for SWAP test")
            raise ValueError("Qubit registers must be the same size")
            
        # Initialize circuit
        swap_circuit = cirq.Circuit()
        
        # Apply Hadamard to control qubit
        swap_circuit.append(cirq.H(control_qubit))
        
        # Apply controlled-SWAP operations
        for a, b in zip(qubits_a, qubits_b):
            swap_circuit.append(cirq.SWAP(a, b).controlled_by(control_qubit))
            
        # Apply Hadamard to control qubit again
        swap_circuit.append(cirq.H(control_qubit))
        
        return swap_circuit
    
    def create_qft(self, qubits: List[cirq.Qid], inverse: bool = False) -> cirq.Circuit:
        """
        Create a Quantum Fourier Transform circuit.
        
        Args:
            qubits (List[cirq.Qid]): Qubits to apply QFT to
            inverse (bool): Whether to create inverse QFT
            
        Returns:
            cirq.Circuit: QFT circuit
        """
        n = len(qubits)
        qft_circuit = cirq.Circuit()
        
        if inverse:
            # Inverse QFT
            # Reverse the qubits for easier implementation
            qubits_rev = list(reversed(qubits))
            
            for i in range(n):
                # Apply inverse phase rotations
                for j in range(i):
                    angle = -2 * np.pi / (2 ** (i - j + 1))
                    qft_circuit.append(cirq.CZ(qubits_rev[j], qubits_rev[i]) ** (angle / np.pi))
                    
                # Apply H gate
                qft_circuit.append(cirq.H(qubits_rev[i]))
                
        else:
            # Forward QFT
            for i in range(n):
                # Apply H gate
                qft_circuit.append(cirq.H(qubits[i]))
                
                # Apply controlled phase rotations
                for j in range(i + 1, n):
                    angle = 2 * np.pi / (2 ** (j - i + 1))
                    qft_circuit.append(cirq.CZ(qubits[i], qubits[j]) ** (angle / np.pi))
                    
            # Reverse the order of qubits (optional)
            # This is often done in standard QFT but may not be necessary for all applications
            # qft_circuit.append(cirq.SWAP(qubits[i], qubits[n-i-1]) for i in range(n // 2))
                
        return qft_circuit
    
    def create_incrementer(self, qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Create a quantum circuit that increments a register by 1.
        
        Args:
            qubits (List[cirq.Qid]): Qubits representing the register
            
        Returns:
            cirq.Circuit: Incrementer circuit
        """
        # Initialize circuit
        inc_circuit = cirq.Circuit()
        
        # Apply X gates to create a cascade
        # In reverse order (from least significant to most significant bit)
        for i in range(len(qubits)-1, -1, -1):
            # Apply X gates to all less significant qubits
            control_qubits = qubits[i+1:] if i < len(qubits)-1 else []
            
            if control_qubits:
                inc_circuit.append(cirq.X(qubits[i]).controlled_by(*control_qubits))
            else:
                inc_circuit.append(cirq.X(qubits[i]))
                
        return inc_circuit
    
    def create_database_query_gate(self, key_qubits: List[cirq.Qid],
                                 value_qubits: List[cirq.Qid],
                                 entries: Dict[str, str]) -> cirq.Circuit:
        """
        Create a quantum circuit for database key-value lookups.
        
        Args:
            key_qubits (List[cirq.Qid]): Qubits for the key register
            value_qubits (List[cirq.Qid]): Qubits for the value register
            entries (Dict[str, str]): Database entries as binary strings
            
        Returns:
            cirq.Circuit: Database query circuit
        """
        if not entries:
            self.logger.warning("Empty database entries provided")
            return cirq.Circuit()
            
        # Check that all keys and values have consistent lengths
        key_length = len(next(iter(entries.keys())))
        value_length = len(next(iter(entries.values())))
        
        if len(key_qubits) != key_length or len(value_qubits) != value_length:
            self.logger.error("Qubit register sizes do not match entry sizes")
            raise ValueError("Qubit register sizes do not match entry sizes")
            
        # Create circuit
        query_circuit = cirq.Circuit()
        
        # For each database entry, create a controlled operation
        for key_str, value_str in entries.items():
            # Create controls based on the key
            controls = []
            for i, bit in enumerate(key_str):
                if bit == '0':
                    # Apply X before and after to condition on |0⟩
                    query_circuit.append(cirq.X(key_qubits[i]))
                    controls.append(key_qubits[i])
                else:
                    # Condition on |1⟩
                    controls.append(key_qubits[i])
                    
            # For each value bit that should be 1, apply a controlled-X
            for i, bit in enumerate(value_str):
                if bit == '1':
                    query_circuit.append(cirq.X(value_qubits[i]).controlled_by(*controls))
                    
            # Undo the X gates applied for |0⟩ controls
            for i, bit in enumerate(key_str):
                if bit == '0':
                    query_circuit.append(cirq.X(key_qubits[i]))
                    
        return query_circuit
    
    def create_phase_estimation_circuit(self, target_qubits: List[cirq.Qid],
                                      phase_qubits: List[cirq.Qid],
                                      unitary_circuit: cirq.Circuit) -> cirq.Circuit:
        """
        Create a quantum phase estimation circuit.
        
        Args:
            target_qubits (List[cirq.Qid]): Target qubits for the unitary
            phase_qubits (List[cirq.Qid]): Qubits to store the phase
            unitary_circuit (cirq.Circuit): Circuit implementing the unitary
            
        Returns:
            cirq.Circuit: Phase estimation circuit
        """
        # Initialize circuit
        qpe_circuit = cirq.Circuit()
        
        # Apply Hadamard to all phase qubits
        qpe_circuit.append(cirq.H.on_each(*phase_qubits))
        
        # Apply controlled-U operations
        for i, phase_qubit in enumerate(phase_qubits):
            # Apply U^(2^i) controlled by the current phase qubit
            power = 2 ** i
            
            # Create controlled version of the unitary
            for _ in range(power):
                # Add controlled version of the unitary circuit
                for moment in unitary_circuit:
                    controlled_moment = cirq.Moment(
                        op.controlled_by(phase_qubit) for op in moment
                    )
                    qpe_circuit.append(controlled_moment)
                    
        # Apply inverse QFT to phase register
        qpe_circuit += self.create_qft(phase_qubits, inverse=True)
        
        return qpe_circuit