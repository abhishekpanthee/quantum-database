"""Tests for real quantum hardware integration.

All tests run against the local simulator fallback (no real hardware
needed).  Feature flags are OFF by default, so every hardware backend
gracefully degrades to the Cirq simulator.
"""

import unittest
import math
import cirq
import numpy as np

from qndb.core.engine.hardware import (
    # Feature flags
    HARDWARE_ENABLED, IBM_ENABLED, GOOGLE_ENABLED, IONQ_ENABLED, BRAKET_ENABLED,
    # Registry
    BackendCapabilities, BackendRegistry, HardwareBackendBase,
    # Backends
    IBMBackend, GoogleBackend, IonQBackend, BraketBackend,
    # Compilation
    HardwareCompiler, TopologyMapper, GateDecomposer, CalibrationData,
    # Hybrid execution
    HybridExecutor, WorkloadPartitioner, CircuitKnitter, ErrorBudgetManager,
    # Error management
    CalibrationMonitor, ErrorMitigator, HardwareNoiseModel,
    FidelityScorer, CircuitRetryManager,
)
from qndb.core.engine.hardware.backend_registry import TopologyType, _SimulatorWrapper
from qndb.core.engine.hardware.error_management import MitigationStrategy, FidelityReport
from qndb.core.engine.hardware.hybrid_executor import WorkloadType, WorkloadAnalysis


# ======================================================================
# Helper: build a small test circuit
# ======================================================================

def _bell_circuit() -> cirq.Circuit:
    q0, q1 = cirq.LineQubit.range(2)
    return cirq.Circuit([
        cirq.H(q0),
        cirq.CNOT(q0, q1),
        cirq.measure(q0, q1, key="result"),
    ])


def _ghz_circuit(n: int = 4) -> cirq.Circuit:
    qubits = cirq.LineQubit.range(n)
    ops = [cirq.H(qubits[0])]
    for i in range(n - 1):
        ops.append(cirq.CNOT(qubits[i], qubits[i + 1]))
    ops.append(cirq.measure(*qubits, key="result"))
    return cirq.Circuit(ops)


def _large_circuit(n: int = 30) -> cirq.Circuit:
    """Circuit that exceeds a small device."""
    qubits = cirq.LineQubit.range(n)
    ops = [cirq.H(q) for q in qubits]
    for i in range(n - 1):
        ops.append(cirq.CNOT(qubits[i], qubits[i + 1]))
    ops.append(cirq.measure(*qubits, key="result"))
    return cirq.Circuit(ops)


# ======================================================================
# 6.0 Feature flags
# ======================================================================

class TestFeatureFlags(unittest.TestCase):
    """Feature flags are OFF by default (no env vars set)."""

    def test_hardware_disabled_by_default(self):
        self.assertFalse(HARDWARE_ENABLED)

    def test_ibm_disabled_by_default(self):
        self.assertFalse(IBM_ENABLED)

    def test_google_disabled_by_default(self):
        self.assertFalse(GOOGLE_ENABLED)

    def test_ionq_disabled_by_default(self):
        self.assertFalse(IONQ_ENABLED)

    def test_braket_disabled_by_default(self):
        self.assertFalse(BRAKET_ENABLED)


# ======================================================================
# 6.1 Backend capabilities
# ======================================================================

class TestBackendCapabilities(unittest.TestCase):

    def test_default_capabilities(self):
        caps = BackendCapabilities()
        self.assertEqual(caps.provider, "simulator")
        self.assertEqual(caps.num_qubits, 32)
        self.assertTrue(caps.is_simulator)
        self.assertIn("H", caps.native_gates)
        self.assertIn("CNOT", caps.native_gates)

    def test_meets_requirements_pass(self):
        caps = BackendCapabilities(num_qubits=10, max_circuit_depth=100)
        self.assertTrue(caps.meets_requirements(min_qubits=5, max_depth=50))

    def test_meets_requirements_fail_qubits(self):
        caps = BackendCapabilities(num_qubits=4)
        self.assertFalse(caps.meets_requirements(min_qubits=8))

    def test_meets_requirements_fail_depth(self):
        caps = BackendCapabilities(max_circuit_depth=10)
        self.assertFalse(caps.meets_requirements(max_depth=100))

    def test_meets_requirements_fail_gates(self):
        caps = BackendCapabilities(native_gates={"H", "X"})
        self.assertFalse(caps.meets_requirements(required_gates={"CNOT", "H"}))

    def test_estimated_fidelity(self):
        caps = BackendCapabilities(
            single_qubit_error=0.001,
            two_qubit_error=0.01,
            readout_error=0.01,
        )
        fid = caps.estimated_fidelity(num_single=10, num_two=5, num_readout=1)
        self.assertGreater(fid, 0.0)
        self.assertLessEqual(fid, 1.0)
        # 10×0.001 + 5×0.01 ≈ 0.06 error in gates alone
        self.assertLess(fid, 1.0)


