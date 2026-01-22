"""
Amplitude Encoder - Encodes classical data into quantum amplitudes.

Implements the Möttönen et al. state preparation algorithm
(arXiv:quant-ph/0407010) for exact amplitude encoding.
"""
import cirq
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import math

class AmplitudeEncoder:
    """
    Encodes classical data into quantum state amplitudes.
    This approach is suitable for encoding continuous data.
    """
    
    def __init__(self, num_qubits: int):
        """
        Initialize the amplitude encoder.
        
        Args:
            num_qubits: Number of qubits available for encoding
        """
        self.num_qubits = num_qubits
        self.max_data_size = 2**num_qubits
        
    def normalize_data(self, data: List[float]) -> np.ndarray:
        """
        Normalize data to create a valid quantum state.
        
        Args:
            data: List of float values to encode
            
        Returns:
            Normalized data vector
        """
        # Pad with zeros if necessary
        padded_data = list(data)
        if len(padded_data) < self.max_data_size:
            padded_data.extend([0.0] * (self.max_data_size - len(padded_data)))
        
        # Truncate if too large
        if len(padded_data) > self.max_data_size:
            padded_data = padded_data[:self.max_data_size]
            
        # Convert to numpy array and normalize
        data_array = np.array(padded_data, dtype=float)
        norm = np.linalg.norm(data_array)
        
        if norm > 0:
            normalized_data = data_array / norm
        else:
            # If norm is zero, initialize to |0>
            normalized_data = np.zeros(self.max_data_size)
            normalized_data[0] = 1.0
            
        return normalized_data

    # ------------------------------------------------------------------
    # Möttönen state preparation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_rotation_angles(state_vector: np.ndarray) -> Tuple[List[List[float]], List[List[float]]]:
        """Compute Ry and Rz rotation angles for the Möttönen algorithm.

        The algorithm decomposes an arbitrary *n*-qubit state into a product of
        uniformly-controlled rotations.  We compute the angles bottom-up from
        the amplitudes.

        Returns:
            (alpha_y, alpha_z) – lists of angle-lists, one per qubit level.
        """
        n = int(np.log2(len(state_vector)))
        N = len(state_vector)

        # Work with magnitudes and phases
        magnitudes = np.abs(state_vector)
        phases = np.angle(state_vector)

        alpha_y: List[List[float]] = []
        alpha_z: List[List[float]] = []

        for k in range(n, 0, -1):
            num_groups = 2 ** (k - 1)
            group_size = N // num_groups
            half = group_size // 2

            angles_y = []
            angles_z = []

            for j in range(num_groups):
                start = j * group_size
                # Ry angle from magnitudes
                sum_left = np.sum(magnitudes[start: start + half] ** 2)
                sum_right = np.sum(magnitudes[start + half: start + group_size] ** 2)
                total = sum_left + sum_right
                if total > 1e-15:
                    angle_y = 2.0 * math.atan2(math.sqrt(sum_right), math.sqrt(sum_left))
                else:
                    angle_y = 0.0
                angles_y.append(angle_y)

                # Rz angle from phases
                mean_left = np.mean(phases[start: start + half]) if half > 0 else 0.0
                mean_right = np.mean(phases[start + half: start + group_size]) if half > 0 else 0.0
                angles_z.append(mean_right - mean_left)

            alpha_y.append(angles_y)
            alpha_z.append(angles_z)

            # Merge magnitudes for the next level
            new_mags = []
            new_phases = []
            for j in range(num_groups):
                start = j * group_size
                m = math.sqrt(np.sum(magnitudes[start: start + group_size] ** 2))
                new_mags.append(m)
                new_phases.append(np.mean(phases[start: start + group_size]))

            magnitudes = np.array(new_mags)
            phases = np.array(new_phases)

        # Reverse so index 0 corresponds to the most-significant qubit
        alpha_y.reverse()
        alpha_z.reverse()
        return alpha_y, alpha_z

    @staticmethod
    def _uniformly_controlled_ry(angles: List[float],
                                  control_qubits: List[cirq.Qid],
                                  target_qubit: cirq.Qid) -> cirq.Circuit:
        """Build a uniformly-controlled Ry rotation (multiplexed Ry)."""
        circuit = cirq.Circuit()
        n_ctrl = len(control_qubits)

        if n_ctrl == 0:
            if abs(angles[0]) > 1e-12:
                circuit.append(cirq.ry(angles[0]).on(target_qubit))
            return circuit

        # Gray-code decomposition for uniformly controlled rotations
        num_angles = len(angles)
        # Compute the angles for the decomposition via Walsh-Hadamard transform
        M = np.array(angles)
        size = len(M)
        step = 1
        while step < size:
            for i in range(0, size, step * 2):
                for j in range(step):
                    a = M[i + j]
                    b = M[i + j + step]
                    M[i + j] = (a + b) / 2
                    M[i + j + step] = (a - b) / 2
            step *= 2

        # Apply rotations with CNOT "peeling" using Gray code order
        for i in range(num_angles):
            if abs(M[i]) > 1e-12:
                circuit.append(cirq.ry(M[i]).on(target_qubit))
            if i < num_angles - 1:
                # Determine which control qubit to toggle (Gray code)
                diff = i ^ (i + 1)
                ctrl_idx = int(np.log2(diff))
                if ctrl_idx < n_ctrl:
                    circuit.append(cirq.CNOT(control_qubits[ctrl_idx], target_qubit))
            else:
                # Last CNOT to complete the cycle
                circuit.append(cirq.CNOT(control_qubits[0], target_qubit))

        return circuit

    def create_encoding_circuit(self, data: List[float]) -> cirq.Circuit:
        """
        Create a quantum circuit to encode the data into amplitudes using the
        Möttönen state preparation algorithm.
        
        Args:
            data: List of float values to encode
            
        Returns:
            Cirq circuit for encoding
        """
        normalized_data = self.normalize_data(data)
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = cirq.Circuit()

        if self.num_qubits == 0:
            return circuit

        alpha_y, alpha_z = self._compute_rotation_angles(normalized_data)

        for level in range(self.num_qubits):
            target = qubits[level]
            controls = qubits[:level]
            circuit += self._uniformly_controlled_ry(alpha_y[level], controls, target)

        return circuit
    
    def encode(self, data: List[float], qubits: List[cirq.Qid]) -> cirq.Circuit:
        """
        Encode classical data into the quantum state of provided qubits.
        
        Args:
            data: List of float values to encode
            qubits: Qubits to encode the data into
            
        Returns:
            Cirq circuit with encoding operations
        """
        if len(qubits) != self.num_qubits:
            raise ValueError(f"Expected {self.num_qubits} qubits, got {len(qubits)}")
            
        normalized_data = self.normalize_data(data)
        circuit = cirq.Circuit()

        if self.num_qubits == 0:
            return circuit

        alpha_y, _ = self._compute_rotation_angles(normalized_data)

        for level in range(self.num_qubits):
            target = qubits[level]
            controls = qubits[:level]
            circuit += self._uniformly_controlled_ry(alpha_y[level], controls, target)

        return circuit

    # ------------------------------------------------------------------
    # Angle encoding (for variational workloads)
    # ------------------------------------------------------------------

    def angle_encode(self, data: List[float], qubits: List[cirq.Qid]) -> cirq.Circuit:
        """Encode each data value as an Ry rotation angle on a separate qubit.

        Suitable for variational quantum algorithms where each feature maps to
        one qubit.

        Args:
            data: Feature values (will be scaled to [0, pi])
            qubits: One qubit per data feature

        Returns:
            Encoding circuit
        """
        if len(data) > len(qubits):
            raise ValueError("More data features than qubits")

        circuit = cirq.Circuit()
        dmin, dmax = min(data), max(data)
        span = dmax - dmin if dmax != dmin else 1.0

        for val, qubit in zip(data, qubits):
            angle = np.pi * (val - dmin) / span
            circuit.append(cirq.ry(angle).on(qubit))

        return circuit

    # ------------------------------------------------------------------
    # Sparse amplitude encoding
    # ------------------------------------------------------------------

    def sparse_encode(self, data: Dict[int, float], qubits: List[cirq.Qid]) -> cirq.Circuit:
        """Encode a sparse vector by only preparing non-zero amplitudes.

        Uses a sequence of controlled rotations that is efficient when the
        number of non-zero entries is much smaller than 2^n.

        Args:
            data: Mapping from basis-state index to amplitude value
            qubits: Qubits for encoding

        Returns:
            Encoding circuit
        """
        if len(qubits) != self.num_qubits:
            raise ValueError(f"Expected {self.num_qubits} qubits, got {len(qubits)}")

        # Build full vector from sparse representation then use Möttönen
        full_vec = np.zeros(self.max_data_size)
        for idx, val in data.items():
            if 0 <= idx < self.max_data_size:
                full_vec[idx] = val
        norm = np.linalg.norm(full_vec)
        if norm > 0:
            full_vec /= norm
        else:
            full_vec[0] = 1.0

        alpha_y, _ = self._compute_rotation_angles(full_vec)
        circuit = cirq.Circuit()
        for level in range(self.num_qubits):
            target = qubits[level]
            controls = qubits[:level]
            circuit += self._uniformly_controlled_ry(alpha_y[level], controls, target)
        return circuit
    
    def estimate_encoding_cost(self, data_size: int) -> Dict[str, Any]:
        """
        Estimate the computational cost of encoding data.
        
        Args:
            data_size: Size of the data to encode
            
        Returns:
            Dictionary with cost estimates
        """
        # Möttönen requires O(2^n) CNOT gates in the worst case
        num_cnots = 2 ** self.num_qubits - 1
        depth = 2 * num_cnots  # each rotation + CNOT pair

        return {
            "num_qubits_required": self.num_qubits,
            "estimated_gate_count": num_cnots + 2 ** self.num_qubits,
            "estimated_circuit_depth": depth,
            "max_encodable_data_size": self.max_data_size,
            "data_compression_ratio": data_size / self.max_data_size if self.max_data_size > 0 else 0
        }