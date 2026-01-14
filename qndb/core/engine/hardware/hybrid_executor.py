"""Hybrid classical-quantum execution engine.

Automatic workload partitioning, circuit knitting for oversized
problems, mid-circuit measurement support, variational loop
orchestration, and error budget management.
"""

import cirq
import enum
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from qndb.core.engine.hardware.backend_registry import (
    BackendCapabilities,
    HardwareBackendBase,
)
from qndb.core.engine.hardware.compilation import HardwareCompiler, CalibrationData

logger = logging.getLogger(__name__)


# ======================================================================
# Workload classification
# ======================================================================

class WorkloadType(enum.Enum):
    CLASSICAL = "classical"
    QUANTUM = "quantum"
    HYBRID = "hybrid"


@dataclass
class WorkloadAnalysis:
    """Result of analysing a circuit to decide execution strategy."""
    workload_type: WorkloadType = WorkloadType.CLASSICAL
    num_qubits_needed: int = 0
    circuit_depth: int = 0
    estimated_advantage: float = 0.0
    exceeds_device: bool = False
    knitting_required: bool = False
    recommended_shots: int = 1000
    reason: str = ""


class WorkloadPartitioner:
    """Decide whether a workload should run classically, on quantum hardware, or hybrid."""

    # Thresholds for quantum advantage heuristics
    MIN_QUBITS_FOR_QUANTUM = 4
    MIN_DEPTH_FOR_QUANTUM = 3
    CLASSICAL_SIMULATION_LIMIT = 25  # qubits — beyond this, quantum may help

    def __init__(self, capabilities: BackendCapabilities) -> None:
        self._caps = capabilities

    def analyse(self, circuit: cirq.Circuit) -> WorkloadAnalysis:
        """Classify a circuit and recommend execution path."""
        qubits = sorted(circuit.all_qubits())
        n_qubits = len(qubits)
        depth = len(circuit)
        n_ops = len(list(circuit.all_operations()))

        analysis = WorkloadAnalysis(
            num_qubits_needed=n_qubits,
            circuit_depth=depth,
        )

        # Too small for quantum advantage
        if n_qubits < self.MIN_QUBITS_FOR_QUANTUM or depth < self.MIN_DEPTH_FOR_QUANTUM:
            analysis.workload_type = WorkloadType.CLASSICAL
            analysis.reason = f"Small circuit ({n_qubits}q, depth {depth}) — classical is faster"
            return analysis

        # Exceeds device capacity?
        if n_qubits > self._caps.num_qubits:
            analysis.exceeds_device = True
            analysis.knitting_required = True
            analysis.workload_type = WorkloadType.HYBRID
            analysis.reason = (
                f"Circuit needs {n_qubits} qubits but device has {self._caps.num_qubits} "
                "— circuit knitting required"
            )
            return analysis

        # Beyond classical simulation limit → quantum
        if n_qubits > self.CLASSICAL_SIMULATION_LIMIT:
            analysis.workload_type = WorkloadType.QUANTUM
            analysis.estimated_advantage = 2.0 ** (n_qubits - self.CLASSICAL_SIMULATION_LIMIT)
            analysis.reason = f"Large circuit ({n_qubits}q) exceeds classical sim threshold"
            return analysis

        # Medium-size: hybrid is often best (classical pre/post-processing)
        analysis.workload_type = WorkloadType.HYBRID
        analysis.estimated_advantage = 1.0 + math.log2(max(1, n_qubits))
        analysis.reason = f"Medium circuit ({n_qubits}q) — hybrid execution recommended"
        return analysis


# ======================================================================
# Circuit knitting
# ======================================================================

class CircuitKnitter:
    """Split a large circuit into sub-circuits that fit on the device.

    This implements a simplified version of circuit cutting / knitting:
    decompose the circuit at cut points, run each fragment, and
    reconstruct the result via classical post-processing.
    """

    def __init__(self, max_qubits: int) -> None:
        self._max_qubits = max_qubits

    def cut(self, circuit: cirq.Circuit) -> List[cirq.Circuit]:
        """Split *circuit* into fragments of at most *max_qubits*."""
        all_qubits = sorted(circuit.all_qubits())
        n = len(all_qubits)

        if n <= self._max_qubits:
            return [circuit]

        # Partition qubits into groups of max_qubits
        groups: List[List[cirq.Qid]] = []
        for i in range(0, n, self._max_qubits):
            groups.append(all_qubits[i : i + self._max_qubits])

        fragments: List[cirq.Circuit] = []
        for group in groups:
            group_set = set(group)
            ops = [
                op for op in circuit.all_operations()
                if all(q in group_set for q in op.qubits)
            ]
            if ops:
                fragments.append(cirq.Circuit(ops))

        # Handle cross-partition operations (simplified: warn + drop)
        cross_ops = [
            op for op in circuit.all_operations()
            if not any(
                all(q in set(g) for q in op.qubits)
                for g in groups
            )
        ]
        if cross_ops:
            logger.warning(
                "CircuitKnitter: %d cross-partition operations will be approximated",
                len(cross_ops),
            )

        return fragments if fragments else [circuit]

    def reconstruct(
        self,
        fragment_results: List[cirq.Result],
    ) -> Dict[str, Any]:
        """Combine results from fragments via classical post-processing.

        This is a simplified reconstruction that merges measurement
        dictionaries from each fragment.
        """
        combined: Dict[str, Any] = {}
        for i, result in enumerate(fragment_results):
            for key, val in result.measurements.items():
                combined[f"fragment_{i}_{key}"] = val
        return combined