# ======================================================================
# 6.1 Backend registry
# ======================================================================

class TestBackendRegistry(unittest.TestCase):

    def test_register_and_get(self):
        reg = BackendRegistry()
        sim = _SimulatorWrapper()
        reg.register("test-sim", sim)
        self.assertIs(reg.get("test-sim"), sim)
        self.assertIn("test-sim", reg.list_backends())

    def test_unregister(self):
        reg = BackendRegistry()
        sim = _SimulatorWrapper()
        reg.register("tmp", sim)
        reg.unregister("tmp")
        self.assertIsNone(reg.get("tmp"))

    def test_list_available(self):
        reg = BackendRegistry()
        sim = _SimulatorWrapper()
        reg.register("sim", sim)
        # Simulator wrapper is always available
        self.assertIn("sim", reg.list_available())

    def test_auto_register_defaults(self):
        reg = BackendRegistry()
        reg.auto_register_defaults()
        backends = reg.list_backends()
        self.assertIn("ibm", backends)
        self.assertIn("google", backends)
        self.assertIn("ionq", backends)
        self.assertIn("braket", backends)
        self.assertIn("simulator", backends)

    def test_select_backend_simulator_fallback(self):
        reg = BackendRegistry()
        reg.auto_register_defaults()
        # No hardware is connected — simulator should be selected
        selected = reg.select_backend(min_qubits=2)
        self.assertIsNotNone(selected)


# ======================================================================
# 6.1 Hardware backends (fallback mode)
# ======================================================================

class TestIBMBackendFallback(unittest.TestCase):

    def test_not_available_without_flag(self):
        backend = IBMBackend()
        self.assertFalse(backend.is_available)

    def test_fallback_run(self):
        backend = IBMBackend()
        circuit = _bell_circuit()
        result = backend.run(circuit, repetitions=100)
        self.assertIsNotNone(result)
        self.assertEqual(len(result.measurements["result"]), 100)

    def test_fallback_simulate(self):
        backend = IBMBackend()
        q0, q1 = cirq.LineQubit.range(2)
        circuit = cirq.Circuit([cirq.H(q0), cirq.CNOT(q0, q1)])
        result = backend.simulate(circuit)
        self.assertIsNotNone(result)

    def test_capabilities(self):
        backend = IBMBackend()
        self.assertEqual(backend.capabilities.provider, "ibm")
        self.assertEqual(backend.capabilities.num_qubits, 127)
        self.assertFalse(backend.capabilities.is_simulator)

    def test_connect_fails_without_sdk(self):
        backend = IBMBackend()
        self.assertFalse(backend.connect())

    def test_default_calibration(self):
        backend = IBMBackend()
        cal = backend.get_calibration()
        self.assertIn("timestamp", cal)
        self.assertIn("t1_us", cal)


class TestGoogleBackendFallback(unittest.TestCase):

    def test_not_available(self):
        backend = GoogleBackend()
        self.assertFalse(backend.is_available)

    def test_fallback_run(self):
        backend = GoogleBackend()
        result = backend.run(_bell_circuit(), repetitions=50)
        self.assertEqual(len(result.measurements["result"]), 50)

    def test_capabilities(self):
        backend = GoogleBackend()
        self.assertEqual(backend.capabilities.provider, "google")


