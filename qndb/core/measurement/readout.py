"""
Measurement and readout protocols for the quantum database system.
"""

import cirq
import numpy as np
from typing import List, Dict, Tuple, Optional, Union, Callable
import logging


class QuantumReadout:
    """
    Handles measurement and result interpretation for quantum database operations.
    """
    
    def __init__(self, shots: int = 1000, error_mitigation: bool = True):
        """
        Initialize the quantum readout system.
        
        Args:
            shots (int): Number of measurement shots to use
            error_mitigation (bool): Whether to apply error mitigation techniques
        """
        self.shots = shots
        self.error_mitigation = error_mitigation
        self.logger = logging.getLogger(__name__)
        
    def measure_circuit(self, circuit: cirq.Circuit, qubits: List[cirq.Qid] = None) -> Dict:
        """
        Measure the given circuit and return the results.
        
        Args:
            circuit (cirq.Circuit): The quantum circuit to measure
            qubits (List[cirq.Qid], optional): Specific qubits to measure
            
        Returns:
            Dict: Measurement results
        """
        # If no qubits specified, measure all qubits in the circuit
        if qubits is None:
            qubits = sorted(circuit.all_qubits())
            
        # Create a new circuit with measurements added
        measurement_circuit = circuit.copy()
        
        # Add measurement operations if not already present
        if not self._has_measurements(measurement_circuit, qubits):
            measurement_circuit.append(cirq.measure(*qubits, key='result'))
            
        # Simulate the circuit
        simulator = cirq.Simulator()
        results = simulator.run(measurement_circuit, repetitions=self.shots)
        
        # Process and return the measurement results
        processed_results = self._process_results(results, qubits)
        
        return processed_results
    
    def measure_with_basis(self, circuit: cirq.Circuit, 
                          measurement_basis: List[Tuple[cirq.Qid, cirq.Gate]], 
                          qubits: List[cirq.Qid] = None) -> Dict:
        """
        Measure the circuit using a specific measurement basis.
        
        Args:
            circuit (cirq.Circuit): The quantum circuit to measure
            measurement_basis (List[Tuple[cirq.Qid, cirq.Gate]]): Basis rotations to apply
            qubits (List[cirq.Qid], optional): Specific qubits to measure
            
        Returns:
            Dict: Measurement results in the specified basis
        """
        # If no qubits specified, use all qubits in the circuit
        if qubits is None:
            qubits = sorted(circuit.all_qubits())
            
        # Create a new circuit with basis rotations
        basis_circuit = circuit.copy()
        
        # Add basis rotation gates
        for qubit, gate in measurement_basis:
            if qubit in qubits:
                basis_circuit.append(gate(qubit))
                
        # Add measurements
        basis_circuit.append(cirq.measure(*qubits, key='result'))
        
        # Simulate the circuit
        simulator = cirq.Simulator()
        results = simulator.run(basis_circuit, repetitions=self.shots)
        
        # Process and return the measurement results
        processed_results = self._process_results(results, qubits)
        
        return processed_results
    
    def statevector_readout(self, circuit: cirq.Circuit) -> np.ndarray:
        """
        Get the final statevector of the quantum circuit.
        
        Args:
            circuit (cirq.Circuit): The quantum circuit
            
        Returns:
            np.ndarray: Final statevector
        """
        # Make sure circuit has no measurements (they collapse the statevector)
        clean_circuit = self._remove_measurements(circuit)
        
        # Simulate the circuit with statevector simulation
        simulator = cirq.Simulator()
        result = simulator.simulate(clean_circuit)
        
        return result.final_state_vector
    
    def sample_expectation(self, circuit: cirq.Circuit, 
                          observables: List[Tuple[List[cirq.Qid], cirq.PauliString]]) -> Dict:
        """
        Measure expectation values of given observables.
        
        Args:
            circuit (cirq.Circuit): The quantum circuit
            observables (List[Tuple[List[cirq.Qid], cirq.PauliString]]): Observables to measure
            
        Returns:
            Dict: Dictionary of expectation values for each observable
        """
        results = {}
        
        for qubits, observable in observables:
            # Create a new circuit for each observable
            obs_circuit = circuit.copy()
            
            # Get the appropriate basis rotations for the observable
            basis_rotations = self._pauli_to_basis_rotations(observable)
            
            # Apply basis rotations
            for qubit, rotation in basis_rotations:
                obs_circuit.append(rotation(qubit))
                
            # Add measurements
            obs_circuit.append(cirq.measure(*qubits, key='result'))
            
            # Simulate the circuit
            simulator = cirq.Simulator()
            sim_results = simulator.run(obs_circuit, repetitions=self.shots)
            
            # Compute expectation value
            expectation = self._compute_expectation(sim_results, observable)
            
            # Store result
            results[str(observable)] = expectation
            
        return results
    
    def _has_measurements(self, circuit: cirq.Circuit, qubits: List[cirq.Qid]) -> bool:
        """
        Check if the circuit already has measurements for all specified qubits.
        
        Args:
            circuit (cirq.Circuit): The quantum circuit
            qubits (List[cirq.Qid]): Qubits to check for measurements
            
        Returns:
            bool: True if all qubits have measurements, False otherwise
        """
        measured_qubits = set()
        
        # Find all measurement operations in the circuit
        for moment in circuit:
            for op in moment:
                if isinstance(op.gate, cirq.MeasurementGate):
                    measured_qubits.update(op.qubits)
                    
        # Check if all specified qubits are measured
        return all(q in measured_qubits for q in qubits)
    
    def _remove_measurements(self, circuit: cirq.Circuit) -> cirq.Circuit:
        """
        Remove all measurement operations from the circuit.
        
        Args:
            circuit (cirq.Circuit): The quantum circuit
            
        Returns:
            cirq.Circuit: Circuit without measurements
        """
        clean_moments = []
        
        # Keep only non-measurement operations
        for moment in circuit:
            clean_ops = [op for op in moment if not isinstance(op.gate, cirq.MeasurementGate)]
            if clean_ops:
                clean_moments.append(cirq.Moment(clean_ops))
                
        return cirq.Circuit(clean_moments)
    
    def _process_results(self, results: cirq.Result, qubits: List[cirq.Qid]) -> Dict:
        """
        Process the measurement results.
        
        Args:
            results (cirq.Result): Raw measurement results
            qubits (List[cirq.Qid]): Measured qubits
            
        Returns:
            Dict: Processed measurement results
        """
        # Get the measurement data
        if 'result' in results.data:
            # Extract the measurement counts for each bit string
            counts = results.histogram(key='result')
            
            # Calculate probabilities
            total_shots = sum(counts.values())
            probabilities = {bitstring: count / total_shots for bitstring, count in counts.items()}
            
            # Apply error mitigation if enabled
            if self.error_mitigation:
                probabilities = self._apply_error_mitigation(probabilities)
                
            # Format the results
            formatted_results = {
                "counts": counts,
                "probabilities": probabilities,
                "most_common": max(probabilities.items(), key=lambda x: x[1])[0],
                "shots": total_shots,
                "qubits_measured": len(qubits),
                "error_mitigation_applied": self.error_mitigation
            }
            
            return formatted_results
        else:
            self.logger.warning("No 'result' key found in measurement results")
            return {"error": "No measurement results found"}
    
    def _apply_error_mitigation(self, probabilities: Dict[int, float]) -> Dict[int, float]:
        """
        Apply error mitigation techniques to the measurement results.
        
        Uses confusion-matrix calibration if a calibration matrix is available,
        otherwise falls back to zero-noise extrapolation (ZNE) inspired
        thresholding.
        
        Args:
            probabilities (Dict[int, float]): Raw measurement probabilities
            
        Returns:
            Dict[int, float]: Error-mitigated probabilities
        """
        # If we have a calibration matrix, use it
        if hasattr(self, '_calibration_matrix') and self._calibration_matrix is not None:
            return self._apply_confusion_matrix_mitigation(probabilities)

        return self._apply_zne_mitigation(probabilities)

    # ------------------------------------------------------------------
    # Zero-noise extrapolation (ZNE)
    # ------------------------------------------------------------------

    def _apply_zne_mitigation(self, probabilities: Dict[int, float]) -> Dict[int, float]:
        """Simplified ZNE-inspired mitigation.

        In full ZNE one runs the circuit at several noise scale factors and
        extrapolates to the zero-noise limit.  Here we use a Richardson-like
        extrapolation on the probability vector: small probabilities that are
        below a noise-floor estimate are suppressed and the distribution is
        renormalised.

        Args:
            probabilities: Raw distribution

        Returns:
            Mitigated distribution
        """
        # Estimate noise floor from shot statistics
        noise_floor = 1.0 / (2 * self.shots)

        # Two-level extrapolation: keep values above noise floor, boost them
        mitigated: Dict[int, float] = {}
        for bitstring, prob in probabilities.items():
            if prob > noise_floor:
                # Linear extrapolation: amplify signal above noise floor
                corrected = prob + (prob - noise_floor) * 0.5
                mitigated[bitstring] = max(0.0, corrected)

        # Renormalise
        total = sum(mitigated.values())
        if total > 0:
            return {bs: p / total for bs, p in mitigated.items()}
        return probabilities

    # ------------------------------------------------------------------
    # Confusion matrix calibration
    # ------------------------------------------------------------------

    def calibrate(self, qubits: List[cirq.Qid],
                  shots: Optional[int] = None) -> np.ndarray:
        """Run calibration circuits to build a confusion (response) matrix.

        For *n* qubits the matrix is 2^n × 2^n.  Row *i* gives the measured
        distribution when the true state is |i⟩.  The inverse of this matrix
        is then applied to raw measurement distributions to correct for readout
        errors.

        Args:
            qubits: Qubits to calibrate
            shots: Calibration shots (defaults to self.shots)

        Returns:
            The calibration matrix (stored internally as well)
        """
        n = len(qubits)
        dim = 2 ** n
        cal_shots = shots or self.shots
        matrix = np.zeros((dim, dim))

        simulator = cirq.Simulator()

        for state_idx in range(dim):
            cal_circuit = cirq.Circuit()
            bits = format(state_idx, f'0{n}b')
            for i, bit in enumerate(bits):
                if bit == '1':
                    cal_circuit.append(cirq.X(qubits[i]))
            cal_circuit.append(cirq.measure(*qubits, key='cal'))

            result = simulator.run(cal_circuit, repetitions=cal_shots)
            counts = result.histogram(key='cal')
            for measured, cnt in counts.items():
                matrix[state_idx, measured] = cnt / cal_shots

        self._calibration_matrix = matrix
        # Compute pseudo-inverse for mitigation
        try:
            self._calibration_inverse = np.linalg.pinv(matrix)
        except np.linalg.LinAlgError:
            self._calibration_inverse = None
            self.logger.warning("Calibration matrix is singular; mitigation disabled")

        return matrix

    def _apply_confusion_matrix_mitigation(self,
                                            probabilities: Dict[int, float]) -> Dict[int, float]:
        """Apply the inverse calibration matrix to the raw distribution."""
        if self._calibration_inverse is None:
            return probabilities

        dim = self._calibration_inverse.shape[0]
        raw_vec = np.zeros(dim)
        for bs, prob in probabilities.items():
            if bs < dim:
                raw_vec[bs] = prob

        corrected = self._calibration_inverse @ raw_vec
        # Clip negatives and renormalise
        corrected = np.maximum(corrected, 0.0)
        total = corrected.sum()
        if total > 0:
            corrected /= total

        return {i: float(corrected[i]) for i in range(dim) if corrected[i] > 1e-10}
    
    def _pauli_to_basis_rotations(self, observable: cirq.PauliString) -> List[Tuple[cirq.Qid, Callable]]:
        """
        Convert Pauli observables to the appropriate basis rotations.
        
        Args:
            observable (cirq.PauliString): Pauli string observable
            
        Returns:
            List[Tuple[cirq.Qid, Callable]]: List of (qubit, rotation) pairs
        """
        rotations = []
        
        for qubit, pauli in observable.items():
            if pauli == cirq.X:
                # Rotate from X basis to Z basis for measurement
                rotations.append((qubit, lambda q: cirq.H(q)))
            elif pauli == cirq.Y:
                # Rotate from Y basis to Z basis for measurement
                rotations.append((qubit, lambda q: cirq.ry(-np.pi/2)(q)))
            # For Z, no rotation needed as we measure in Z basis
            
        return rotations
    
    def _compute_expectation(self, results: cirq.Result, observable: cirq.PauliString) -> float:
        """
        Compute the expectation value of an observable from measurement results.
        
        Args:
            results (cirq.Result): Measurement results
            observable (cirq.PauliString): Observable whose expectation to compute
            
        Returns:
            float: Expectation value
        """
        # Get the measurement counts
        counts = results.histogram(key='result')
        
        # Initialize expectation value
        expectation = 0.0
        total_shots = sum(counts.values())
        
        # For each bitstring, determine its contribution to the expectation value
        for bitstring, count in counts.items():
            # For a Pauli observable, the eigenvalue is ±1 depending on parity
            parity = bin(bitstring).count('1') % 2
            eigenvalue = 1.0 if parity == 0 else -1.0
            
            # Add contribution to expectation value
            expectation += eigenvalue * (count / total_shots)
            
        return expectation