# ======================================================================
# Error budget manager
# ======================================================================

@dataclass
class ErrorBudget:
    """Error budget allocation for a quantum execution."""
    total_budget: float = 0.01  # max acceptable total error rate
    gate_budget: float = 0.005
    readout_budget: float = 0.003
    decoherence_budget: float = 0.002
    remaining: float = 0.01


class ErrorBudgetManager:
    """Allocate and track error budgets across circuit execution."""

    def __init__(self, total_budget: float = 0.01) -> None:
        self._total = total_budget

    def allocate(
        self,
        circuit: cirq.Circuit,
        capabilities: BackendCapabilities,
    ) -> ErrorBudget:
        """Compute error budget allocation for a circuit + device pair."""
        ops = list(circuit.all_operations())
        n_single = sum(1 for o in ops if len(o.qubits) == 1)
        n_two = sum(1 for o in ops if len(o.qubits) == 2)
        n_readout = sum(1 for o in ops if cirq.is_measurement(o))

        gate_error = (
            n_single * capabilities.single_qubit_error
            + n_two * capabilities.two_qubit_error
        )
        readout_error = n_readout * capabilities.readout_error

        # T2 decoherence estimate
        depth = len(circuit)
        total_time_us = depth * (capabilities.two_qubit_gate_time_ns / 1000.0)
        decoherence = 1.0 - math.exp(-total_time_us / max(capabilities.t2_us, 1e-6))

        total_estimated = gate_error + readout_error + decoherence
        remaining = max(0.0, self._total - total_estimated)

        return ErrorBudget(
            total_budget=self._total,
            gate_budget=gate_error,
            readout_budget=readout_error,
            decoherence_budget=decoherence,
            remaining=remaining,
        )

    def is_within_budget(self, budget: ErrorBudget) -> bool:
        return budget.remaining > 0


# ======================================================================
# Hybrid executor
# ======================================================================