class TestIonQBackendFallback(unittest.TestCase):

    def test_not_available(self):
        backend = IonQBackend()
        self.assertFalse(backend.is_available)

    def test_fallback_run(self):
        backend = IonQBackend()
        result = backend.run(_bell_circuit(), repetitions=50)
        self.assertEqual(len(result.measurements["result"]), 50)

    def test_capabilities(self):
        backend = IonQBackend()
        self.assertEqual(backend.capabilities.provider, "ionq")
        # Trapped ions have all-to-all connectivity
        self.assertEqual(backend.capabilities.topology, TopologyType.ALL_TO_ALL)


class TestBraketBackendFallback(unittest.TestCase):

    def test_not_available(self):
        backend = BraketBackend()
        self.assertFalse(backend.is_available)

    def test_fallback_run(self):
        backend = BraketBackend()
        result = backend.run(_bell_circuit(), repetitions=50)
        self.assertEqual(len(result.measurements["result"]), 50)

    def test_capabilities(self):
        backend = BraketBackend()
        self.assertEqual(backend.capabilities.provider, "braket")


# ======================================================================
# 6.2 Topology mapper
# ======================================================================

class TestTopologyMapper(unittest.TestCase):

    def _caps(self, topo: TopologyType, n: int = 8) -> BackendCapabilities:
        return BackendCapabilities(num_qubits=n, topology=topo)

    def test_all_to_all_always_adjacent(self):
        mapper = TopologyMapper(self._caps(TopologyType.ALL_TO_ALL, 5))
        self.assertTrue(mapper.are_adjacent(0, 4))
        self.assertTrue(mapper.are_adjacent(2, 3))

    def test_linear_adjacent(self):
        mapper = TopologyMapper(self._caps(TopologyType.LINEAR, 5))
        self.assertTrue(mapper.are_adjacent(0, 1))
        self.assertFalse(mapper.are_adjacent(0, 2))

    def test_ring_wraps(self):
        mapper = TopologyMapper(self._caps(TopologyType.RING, 5))
        self.assertTrue(mapper.are_adjacent(0, 4))
        self.assertTrue(mapper.are_adjacent(0, 1))

    def test_grid_connectivity(self):
        mapper = TopologyMapper(self._caps(TopologyType.GRID, 9))
        # 3×3 grid: 0-1, 0-3, 4-1, 4-3, 4-5, 4-7
        self.assertTrue(mapper.are_adjacent(0, 1))
        self.assertTrue(mapper.are_adjacent(0, 3))
        self.assertFalse(mapper.are_adjacent(0, 4))

    def test_shortest_path(self):
        mapper = TopologyMapper(self._caps(TopologyType.LINEAR, 5))
        path = mapper.shortest_path(0, 4)
        self.assertEqual(path, [0, 1, 2, 3, 4])

    def test_map_logical_to_physical(self):
        caps = BackendCapabilities(num_qubits=8, topology=TopologyType.ALL_TO_ALL)
        mapper = TopologyMapper(caps)
        circuit = _bell_circuit()
        mapped, mapping = mapper.map_logical_to_physical(circuit)
        self.assertEqual(len(mapping), 2)
        self.assertIsInstance(mapped, cirq.Circuit)

    def test_map_raises_on_insufficient_qubits(self):
        caps = BackendCapabilities(num_qubits=1, topology=TopologyType.LINEAR)
        mapper = TopologyMapper(caps)
        with self.assertRaises(RuntimeError):
            mapper.map_logical_to_physical(_bell_circuit())

    def test_insert_swaps_on_linear(self):
        caps = BackendCapabilities(num_qubits=5, topology=TopologyType.LINEAR)
        mapper = TopologyMapper(caps)
        circuit = _bell_circuit()
        mapped, mapping = mapper.map_logical_to_physical(circuit)
        routed = mapper.insert_swaps(mapped, mapping)
        self.assertIsInstance(routed, cirq.Circuit)


# ======================================================================
# 6.2 Gate decomposer
# ======================================================================

