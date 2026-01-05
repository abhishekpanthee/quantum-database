"""Main quantum processing engine for the database system."""

import cirq
import numpy as np
import sympy
import time
import logging
from typing import Dict, List, Any, Optional

from qndb.core.engine.backends import BackendBase, SimulatorBackend, CloudBackend
from qndb.core.engine.noise import NoiseConfig

logger = logging.getLogger(__name__)


class QuantumEngine:
    """Main quantum processing unit for the database system."""

    def __init__(
        self,
        num_qubits: int = 10,
        simulator_type: str = "simulator",
        noise_config: Optional[NoiseConfig] = None,
        backend: Optional[BackendBase] = None,
    ) -> None:
        self.num_qubits = num_qubits
        self.simulator_type = simulator_type
        self.noise_config = noise_config
        self.qubits = self._initialize_qubits()

        if backend is not None:
            self._backend = backend
        elif simulator_type == "hardware":
            self._backend = CloudBackend()
        else:
            self._backend = SimulatorBackend(noise_model=noise_config)

        self.simulator = (
            self._backend._simulator
            if hasattr(self._backend, "_simulator")
            else cirq.Simulator()
        )

        self.circuit = cirq.Circuit()
        self.measurement_results: Dict[str, Any] = {}
        self._active_jobs: Dict[str, Any] = {}
        self._total_qubits = num_qubits
        self._available_qubits = num_qubits
        self._state_version = 0

        # Qubit allocation tracking
        self._allocated: Dict[str, List[int]] = {}

        # Circuit parameterisation support
        self._parameters: Dict[str, sympy.Symbol] = {}

        # Checkpointing
        self._checkpoints: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        try:
            self.reset_circuit()
            if config:
                if "num_qubits" in config:
                    self.num_qubits = config["num_qubits"]
                    self.qubits = self._initialize_qubits()
                if "simulator_type" in config:
                    self.simulator_type = config["simulator_type"]
            return True
        except Exception as e:
            logger.error("Error initializing quantum engine: %s", e)
            return False

    def _initialize_qubits(self) -> List[cirq.Qid]:
        return [cirq.LineQubit(i) for i in range(self.num_qubits)]

    # ------------------------------------------------------------------
    # Circuit manipulation
    # ------------------------------------------------------------------

    def reset_circuit(self) -> None:
        self.circuit = cirq.Circuit()

    def add_operations(self, operations: List[cirq.Operation]) -> None:
        self.circuit.append(operations)

    def run_circuit(self, repetitions: int = 1000) -> Dict[str, np.ndarray]:
        self.measurement_results = self.simulator.run(self.circuit, repetitions=repetitions)
        return self.measurement_results.measurements

    def get_state_vector(self) -> np.ndarray:
        return self.simulator.simulate(self.circuit).final_state_vector

    def apply_operation(
        self,
        operation_type: str,
        qubits: List[int],
        params: Optional[List[float]] = None,
    ) -> None:
        target_qubits = [self.qubits[i] for i in qubits]

        _single = {"H": cirq.H, "X": cirq.X, "Y": cirq.Y, "Z": cirq.Z}
        if operation_type in _single:
            operations = [_single[operation_type](q) for q in target_qubits]
        elif operation_type == "CNOT" and len(qubits) >= 2:
            operations = [cirq.CNOT(self.qubits[qubits[0]], self.qubits[qubits[1]])]
        elif operation_type == "CZ" and len(qubits) >= 2:
            operations = [cirq.CZ(self.qubits[qubits[0]], self.qubits[qubits[1]])]
        elif operation_type == "SWAP" and len(qubits) >= 2:
            operations = [cirq.SWAP(self.qubits[qubits[0]], self.qubits[qubits[1]])]
        elif operation_type == "Rx" and params:
            operations = [cirq.rx(params[0])(q) for q in target_qubits]
        elif operation_type == "Ry" and params:
            operations = [cirq.ry(params[0])(q) for q in target_qubits]
        elif operation_type == "Rz" and params:
            operations = [cirq.rz(params[0])(q) for q in target_qubits]
        else:
            raise ValueError(f"Unknown operation type: {operation_type}")

        self.add_operations(operations)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def reset_state(self) -> None:
        self.qubits = self._initialize_qubits()
        self.reset_circuit()
        self.measurement_results = {}
        self._active_jobs = {}
        self._available_qubits = self._total_qubits
        self._state_version += 1
        print("Quantum state has been reset.")

    def get_current_state(self) -> Dict[str, Any]:
        state_vector = self.get_state_vector()
        return {
            "state_vector": state_vector,
            "num_qubits": self.num_qubits,
            "time_stamp": time.time(),
        }

    def get_state_version(self) -> str:
        return str(self._state_version)

    def apply_state_updates(self, updates: Dict[str, Any]) -> bool:
        try:
            self.reset_circuit()
            if "operations" in updates:
                for op in updates["operations"]:
                    op_type = op.get("type")
                    qubits = op.get("qubits", [])
                    params = op.get("params")
                    if op_type and qubits:
                        self.apply_operation(op_type, qubits, params)
            return True
        except Exception as e:
            logger.error("Failed to apply state updates: %s", e)
            return False

    # ------------------------------------------------------------------
    # Resource management
    # ------------------------------------------------------------------

    def release_resources(self, job_id: Optional[str] = None) -> bool:
        logger.info("Releasing quantum resources for job_id: %s", job_id or "ALL")
        try:
            if job_id is None:
                self._reset_quantum_state()
                self._deallocate_all_qubits()
            else:
                job_resources = self._active_jobs.get(job_id)
                if job_resources:
                    self._deallocate_qubits(job_resources["qubits"])
                    self._active_jobs.pop(job_id)
                else:
                    logger.warning("No active job found with ID: %s", job_id)
                    return False
            return True
        except Exception as e:
            logger.error("Failed to release quantum resources: %s", e)
            return False

    def _reset_quantum_state(self) -> None:
        pass

    def _deallocate_all_qubits(self) -> None:
        self._active_jobs.clear()
        self._available_qubits = self._total_qubits

    def _deallocate_qubits(self, qubits: List[int]) -> None:
        self._available_qubits += len(qubits)

    # ------------------------------------------------------------------
    # Measurement
    # ------------------------------------------------------------------

    def measure_qubits(self, qubits: List[int], key: str = "measurement") -> None:
        target_qubits = [self.qubits[i] for i in qubits]
        self.circuit.append(cirq.measure(*target_qubits, key=key))

    def get_circuit_diagram(self) -> str:
        return str(self.circuit)

    def estimate_resources(self) -> Dict[str, Any]:
        num_operations = len(list(self.circuit.all_operations()))
        depth = cirq.Circuit(self.circuit.all_operations()).depth()
        return {
            "num_qubits": self.num_qubits,
            "num_operations": num_operations,
            "circuit_depth": depth,
        }

    # ------------------------------------------------------------------
    # Circuit parameterisation
    # ------------------------------------------------------------------

    def create_parameter(self, name: str) -> sympy.Symbol:
        sym = sympy.Symbol(name)
        self._parameters[name] = sym
        return sym

    def resolve_parameters(self, param_values: Dict[str, float]) -> cirq.Circuit:
        resolver = cirq.ParamResolver(param_values)
        return cirq.resolve_parameters(self.circuit, resolver)

    # ------------------------------------------------------------------
    # Qubit allocation lifecycle
    # ------------------------------------------------------------------

    def allocate_qubits(self, count: int, job_id: Optional[str] = None) -> List[cirq.Qid]:
        if count > self._available_qubits:
            raise RuntimeError(
                f"Cannot allocate {count} qubits; only {self._available_qubits} available"
            )

        used_indices: set = set()
        for indices in self._allocated.values():
            used_indices.update(indices)

        free = [i for i in range(self._total_qubits) if i not in used_indices]
        chosen = free[:count]

        jid = job_id or f"job_{len(self._allocated)}"
        self._allocated[jid] = chosen
        self._available_qubits -= count
        self._active_jobs[jid] = {"qubits": chosen, "allocated_at": time.time()}

        return [self.qubits[i] for i in chosen]

    def deallocate_qubits(self, job_id: str) -> bool:
        if job_id not in self._allocated:
            logger.warning("No allocation found for job_id=%s", job_id)
            return False
        freed = self._allocated.pop(job_id)
        self._available_qubits += len(freed)
        self._active_jobs.pop(job_id, None)
        return True

    # ------------------------------------------------------------------
    # Checkpointing
    # ------------------------------------------------------------------

    def save_checkpoint(self, name: str) -> None:
        self._checkpoints[name] = {
            "circuit_ops": list(self.circuit.all_operations()),
            "state_version": self._state_version,
            "timestamp": time.time(),
        }
        logger.info("Checkpoint '%s' saved (v%s)", name, self._state_version)

    def restore_checkpoint(self, name: str) -> bool:
        cp = self._checkpoints.get(name)
        if cp is None:
            logger.warning("Checkpoint '%s' not found", name)
            return False
        self.circuit = cirq.Circuit(cp["circuit_ops"])
        self._state_version = cp["state_version"]
        logger.info("Restored checkpoint '%s'", name)
        return True

    def list_checkpoints(self) -> List[str]:
        return list(self._checkpoints.keys())