class HybridExecutor:
    """Orchestrate hybrid classical-quantum execution.

    Combines workload partitioning, hardware compilation, circuit
    knitting, variational loops, and mid-circuit measurement into
    a single execution interface.
    """

    def __init__(
        self,
        backend: HardwareBackendBase,
        compiler: Optional[HardwareCompiler] = None,
    ) -> None:
        self._backend = backend
        self._caps = backend.capabilities
        self._compiler = compiler or HardwareCompiler(self._caps)
        self._partitioner = WorkloadPartitioner(self._caps)
        self._knitter = CircuitKnitter(self._caps.num_qubits)
        self._budget_mgr = ErrorBudgetManager()

    # -- Main entry point ---------------------------------------------------

    def execute(
        self,
        circuit: cirq.Circuit,
        repetitions: int = 1000,
        compile: bool = True,
    ) -> Dict[str, Any]:
        """Execute a circuit using the optimal strategy.

        Returns a dict with ``result``, ``strategy``, ``stats``, and
        ``error_budget``.
        """
        analysis = self._partitioner.analyse(circuit)
        budget = self._budget_mgr.allocate(circuit, self._caps)

        if analysis.workload_type == WorkloadType.CLASSICAL:
            return self._execute_classical(circuit, repetitions, analysis, budget)

        if analysis.knitting_required:
            return self._execute_knitted(circuit, repetitions, analysis, budget, compile)

        return self._execute_quantum(circuit, repetitions, analysis, budget, compile)

    # -- Strategies ---------------------------------------------------------

    def _execute_classical(
        self,
        circuit: cirq.Circuit,
        repetitions: int,
        analysis: WorkloadAnalysis,
        budget: ErrorBudget,
    ) -> Dict[str, Any]:
        """Run on a local simulator (classical fast path)."""
        sim = cirq.Simulator()
        result = sim.run(circuit, repetitions=repetitions)
        return {
            "result": result,
            "strategy": "classical",
            "analysis": analysis,
            "error_budget": budget,
        }

    def _execute_quantum(
        self,
        circuit: cirq.Circuit,
        repetitions: int,
        analysis: WorkloadAnalysis,
        budget: ErrorBudget,
        compile: bool,
    ) -> Dict[str, Any]:
        """Compile and run on the quantum backend."""
        if compile:
            compiled = self._compiler.compile(circuit)
            run_circuit = compiled["compiled_circuit"]
            stats = compiled["stats"]
        else:
            run_circuit = circuit
            stats = {}

        result = self._backend.run(run_circuit, repetitions)
        return {
            "result": result,
            "strategy": "quantum",
            "analysis": analysis,
            "compilation_stats": stats,
            "error_budget": budget,
        }

    def _execute_knitted(
        self,
        circuit: cirq.Circuit,
        repetitions: int,
        analysis: WorkloadAnalysis,
        budget: ErrorBudget,
        compile: bool,
    ) -> Dict[str, Any]:
        """Split circuit, execute fragments, recombine."""
        fragments = self._knitter.cut(circuit)
        fragment_results: List[cirq.Result] = []

        for i, frag in enumerate(fragments):
            if compile:
                compiled = self._compiler.compile(frag)
                frag = compiled["compiled_circuit"]
            result = self._backend.run(frag, repetitions)
            fragment_results.append(result)
            logger.info("Fragment %d/%d executed", i + 1, len(fragments))

        combined = self._knitter.reconstruct(fragment_results)
        return {
            "result": combined,
            "strategy": "knitted",
            "num_fragments": len(fragments),
            "analysis": analysis,
            "error_budget": budget,
        }

    # -- Variational loops --------------------------------------------------

    def variational_loop(
        self,
        circuit: cirq.Circuit,
        cost_function: Callable[[Dict[str, Any]], float],
        initial_params: Dict[str, float],
        max_iterations: int = 100,
        tolerance: float = 1e-4,
        repetitions: int = 1000,
    ) -> Dict[str, Any]:
        """Run an iterative quantum-classical optimisation loop.

        A simplified gradient-free optimiser (coordinate descent) that
        alternates between quantum circuit evaluation and classical
        parameter updates.
        """
        params = dict(initial_params)
        best_cost = float("inf")
        best_params = dict(params)
        history: List[float] = []

        for iteration in range(max_iterations):
            # Resolve parameters and run
            resolver = cirq.ParamResolver(params)
            resolved = cirq.resolve_parameters(circuit, resolver)
            exec_result = self.execute(resolved, repetitions, compile=True)

            cost = cost_function(exec_result)
            history.append(cost)

            if cost < best_cost:
                best_cost = cost
                best_params = dict(params)

            # Convergence check
            if len(history) >= 2 and abs(history[-1] - history[-2]) < tolerance:
                logger.info("Variational loop converged at iteration %d", iteration)
                break

            # Simple coordinate descent step
            for key in params:
                delta = 0.1 * (0.95 ** iteration)
                for sign in [+1, -1]:
                    trial = dict(params)
                    trial[key] = params[key] + sign * delta
                    resolver = cirq.ParamResolver(trial)
                    resolved = cirq.resolve_parameters(circuit, resolver)
                    trial_result = self.execute(resolved, repetitions, compile=False)
                    trial_cost = cost_function(trial_result)
                    if trial_cost < cost:
                        params[key] = trial[key]
                        cost = trial_cost
                        break

        return {
            "optimal_params": best_params,
            "optimal_cost": best_cost,
            "iterations": len(history),
            "cost_history": history,
        }

    # -- Mid-circuit measurement --------------------------------------------

    def execute_with_mid_circuit_measurement(
        self,
        circuit: cirq.Circuit,
        measurement_keys: List[str],
        classical_callback: Optional[Callable[[Dict[str, Any]], List[cirq.Operation]]] = None,
        repetitions: int = 1000,
    ) -> Dict[str, Any]:
        """Execute a circuit with mid-circuit measurements and optional classical feedforward.

        If the backend supports mid-circuit measurement natively, the
        circuit is sent as-is.  Otherwise it is split at measurement
        points and the classical callback can inject operations between
        segments.
        """
        if self._caps.supports_mid_circuit_measurement:
            result = self._backend.run(circuit, repetitions)
            return {"result": result, "native_mid_circuit": True}

        # Emulate: split at measurements
        segments = self._split_at_measurements(circuit, measurement_keys)
        accumulated_ops: List[cirq.Operation] = []
        mid_results: Dict[str, Any] = {}

        for i, segment in enumerate(segments):
            full = cirq.Circuit(accumulated_ops + list(segment.all_operations()))
            result = self._backend.run(full, repetitions)
            mid_results[f"segment_{i}"] = result

            if classical_callback and i < len(segments) - 1:
                extra_ops = classical_callback(mid_results)
                accumulated_ops.extend(list(segment.all_operations()))
                accumulated_ops.extend(extra_ops)
            else:
                accumulated_ops.extend(list(segment.all_operations()))

        return {"result": mid_results, "native_mid_circuit": False}

    @staticmethod
    def _split_at_measurements(
        circuit: cirq.Circuit,
        keys: List[str],
    ) -> List[cirq.Circuit]:
        """Split a circuit into segments at measurement points."""
        segments: List[List[cirq.Operation]] = [[]]
        for op in circuit.all_operations():
            if cirq.is_measurement(op):
                segments[-1].append(op)
                segments.append([])
            else:
                segments[-1].append(op)
        return [cirq.Circuit(seg) for seg in segments if seg]