class TestGateDecomposer(unittest.TestCase):

    def test_native_gate_passthrough(self):
        dec = GateDecomposer({"H", "CNOT", "X"})
        circuit = _bell_circuit()
        decomposed = dec.decompose_circuit(circuit)
        # Should not change if everything is native
        self.assertIsInstance(decomposed, cirq.Circuit)

    def test_decompose_non_native(self):
        # Only allow single-qubit gates
        dec = GateDecomposer({"H", "X", "Rz"})
        q0, q1 = cirq.LineQubit.range(2)
        circuit = cirq.Circuit([cirq.SWAP(q0, q1)])
        decomposed = dec.decompose_circuit(circuit)
        # cirq.SWAP decomposes into CNOTs
        self.assertIsInstance(decomposed, cirq.Circuit)


# ======================================================================
# 6.2 Calibration data
# ======================================================================

class TestCalibrationData(unittest.TestCase):

    def test_from_capabilities(self):
        caps = BackendCapabilities(num_qubits=5, single_qubit_error=0.002)
        cal = CalibrationData.from_capabilities(caps)
        self.assertEqual(len(cal.single_qubit_errors), 5)
        self.assertAlmostEqual(cal.single_qubit_errors[0], 0.002)

    def test_timestamp(self):
        cal = CalibrationData.from_capabilities(BackendCapabilities())
        self.assertGreater(cal.timestamp, 0)


# ======================================================================
# 6.2 Hardware compiler
# ======================================================================

class TestHardwareCompiler(unittest.TestCase):

    def test_compile_bell_circuit(self):
        caps = BackendCapabilities(num_qubits=10, topology=TopologyType.ALL_TO_ALL)
        compiler = HardwareCompiler(caps)
        result = compiler.compile(_bell_circuit())
        self.assertIn("compiled_circuit", result)
        self.assertIn("qubit_mapping", result)
        self.assertIn("stats", result)
        self.assertIn("estimated_fidelity", result["stats"])

    def test_compile_ghz(self):
        caps = BackendCapabilities(num_qubits=10, topology=TopologyType.LINEAR)
        compiler = HardwareCompiler(caps)
        result = compiler.compile(_ghz_circuit(4))
        self.assertGreater(result["stats"]["total_operations"], 0)

    def test_cancel_adjacent_inverses(self):
        q = cirq.LineQubit(0)
        circuit = cirq.Circuit([cirq.X(q), cirq.X(q), cirq.H(q)])
        caps = BackendCapabilities(num_qubits=5, topology=TopologyType.ALL_TO_ALL)
        compiler = HardwareCompiler(caps)
        result = compiler.compile(circuit, optimisation_level=1)
        # X·X should be cancelled, leaving just H
        ops = list(result["compiled_circuit"].all_operations())
        self.assertLess(len(ops), 3)

    def test_stats_fidelity_range(self):
        caps = BackendCapabilities(num_qubits=10)
        compiler = HardwareCompiler(caps)
        result = compiler.compile(_bell_circuit())
        fid = result["stats"]["estimated_fidelity"]
        self.assertGreater(fid, 0.0)
        self.assertLessEqual(fid, 1.0)


# ======================================================================
# 6.3 Workload partitioner
# ======================================================================

class TestWorkloadPartitioner(unittest.TestCase):

    def test_small_circuit_classical(self):
        caps = BackendCapabilities(num_qubits=30)
        wp = WorkloadPartitioner(caps)
        q = cirq.LineQubit(0)
        tiny = cirq.Circuit([cirq.H(q)])
        analysis = wp.analyse(tiny)
        self.assertEqual(analysis.workload_type, WorkloadType.CLASSICAL)

    def test_medium_circuit_hybrid(self):
        caps = BackendCapabilities(num_qubits=30)
        wp = WorkloadPartitioner(caps)
        analysis = wp.analyse(_ghz_circuit(8))
        self.assertIn(analysis.workload_type, [WorkloadType.HYBRID, WorkloadType.QUANTUM])

    def test_oversized_circuit_knitting(self):
        caps = BackendCapabilities(num_qubits=5)
        wp = WorkloadPartitioner(caps)
        analysis = wp.analyse(_large_circuit(10))
        self.assertTrue(analysis.exceeds_device)
        self.assertTrue(analysis.knitting_required)


# ======================================================================
# 6.3 Circuit knitter
# ======================================================================

