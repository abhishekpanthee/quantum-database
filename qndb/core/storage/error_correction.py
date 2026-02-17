"""
Error Correction - Quantum error correction mechanisms for robust storage.
"""
import cirq
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

class QuantumErrorCorrection:
    """
    Implements quantum error correction codes for robust quantum data storage.
    """
    
    def __init__(self, code_type: str = "bit_flip"):
        """
        Initialize the error correction module.
        
        Args:
            code_type: Type of error correction code to use
                       ("bit_flip", "phase_flip", "shor", "steane")
        """
        self.code_type = code_type
    
    def encode_bit_flip(self, qubit: cirq.Qid, ancilla_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Encode a single qubit using the 3-qubit bit flip code.
        
        Args:
            qubit: Data qubit to encode
            ancilla_qubits: Two ancilla qubits for encoding
            
        Returns:
            Circuit that encodes the qubit
        """
        if len(ancilla_qubits) != 2:
            raise ValueError("Bit flip code requires exactly 2 ancilla qubits")
            
        circuit = cirq.Circuit()
        
        # Apply CNOT from data qubit to each ancilla
        circuit.append(cirq.CNOT(qubit, ancilla_qubits[0]))
        circuit.append(cirq.CNOT(qubit, ancilla_qubits[1]))
        
        return circuit
    
    def decode_bit_flip(self, 
                        data_qubits: List[cirq.Qid], 
                        target_qubit: cirq.Qid) -> cirq.Circuit:
        """
        Decode the 3-qubit bit flip code.
        
        Args:
            data_qubits: Three qubits containing the encoded data
            target_qubit: Qubit to store the decoded result
            
        Returns:
            Circuit that decodes the qubit
        """
        if len(data_qubits) != 3:
            raise ValueError("Bit flip decoding requires exactly 3 data qubits")
            
        circuit = cirq.Circuit()
        
        # Majority vote (simplified)
        # In a real quantum circuit, we would use ancilla qubits
        # to perform the majority vote and error correction
        
        # Apply Toffoli gate for the majority vote
        circuit.append(cirq.CCX(data_qubits[0], data_qubits[1], target_qubit))
        circuit.append(cirq.CNOT(data_qubits[0], target_qubit))
        circuit.append(cirq.CNOT(data_qubits[2], target_qubit))
        
        return circuit
    
    def encode_phase_flip(self, qubit: cirq.Qid, ancilla_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Encode a single qubit using the 3-qubit phase flip code.
        
        Args:
            qubit: Data qubit to encode
            ancilla_qubits: Two ancilla qubits for encoding
            
        Returns:
            Circuit that encodes the qubit
        """
        if len(ancilla_qubits) != 2:
            raise ValueError("Phase flip code requires exactly 2 ancilla qubits")
            
        circuit = cirq.Circuit()
        
        # Apply Hadamard to all qubits
        circuit.append(cirq.H(qubit))
        circuit.append(cirq.H(ancilla_qubits[0]))
        circuit.append(cirq.H(ancilla_qubits[1]))
        
        # Apply CNOT from data qubit to each ancilla
        circuit.append(cirq.CNOT(qubit, ancilla_qubits[0]))
        circuit.append(cirq.CNOT(qubit, ancilla_qubits[1]))
        
        # Apply Hadamard to all qubits again
        circuit.append(cirq.H(qubit))
        circuit.append(cirq.H(ancilla_qubits[0]))
        circuit.append(cirq.H(ancilla_qubits[1]))
        
        return circuit
    
    def decode_phase_flip(self, 
                         data_qubits: List[cirq.Qid], 
                         target_qubit: cirq.Qid) -> cirq.Circuit:
        """
        Decode the 3-qubit phase flip code.
        
        Args:
            data_qubits: Three qubits containing the encoded data
            target_qubit: Qubit to store the decoded result
            
        Returns:
            Circuit that decodes the qubit
        """
        if len(data_qubits) != 3:
            raise ValueError("Phase flip decoding requires exactly 3 data qubits")
            
        circuit = cirq.Circuit()
        
        # Apply Hadamard to all qubits
        circuit.append(cirq.H(data_qubits[0]))
        circuit.append(cirq.H(data_qubits[1]))
        circuit.append(cirq.H(data_qubits[2]))
        
        # Majority vote (similar to bit flip)
        circuit.append(cirq.CCX(data_qubits[0], data_qubits[1], target_qubit))
        circuit.append(cirq.CNOT(data_qubits[0], target_qubit))
        circuit.append(cirq.CNOT(data_qubits[2], target_qubit))
        
        # Apply final Hadamard
        circuit.append(cirq.H(target_qubit))
        
        return circuit
    
    def encode_shor(self, qubit: cirq.Qid, ancilla_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Encode a single qubit using Shor's 9-qubit code.
        
        Args:
            qubit: Data qubit to encode
            ancilla_qubits: Eight ancilla qubits for encoding
            
        Returns:
            Circuit that encodes the qubit
        """
        if len(ancilla_qubits) != 8:
            raise ValueError("Shor's code requires exactly 8 ancilla qubits")
            
        circuit = cirq.Circuit()
        
        # Group qubits for easier referencing
        qubits = [qubit] + ancilla_qubits
        
        # First level of encoding (phase flip code)
        circuit.append(cirq.H(qubits[0]))
        circuit.append(cirq.CNOT(qubits[0], qubits[3]))
        circuit.append(cirq.CNOT(qubits[0], qubits[6]))
        
        # Second level (bit flip code for each group)
        for i in range(0, 9, 3):
            if i < len(qubits):
                circuit.append(cirq.CNOT(qubits[i], qubits[i+1]))
                circuit.append(cirq.CNOT(qubits[i], qubits[i+2]))
        
        return circuit
    
    def encode_steane(self, qubit: cirq.Qid, ancilla_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Encode a single qubit using Steane's [7,1,3] code.

        The Steane code is the smallest CSS code that can correct an arbitrary
        single-qubit error.  It is based on the classical [7,4,3] Hamming code.

        Qubit ordering: qubits[0] = data, qubits[1..6] = ancillas.
        The logical |0⟩_L is the uniform superposition of even-weight codewords
        of the [7,4] Hamming code; |1⟩_L has odd-weight codewords.

        Stabilizer generators (X-type):
            X0 X2 X4 X6,  X1 X2 X5 X6,  X3 X4 X5 X6
        Stabilizer generators (Z-type):
            Z0 Z2 Z4 Z6,  Z1 Z2 Z5 Z6,  Z3 Z4 Z5 Z6

        Args:
            qubit: Data qubit to encode
            ancilla_qubits: Six ancilla qubits for encoding
            
        Returns:
            Circuit that encodes the qubit
        """
        if len(ancilla_qubits) != 6:
            raise ValueError("Steane's code requires exactly 6 ancilla qubits")
            
        circuit = cirq.Circuit()
        q = [qubit] + list(ancilla_qubits)  # q[0]..q[6]

        # --- Encode |ψ⟩ = α|0⟩ + β|1⟩ into the [7,1,3] Steane code ---
        # Step 1: Spread the data qubit across the code block
        circuit.append(cirq.CNOT(q[0], q[3]))
        circuit.append(cirq.CNOT(q[0], q[5]))

        # Step 2: Create superposition for the X stabilizers
        circuit.append(cirq.H(q[1]))
        circuit.append(cirq.H(q[2]))
        circuit.append(cirq.H(q[4]))

        # Step 3: Entangle according to the Hamming parity-check matrix
        # H = [[1,0,1,0,1,0,1],
        #      [0,1,1,0,0,1,1],
        #      [0,0,0,1,1,1,1]]
        circuit.append(cirq.CNOT(q[1], q[0]))
        circuit.append(cirq.CNOT(q[1], q[2]))
        circuit.append(cirq.CNOT(q[1], q[6]))

        circuit.append(cirq.CNOT(q[2], q[0]))
        circuit.append(cirq.CNOT(q[2], q[5]))
        circuit.append(cirq.CNOT(q[2], q[6]))

        circuit.append(cirq.CNOT(q[4], q[0]))
        circuit.append(cirq.CNOT(q[4], q[3]))
        circuit.append(cirq.CNOT(q[4], q[5]))
        circuit.append(cirq.CNOT(q[4], q[6]))
        
        return circuit
    
    def encode(self, qubit: cirq.Qid, ancilla_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Encode a qubit using the selected error correction code.
        
        Args:
            qubit: Data qubit to encode
            ancilla_qubits: Ancilla qubits for encoding
            
        Returns:
            Circuit that encodes the qubit
        """
        if self.code_type == "bit_flip":
            return self.encode_bit_flip(qubit, ancilla_qubits)
        elif self.code_type == "phase_flip":
            return self.encode_phase_flip(qubit, ancilla_qubits)
        elif self.code_type == "shor":
            return self.encode_shor(qubit, ancilla_qubits)
        elif self.code_type == "steane":
            return self.encode_steane(qubit, ancilla_qubits)
        else:
            raise ValueError(f"Unknown error correction code: {self.code_type}")
    
    def detect_errors(self, qubits: List[cirq.Qid], syndrome_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Create a circuit to detect errors in encoded qubits.
        
        Args:
            qubits: Data qubits with potential errors
            syndrome_qubits: Qubits to store the error syndromes
            
        Returns:
            Circuit that performs error detection
        """
        if self.code_type == "bit_flip":
            return self._detect_bit_flip_errors(qubits, syndrome_qubits)
        elif self.code_type == "phase_flip":
            return self._detect_phase_flip_errors(qubits, syndrome_qubits)
        else:
            # Unsupported code type — return empty circuit
            return cirq.Circuit()
            
    def _detect_bit_flip_errors(self, qubits: List[cirq.Qid], syndrome_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """Detect bit flip errors."""
        if len(qubits) != 3 or len(syndrome_qubits) != 2:
            raise ValueError("Bit flip error detection requires 3 data qubits and 2 syndrome qubits")
            
        circuit = cirq.Circuit()
        
        # Compute the parity checks
        circuit.append(cirq.CNOT(qubits[0], syndrome_qubits[0]))
        circuit.append(cirq.CNOT(qubits[1], syndrome_qubits[0]))
        
        circuit.append(cirq.CNOT(qubits[1], syndrome_qubits[1]))
        circuit.append(cirq.CNOT(qubits[2], syndrome_qubits[1]))
        
        # Measure the syndrome qubits
        circuit.append(cirq.measure(syndrome_qubits[0], syndrome_qubits[1], key='syndrome'))
        
        return circuit
        
    def _detect_phase_flip_errors(self, qubits: List[cirq.Qid], syndrome_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """Detect phase flip errors."""
        if len(qubits) != 3 or len(syndrome_qubits) != 2:
            raise ValueError("Phase flip error detection requires 3 data qubits and 2 syndrome qubits")
            
        circuit = cirq.Circuit()
        
        # Apply Hadamard to all data qubits
        circuit.append(cirq.H.on_each(*qubits))
        
        # Compute the parity checks (same as bit flip error detection)
        circuit.append(cirq.CNOT(qubits[0], syndrome_qubits[0]))
        circuit.append(cirq.CNOT(qubits[1], syndrome_qubits[0]))
        
        circuit.append(cirq.CNOT(qubits[1], syndrome_qubits[1]))
        circuit.append(cirq.CNOT(qubits[2], syndrome_qubits[1]))
        
        # Measure the syndrome qubits
        circuit.append(cirq.measure(syndrome_qubits[0], syndrome_qubits[1], key='syndrome'))
        
        # Apply Hadamard to all data qubits again
        circuit.append(cirq.H.on_each(*qubits))
        
        return circuit
    
    def correct_errors(self, qubits: List[cirq.Qid], syndrome: int) -> cirq.Circuit:
        """
        Create a circuit to correct errors based on the syndrome.
        
        Args:
            qubits: Data qubits to correct
            syndrome: Error syndrome value
            
        Returns:
            Circuit that performs error correction
        """
        circuit = cirq.Circuit()
        
        if self.code_type == "bit_flip":
            # Apply X gate to the qubit with an error
            if syndrome == 1:  # 01 syndrome
                circuit.append(cirq.X(qubits[0]))
            elif syndrome == 2:  # 10 syndrome
                circuit.append(cirq.X(qubits[2]))
            elif syndrome == 3:  # 11 syndrome
                circuit.append(cirq.X(qubits[1]))
        
        elif self.code_type == "phase_flip":
            # Apply Z gate to the qubit with an error
            if syndrome == 1:  # 01 syndrome
                circuit.append(cirq.Z(qubits[0]))
            elif syndrome == 2:  # 10 syndrome
                circuit.append(cirq.Z(qubits[2]))
            elif syndrome == 3:  # 11 syndrome
                circuit.append(cirq.Z(qubits[1]))
        
        # Other codes would have more complex syndrome correction mappings
        
        return circuit
    
    def apply_bit_flip_code(self, circuit: cirq.Circuit, qubits: List[cirq.Qid]) -> Tuple[cirq.Circuit, List[cirq.Qid]]:
        """
        Apply bit-flip error correction code to a circuit.
        
        Args:
            circuit: Original circuit
            qubits: List of qubits to encode
            
        Returns:
            Tuple of (protected circuit, protected qubits)
        """
        # Create a new circuit
        protected_circuit = circuit.copy()
        
        # Create new qubits for the encoding
        protected_qubits = []
        
        for qubit in qubits:
            # Each logical qubit is encoded into 3 physical qubits
            q0 = qubit
            q1 = cirq.LineQubit(len(protected_qubits) + len(qubits))
            q2 = cirq.LineQubit(len(protected_qubits) + len(qubits) + 1)
            
            # Encode using the bit-flip code
            protected_circuit.append(cirq.CNOT(q0, q1))
            protected_circuit.append(cirq.CNOT(q0, q2))
            
            # Add to protected qubits list
            protected_qubits.extend([q0, q1, q2])
        
        return protected_circuit, protected_qubits

    def apply_phase_flip_code(self, circuit: cirq.Circuit, qubits: List[cirq.Qid]) -> Tuple[cirq.Circuit, List[cirq.Qid]]:
        """
        Apply phase-flip error correction code to a circuit.
        
        Args:
            circuit: Original circuit
            qubits: List of qubits to encode
            
        Returns:
            Tuple of (protected circuit, protected qubits)
        """
        # Create a new circuit
        protected_circuit = circuit.copy()
        
        # Create new qubits for the encoding
        protected_qubits = []
        
        for qubit in qubits:
            # Each logical qubit is encoded into 3 physical qubits
            q0 = qubit
            q1 = cirq.LineQubit(len(protected_qubits) + len(qubits))
            q2 = cirq.LineQubit(len(protected_qubits) + len(qubits) + 1)
            
            # Encode using the phase-flip code (which is like bit-flip in Hadamard basis)
            # First Hadamard transform
            protected_circuit.append(cirq.H(q0))
            protected_circuit.append(cirq.H(q1))
            protected_circuit.append(cirq.H(q2))
            
            # Then standard bit-flip encoding
            protected_circuit.append(cirq.CNOT(q0, q1))
            protected_circuit.append(cirq.CNOT(q0, q2))
            
            # Final Hadamard transform
            protected_circuit.append(cirq.H(q0))
            protected_circuit.append(cirq.H(q1))
            protected_circuit.append(cirq.H(q2))
            
            # Add to protected qubits list
            protected_qubits.extend([q0, q1, q2])
        
        return protected_circuit, protected_qubits

    def detect_and_correct_errors(self, circuit: cirq.Circuit, qubits: List[cirq.Qid], 
                                  code_type: str = "bit_flip") -> cirq.Circuit:
        """
        Create a circuit that detects and corrects errors.
        
        Args:
            circuit: Circuit with potential errors
            qubits: Protected qubits
            code_type: Type of error correction code
            
        Returns:
            Circuit with error correction
        """
        # Create syndrome measurement circuit
        corrected_circuit = circuit.copy()
        
        # Add syndrome qubits
        syndrome_qubits = [
            cirq.LineQubit(len(circuit.all_qubits()) + i)
            for i in range(len(qubits) // 3 * 2)  # 2 syndrome qubits per logical qubit
        ]
        
        # Apply appropriate syndrome extraction based on code type
        if code_type == "bit_flip":
            # For each logical qubit (every 3 physical qubits)
            for i in range(0, len(qubits), 3):
                if i + 2 < len(qubits):
                    # Create syndrome circuit for this logical qubit
                    s0 = syndrome_qubits[i // 3 * 2]
                    s1 = syndrome_qubits[i // 3 * 2 + 1]
                    
                    # Measure syndromes
                    corrected_circuit.append(cirq.CNOT(qubits[i], s0))
                    corrected_circuit.append(cirq.CNOT(qubits[i+1], s0))
                    corrected_circuit.append(cirq.CNOT(qubits[i+1], s1))
                    corrected_circuit.append(cirq.CNOT(qubits[i+2], s1))
                    
                    # Add correction operations based on syndromes
                    corrected_circuit.append(cirq.X(qubits[i]).controlled_by(s0, s1))
                    corrected_circuit.append(cirq.X(qubits[i+1]).controlled_by(s1))
                    corrected_circuit.append(cirq.X(qubits[i+2]).controlled_by(s0))
        
        elif code_type == "phase_flip":
            # Similar to bit flip but in Hadamard basis
            for i in range(0, len(qubits), 3):
                if i + 2 < len(qubits):
                    # Apply Hadamard to change to X basis
                    corrected_circuit.append(cirq.H.on_each(qubits[i], qubits[i+1], qubits[i+2]))
                    
                    # Create syndrome circuit for this logical qubit
                    s0 = syndrome_qubits[i // 3 * 2]
                    s1 = syndrome_qubits[i // 3 * 2 + 1]
                    
                    # Measure syndromes
                    corrected_circuit.append(cirq.CNOT(qubits[i], s0))
                    corrected_circuit.append(cirq.CNOT(qubits[i+1], s0))
                    corrected_circuit.append(cirq.CNOT(qubits[i+1], s1))
                    corrected_circuit.append(cirq.CNOT(qubits[i+2], s1))
                    
                    # Add correction operations based on syndromes
                    corrected_circuit.append(cirq.X(qubits[i]).controlled_by(s0, s1))
                    corrected_circuit.append(cirq.X(qubits[i+1]).controlled_by(s1))
                    corrected_circuit.append(cirq.X(qubits[i+2]).controlled_by(s0))
                    
                    # Apply Hadamard to return to Z basis
                    corrected_circuit.append(cirq.H.on_each(qubits[i], qubits[i+1], qubits[i+2]))
        
        return corrected_circuit

    def create_syndrome_circuit(self, circuit: cirq.Circuit, qubits: List[cirq.Qid], 
                               code_type: str = "bit_flip") -> cirq.Circuit:
        """
        Create a circuit with syndrome measurements.
        
        Args:
            circuit: Original circuit
            qubits: Protected qubits
            code_type: Type of error correction code
            
        Returns:
            Circuit with syndrome measurements
        """
        syndrome_circuit = circuit.copy()
        
        # Add syndrome qubits
        syndrome_qubits = [
            cirq.LineQubit(len(circuit.all_qubits()) + i)
            for i in range(len(qubits) // 3 * 2)  # 2 syndrome qubits per logical qubit
        ]
        
        # For each logical qubit (3 physical qubits)
        for i in range(0, len(qubits), 3):
            if i + 2 < len(qubits):
                # Get syndrome qubits for this logical qubit
                s0 = syndrome_qubits[i // 3 * 2]
                s1 = syndrome_qubits[i // 3 * 2 + 1]
                
                if code_type == "bit_flip":
                    # Initialize syndrome qubits
                    syndrome_circuit.append(cirq.X.on_each(s0, s1))
                    syndrome_circuit.append(cirq.H.on_each(s0, s1))
                    
                    # Measure parity
                    syndrome_circuit.append(cirq.CNOT(qubits[i], s0))
                    syndrome_circuit.append(cirq.CNOT(qubits[i+1], s0))
                    syndrome_circuit.append(cirq.CNOT(qubits[i+1], s1))
                    syndrome_circuit.append(cirq.CNOT(qubits[i+2], s1))
                    
                    # Measure syndrome
                    syndrome_circuit.append(cirq.measure(s0, s1, key=f'syndrome_{i}'))
                    
                elif code_type == "phase_flip":
                    # Transform to X-basis
                    syndrome_circuit.append(cirq.H.on_each(qubits[i], qubits[i+1], qubits[i+2]))
                    
                    # Initialize syndrome qubits
                    syndrome_circuit.append(cirq.X.on_each(s0, s1))
                    syndrome_circuit.append(cirq.H.on_each(s0, s1))
                    
                    # Measure parity
                    syndrome_circuit.append(cirq.CNOT(qubits[i], s0))
                    syndrome_circuit.append(cirq.CNOT(qubits[i+1], s0))
                    syndrome_circuit.append(cirq.CNOT(qubits[i+1], s1))
                    syndrome_circuit.append(cirq.CNOT(qubits[i+2], s1))
                    
                    # Measure syndrome
                    syndrome_circuit.append(cirq.measure(s0, s1, key=f'syndrome_{i}'))
                    
                    # Transform back to Z-basis
                    syndrome_circuit.append(cirq.H.on_each(qubits[i], qubits[i+1], qubits[i+2]))
        
        return syndrome_circuit

    # ------------------------------------------------------------------
    # Steane [7,1,3] stabilizer syndrome measurement
    # ------------------------------------------------------------------

    def detect_steane_errors(self, code_qubits: List[cirq.Qid],
                             syndrome_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """Measure the six stabiliser generators of the Steane code.

        X-stabilisers:  X0X2X4X6, X1X2X5X6, X3X4X5X6
        Z-stabilisers:  Z0Z2Z4Z6, Z1Z2Z5Z6, Z3Z4Z5Z6

        Each stabiliser is measured non-destructively via an ancilla qubit.

        Args:
            code_qubits: Seven code qubits (q0..q6)
            syndrome_qubits: Six syndrome ancilla qubits

        Returns:
            Circuit with syndrome measurements
        """
        if len(code_qubits) != 7:
            raise ValueError("Steane code requires exactly 7 code qubits")
        if len(syndrome_qubits) < 6:
            raise ValueError("Need at least 6 syndrome qubits")

        q = code_qubits
        s = syndrome_qubits
        circuit = cirq.Circuit()

        # X-type stabilisers (measured via H-CNOT-H pattern)
        x_stabs = [
            (s[0], [0, 2, 4, 6]),
            (s[1], [1, 2, 5, 6]),
            (s[2], [3, 4, 5, 6]),
        ]
        for anc, data_indices in x_stabs:
            circuit.append(cirq.H(anc))
            for idx in data_indices:
                circuit.append(cirq.CNOT(anc, q[idx]))
            circuit.append(cirq.H(anc))

        # Z-type stabilisers
        z_stabs = [
            (s[3], [0, 2, 4, 6]),
            (s[4], [1, 2, 5, 6]),
            (s[5], [3, 4, 5, 6]),
        ]
        for anc, data_indices in z_stabs:
            for idx in data_indices:
                circuit.append(cirq.CNOT(q[idx], anc))

        # Measure all syndrome qubits
        circuit.append(cirq.measure(*s[:6], key='steane_syndrome'))
        return circuit

    def correct_steane_errors(self, code_qubits: List[cirq.Qid],
                               syndrome: int) -> cirq.Circuit:
        """Apply corrections for the Steane code given a 6-bit syndrome.

        The lower 3 bits (X-syndrome) identify the Z-error location.
        The upper 3 bits (Z-syndrome) identify the X-error location.
        The syndrome value maps directly to the 1-indexed qubit position
        (0 means no error).

        Args:
            code_qubits: Seven code qubits
            syndrome: 6-bit integer (z_synd << 3 | x_synd)

        Returns:
            Correction circuit
        """
        circuit = cirq.Circuit()
        x_synd = syndrome & 0b111
        z_synd = (syndrome >> 3) & 0b111

        # X syndrome -> apply Z correction
        if 1 <= x_synd <= 7:
            circuit.append(cirq.Z(code_qubits[x_synd - 1]))

        # Z syndrome -> apply X correction
        if 1 <= z_synd <= 7:
            circuit.append(cirq.X(code_qubits[z_synd - 1]))

        return circuit

    # ------------------------------------------------------------------
    # Surface code (distance 3)
    # ------------------------------------------------------------------

    def create_surface_code_d3(self) -> Dict[str, Any]:
        """Create a distance-3 rotated surface code layout.

        Returns a dictionary with data qubits, X-stabiliser ancillas,
        Z-stabiliser ancillas, and a circuit that performs one round of
        stabiliser measurements.

        Returns:
            Dict with keys 'data_qubits', 'x_ancillas', 'z_ancillas',
            'syndrome_circuit'.
        """
        # Distance-3 rotated surface code: 9 data qubits arranged in a 3×3 grid
        data = [[cirq.GridQubit(r, c) for c in range(3)] for r in range(3)]
        data_flat = [q for row in data for q in row]

        # X stabiliser ancillas (4 plaquettes)
        x_anc = [cirq.GridQubit(r + 0.5, c + 0.5)
                 for r in range(2) for c in range(2) if (r + c) % 2 == 0]
        # For distance 3 we have specific plaquette positions
        x_anc = [cirq.NamedQubit(f"Xa_{i}") for i in range(4)]

        # Z stabiliser ancillas (4 plaquettes)
        z_anc = [cirq.NamedQubit(f"Za_{i}") for i in range(4)]

        # X-stabiliser plaquettes (each touches 4 data qubits)
        x_plaquettes = [
            (x_anc[0], [data[0][0], data[0][1], data[1][0], data[1][1]]),
            (x_anc[1], [data[0][1], data[0][2], data[1][1], data[1][2]]),
            (x_anc[2], [data[1][0], data[1][1], data[2][0], data[2][1]]),
            (x_anc[3], [data[1][1], data[1][2], data[2][1], data[2][2]]),
        ]

        # Z-stabiliser plaquettes
        z_plaquettes = [
            (z_anc[0], [data[0][0], data[0][1], data[1][0], data[1][1]]),
            (z_anc[1], [data[0][1], data[0][2], data[1][1], data[1][2]]),
            (z_anc[2], [data[1][0], data[1][1], data[2][0], data[2][1]]),
            (z_anc[3], [data[1][1], data[1][2], data[2][1], data[2][2]]),
        ]

        circuit = cirq.Circuit()

        # X-stabiliser measurement: H-CNOT-H
        for anc, dqs in x_plaquettes:
            circuit.append(cirq.H(anc))
            for dq in dqs:
                circuit.append(cirq.CNOT(anc, dq))
            circuit.append(cirq.H(anc))

        # Z-stabiliser measurement: CNOT
        for anc, dqs in z_plaquettes:
            for dq in dqs:
                circuit.append(cirq.CNOT(dq, anc))

        # Measure ancillas
        all_anc = x_anc + z_anc
        circuit.append(cirq.measure(*all_anc, key='surface_syndrome'))

        return {
            "data_qubits": data_flat,
            "x_ancillas": x_anc,
            "z_ancillas": z_anc,
            "syndrome_circuit": circuit,
        }

    # ------------------------------------------------------------------
    # Minimum-weight perfect matching (MWPM) syndrome decoding
    # ------------------------------------------------------------------

    @staticmethod
    def mwpm_decode(syndrome_bits: List[int],
                    code_distance: int = 3) -> List[Tuple[int, str]]:
        """Decode a syndrome using a greedy minimum-weight perfect matching.

        This is a simplified MWPM implementation that pairs defects greedily
        by shortest Manhattan distance.  For production use, replace with
        PyMatching or Stim+PyMatching.

        Args:
            syndrome_bits: List of 0/1 syndrome outcomes
            code_distance: Code distance (default 3)

        Returns:
            List of (qubit_index, correction_type) tuples
        """
        # Find defect positions (syndrome bits that are 1)
        defects = [i for i, bit in enumerate(syndrome_bits) if bit == 1]

        if len(defects) == 0:
            return []

        # If odd number of defects, add a virtual boundary defect
        if len(defects) % 2 == 1:
            defects.append(-1)  # boundary

        corrections: List[Tuple[int, str]] = []

        # Greedy matching: pair closest defects
        matched = set()
        pairs = []
        remaining = list(defects)

        while len(remaining) >= 2:
            best_dist = float('inf')
            best_pair = (0, 1)
            for i in range(len(remaining)):
                for j in range(i + 1, len(remaining)):
                    d_i, d_j = remaining[i], remaining[j]
                    if d_i == -1 or d_j == -1:
                        dist = code_distance  # boundary distance
                    else:
                        dist = abs(d_i - d_j)
                    if dist < best_dist:
                        best_dist = dist
                        best_pair = (i, j)
            i, j = best_pair
            a, b = remaining[i], remaining[j]
            pairs.append((a, b))
            remaining = [remaining[k] for k in range(len(remaining))
                         if k != i and k != j]

        # Convert matched pairs to corrections
        half = len(syndrome_bits) // 2
        for a, b in pairs:
            if a == -1 or b == -1:
                real = a if b == -1 else b
                if real < half:
                    corrections.append((real, "X"))
                else:
                    corrections.append((real - half, "Z"))
            else:
                # Correction on the path between the two defects
                lo, hi = min(a, b), max(a, b)
                for q in range(lo, hi):
                    if q < half:
                        corrections.append((q, "X"))
                    else:
                        corrections.append((q - half, "Z"))

        return corrections