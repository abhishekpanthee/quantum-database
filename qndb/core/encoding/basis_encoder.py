"""
Basis Encoder - Encodes classical data into computational basis states.
"""
import cirq
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

class BasisEncoder:
    """
    Encodes classical data into computational basis states.
    This approach is suitable for encoding discrete data.
    """
    
    def __init__(self, num_qubits: int):
        """
        Initialize the basis encoder.
        
        Args:
            num_qubits: Number of qubits available for encoding
        """
        self.num_qubits = num_qubits
        self.max_integer = 2**num_qubits - 1
        
    def int_to_binary(self, value: int) -> List[int]:
        """
        Convert an integer to its binary representation.
        
        Args:
            value: Integer to convert
            
        Returns:
            List of binary digits (0s and 1s)
        """
        if value < 0 or value > self.max_integer:
            raise ValueError(f"Value must be between 0 and {self.max_integer}")
            
        binary = bin(value)[2:].zfill(self.num_qubits)
        return [int(bit) for bit in binary]
    
    def encode_integer(self, value: int, qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Encode an integer value into qubits.
        
        Args:
            value: Integer value to encode
            qubits: Qubits to encode the value into
            
        Returns:
            Cirq circuit with encoding operations
        """
        if len(qubits) != self.num_qubits:
            raise ValueError(f"Expected {self.num_qubits} qubits, got {len(qubits)}")
            
        binary_rep = self.int_to_binary(value)
        circuit = cirq.Circuit()
        
        # Apply X gates to qubits that should be in state |1>
        for i, bit in enumerate(binary_rep):
            if bit == 1:
                circuit.append(cirq.X(qubits[i]))
                
        return circuit
    
    def encode_bitstring(self, bitstring: str, qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Encode a bitstring into qubits.
        
        Args:
            bitstring: String of 0s and 1s to encode
            qubits: Qubits to encode the bitstring into
            
        Returns:
            Cirq circuit with encoding operations
        """
        if len(bitstring) > self.num_qubits:
            raise ValueError(f"Bitstring length exceeds available qubits")
            
        # Pad with leading zeros if necessary
        padded_bitstring = bitstring.zfill(self.num_qubits)
        
        circuit = cirq.Circuit()
        
        # Apply X gates to qubits that should be in state |1>
        for i, bit in enumerate(padded_bitstring):
            if bit == '1':
                circuit.append(cirq.X(qubits[i]))
                
        return circuit
    
    def encode_text(self, text: str, qubits: List[cirq.Qid]) -> List[cirq.Circuit]:
        """
        Encode text by converting each character to its ASCII value.
        
        Args:
            text: Text to encode
            qubits: Qubits to encode each character into
            
        Returns:
            List of circuits, one for each character
        """
        if self.num_qubits < 8:
            raise ValueError("Need at least 8 qubits to encode ASCII characters")
            
        circuits = []
        
        for char in text:
            ascii_value = ord(char)
            circuit = self.encode_integer(ascii_value, qubits)
            circuits.append(circuit)
            
        return circuits
    
    def decode_measurement(self, measurement_results: Dict[str, np.ndarray]) -> int:
        """
        Decode measurement results into an integer.
        
        Args:
            measurement_results: Measurement results from running a circuit
            
        Returns:
            Integer value decoded from the measurement
        """
        # Extract the most common measurement result
        if 'measurement' not in measurement_results:
            raise KeyError("Expected 'measurement' key in measurement results")
            
        results = measurement_results['measurement']
        
        # Get the most common result
        if len(results.shape) > 1:
            # Multiple repetitions, find the most common
            most_common_idx = np.argmax(np.sum(results, axis=0))
            bits = results[most_common_idx]
        else:
            # Single result
            bits = results
        
        # Convert binary to integer
        value = 0
        for i, bit in enumerate(bits):
            value += bit * (2 ** (self.num_qubits - 1 - i))
            
        return value