class TestCircuitKnitter(unittest.TestCase):

    def test_no_cut_needed(self):
        knitter = CircuitKnitter(max_qubits=10)
        fragments = knitter.cut(_bell_circuit())
        self.assertEqual(len(fragments), 1)

    def test_cut_required(self):
        knitter = CircuitKnitter(max_qubits=3)
        fragments = knitter.cut(_ghz_circuit(6))
        self.assertGreaterEqual(len(fragments), 1)

    def test_reconstruct(self):
        knitter = CircuitKnitter(max_qubits=10)
        sim = cirq.Simulator()
        result = sim.run(_bell_circuit(), repetitions=10)
        combined = knitter.reconstruct([result])
        self.assertIsInstance(combined, dict)


# ======================================================================
# 6.3 Error budget manager
# ======================================================================

class TestErrorBudgetManager(unittest.TestCase):

    def test_allocate(self):
        caps = BackendCapabilities(
            single_qubit_error=0.001,
            two_qubit_error=0.01,
            readout_error=0.01,
        )
        mgr = ErrorBudgetManager(total_budget=0.1)
        budget = mgr.allocate(_bell_circuit(), caps)
        self.assertGreater(budget.total_budget, 0)
        self.assertIsInstance(budget.remaining, float)

    def test_is_within_budget(self):
        mgr = ErrorBudgetManager(total_budget=1.0)
        caps = BackendCapabilities()
        budget = mgr.allocate(_bell_circuit(), caps)
        self.assertTrue(mgr.is_within_budget(budget))


# ======================================================================
# 6.3 Hybrid executor
# ======================================================================

class TestHybridExecutor(unittest.TestCase):

    def setUp(self):
        self.backend = _SimulatorWrapper()
        self.executor = HybridExecutor(self.backend)

    def test_execute_classical_path(self):
        q = cirq.LineQubit(0)
        tiny = cirq.Circuit([cirq.H(q), cirq.measure(q, key="m")])
        result = self.executor.execute(tiny, repetitions=100)
        self.assertEqual(result["strategy"], "classical")
        self.assertIsNotNone(result["result"])

    def test_execute_quantum_path(self):
        result = self.executor.execute(_ghz_circuit(8), repetitions=100)
        self.assertIn(result["strategy"], ["quantum", "hybrid"])
        self.assertIsNotNone(result["result"])

    def test_execute_knitted_path(self):
        # Use a backend with very few qubits
        caps = BackendCapabilities(num_qubits=3, topology=TopologyType.ALL_TO_ALL, is_simulator=True)
        small_backend = _SimulatorWrapper()
        small_backend._capabilities = caps
        executor = HybridExecutor(small_backend)
        # Circuit with 6 non-adjacent qubits of independent H gates
        qubits = cirq.LineQubit.range(6)
        circuit = cirq.Circuit([cirq.H(q) for q in qubits] + [cirq.measure(*qubits[:3], key="a")])
        result = executor.execute(circuit, repetitions=50)
        # Should use knitting since circuit needs 6 qubits but device has 3
        self.assertIsNotNone(result)

    def test_mid_circuit_measurement(self):
        q0, q1 = cirq.LineQubit.range(2)
        circuit = cirq.Circuit([
            cirq.H(q0),
            cirq.measure(q0, key="mid"),
            cirq.CNOT(q0, q1),
            cirq.measure(q0, q1, key="final"),
        ])
        result = self.executor.execute_with_mid_circuit_measurement(
            circuit, ["mid", "final"], repetitions=50,
        )
        self.assertIsNotNone(result)


# ======================================================================
# 6.4 Calibration monitor
# ======================================================================

class TestCalibrationMonitor(unittest.TestCase):

    def test_refresh(self):
        backend = _SimulatorWrapper()
        monitor = CalibrationMonitor(backend)
        cal = monitor.refresh()
        self.assertIsNotNone(cal)
        self.assertIsNotNone(monitor.latest)

    def test_needs_refresh_initially(self):
        backend = _SimulatorWrapper()
        monitor = CalibrationMonitor(backend, refresh_interval_s=0.0)
        self.assertTrue(monitor.needs_refresh())

    def test_no_alerts_initially(self):
        backend = _SimulatorWrapper()
        monitor = CalibrationMonitor(backend)
        monitor.refresh()
        self.assertEqual(len(monitor.alerts), 0)

    def test_clear_alerts(self):
        backend = _SimulatorWrapper()
        monitor = CalibrationMonitor(backend)
        monitor._alerts.append({"type": "test"})
        monitor.clear_alerts()
        self.assertEqual(len(monitor.alerts), 0)


# ======================================================================
# 6.4 Error mitigator
# ======================================================================

class TestErrorMitigator(unittest.TestCase):

    def test_select_strategy_none(self):
        # Simulator with perfect fidelity
        caps = BackendCapabilities(
            single_qubit_error=0.0, two_qubit_error=0.0, readout_error=0.0,
        )
        em = ErrorMitigator(caps)
        strategy = em.select_strategy(_bell_circuit(), desired_fidelity=0.9)
        self.assertEqual(strategy, MitigationStrategy.NONE)

    def test_select_strategy_measurement(self):
        caps = BackendCapabilities(readout_error=0.1, two_qubit_error=0.001)
        em = ErrorMitigator(caps)
        strategy = em.select_strategy(_bell_circuit(), desired_fidelity=0.99)
        self.assertEqual(strategy, MitigationStrategy.MEASUREMENT_ERROR_MITIGATION)

    def test_apply_none(self):
        caps = BackendCapabilities()
        em = ErrorMitigator(caps)
        counts = {"00": 500, "11": 500}
        result = em.apply(MitigationStrategy.NONE, counts)
        self.assertAlmostEqual(result["00"], 0.5)
        self.assertAlmostEqual(result["11"], 0.5)

    def test_apply_measurement_mitigation(self):
        caps = BackendCapabilities(readout_error=0.05)
        em = ErrorMitigator(caps)
        cal = CalibrationData.from_capabilities(caps)
        counts = {"00": 400, "01": 50, "10": 50, "11": 500}
        result = em.apply(MitigationStrategy.MEASUREMENT_ERROR_MITIGATION, counts, cal)
        self.assertIsInstance(result, dict)
        total = sum(result.values())
        self.assertAlmostEqual(total, 1.0, places=5)

    def test_apply_zne(self):
        caps = BackendCapabilities()
        em = ErrorMitigator(caps)
        counts = {"00": 600, "11": 400}
        result = em.apply(MitigationStrategy.ZERO_NOISE_EXTRAPOLATION, counts)
        self.assertIsInstance(result, dict)
        self.assertAlmostEqual(sum(result.values()), 1.0, places=5)

    def test_apply_empty_counts(self):
        caps = BackendCapabilities()
        em = ErrorMitigator(caps)
        result = em.apply(MitigationStrategy.NONE, {})
        self.assertEqual(result, {})


# ======================================================================
# 6.4 Hardware noise model
# ======================================================================

class TestHardwareNoiseModel(unittest.TestCase):

    def test_build_noise_model(self):
        caps = BackendCapabilities(two_qubit_error=0.01)
        hnm = HardwareNoiseModel(caps)
        model = hnm.build_noise_model()
        self.assertIsNotNone(model)

    def test_simulate_with_noise(self):
        caps = BackendCapabilities(two_qubit_error=0.01)
        hnm = HardwareNoiseModel(caps)
        result = hnm.simulate_with_noise(_bell_circuit(), repetitions=50)
        self.assertEqual(len(result.measurements["result"]), 50)


# ======================================================================
# 6.4 Fidelity scorer
# ======================================================================

class TestFidelityScorer(unittest.TestCase):

    def test_score_simulator(self):
        caps = BackendCapabilities(is_simulator=True)
        scorer = FidelityScorer(caps)
        report = scorer.score(_bell_circuit())
        self.assertIsInstance(report, FidelityReport)
        self.assertGreater(report.estimated_fidelity, 0.0)
        self.assertTrue(any("Running on simulator" in w for w in report.warnings))

    def test_score_noisy_device(self):
        caps = BackendCapabilities(
            single_qubit_error=0.01,
            two_qubit_error=0.05,
            readout_error=0.03,
            is_simulator=False,
            t2_us=10.0,
            two_qubit_gate_time_ns=500.0,
        )
        scorer = FidelityScorer(caps)
        report = scorer.score(_ghz_circuit(10))
        self.assertLess(report.estimated_fidelity, 1.0)
        self.assertIn(report.confidence_level, ["high", "medium", "low", "very_low"])

    def test_mitigation_improves_fidelity(self):
        caps = BackendCapabilities(
            single_qubit_error=0.005,
            two_qubit_error=0.03,
            readout_error=0.02,
            is_simulator=False,
        )
        scorer = FidelityScorer(caps)
        no_mit = scorer.score(_ghz_circuit(6), MitigationStrategy.NONE)
        with_mit = scorer.score(_ghz_circuit(6), MitigationStrategy.ZERO_NOISE_EXTRAPOLATION)
        self.assertGreaterEqual(with_mit.estimated_fidelity, no_mit.estimated_fidelity)


# ======================================================================
# 6.4 Circuit retry manager
# ======================================================================

class TestCircuitRetryManager(unittest.TestCase):

    def test_success_first_try(self):
        mgr = CircuitRetryManager(max_retries=3)
        sim = cirq.Simulator()
        result = mgr.execute_with_retry(
            lambda c, r: sim.run(c, repetitions=r),
            _bell_circuit(),
            repetitions=50,
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 1)

    def test_retry_on_failure(self):
        mgr = CircuitRetryManager(max_retries=2, backoff_base_s=0.01)
        call_count = [0]

        def failing_run(circuit, reps):
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("Simulated hardware error")
            return cirq.Simulator().run(circuit, repetitions=reps)

        result = mgr.execute_with_retry(failing_run, _bell_circuit(), repetitions=10)
        self.assertTrue(result["success"])
        self.assertEqual(result["attempts"], 3)

    def test_all_retries_fail(self):
        mgr = CircuitRetryManager(max_retries=1, backoff_base_s=0.01)

        def always_fail(circuit, reps):
            raise RuntimeError("Always fails")

        result = mgr.execute_with_retry(always_fail, _bell_circuit())
        self.assertFalse(result["success"])
        self.assertEqual(result["attempts"], 2)
        self.assertIn("last_error", result)

    def test_history_tracking(self):
        mgr = CircuitRetryManager(max_retries=0)
        sim = cirq.Simulator()
        mgr.execute_with_retry(
            lambda c, r: sim.run(c, repetitions=r),
            _bell_circuit(),
        )
        self.assertEqual(len(mgr.history), 1)
        self.assertTrue(mgr.history[0]["success"])


# ======================================================================
# Integration: end-to-end
# ======================================================================

class TestEndToEnd(unittest.TestCase):
    """Integration test: full pipeline from registry → compile → execute."""

    def test_full_pipeline(self):
        # 1. Registry
        registry = BackendRegistry()
        registry.auto_register_defaults()

        # 2. Select best backend
        backend = registry.select_backend(min_qubits=4)
        self.assertIsNotNone(backend)

        # 3. Compile
        compiler = HardwareCompiler(backend.capabilities)
        compiled = compiler.compile(_ghz_circuit(4))
        self.assertIn("compiled_circuit", compiled)

        # 4. Fidelity check
        scorer = FidelityScorer(backend.capabilities)
        report = scorer.score(compiled["compiled_circuit"])
        self.assertGreater(report.estimated_fidelity, 0.0)

        # 5. Execute via hybrid executor
        executor = HybridExecutor(backend, compiler)
        result = executor.execute(_ghz_circuit(4), repetitions=100)
        self.assertIsNotNone(result["result"])

    def test_import_from_shim(self):
        """Verify backward-compat shim re-exports hardware symbols."""
        from qndb.core.quantum_engine import (
            HARDWARE_ENABLED,
            BackendRegistry,
            HardwareCompiler,
            HybridExecutor,
            FidelityScorer,
        )
        self.assertIsNotNone(BackendRegistry)
        self.assertIsNotNone(HardwareCompiler)

    def test_import_from_engine_package(self):
        from qndb.core.engine import (
            BackendRegistry,
            IBMBackend,
            GoogleBackend,
            IonQBackend,
            BraketBackend,
        )
        self.assertIsNotNone(BackendRegistry)
        self.assertIsNotNone(IBMBackend)


if __name__ == "__main__":
    unittest.main()
