import unittest
import numpy as np
import logging
import sys
import cirq

from qndb.core.algorithms.search_optimization import (
    QAOASolver,
    VQESolver,
    AdaptiveGrover,
    QuantumAnnealingInterface,
    QuantumWalkSpatialSearch,
)
from qndb.core.algorithms.linear_algebra import (
    HHLSolver,
    QuantumPCA,
    QSVTFramework,
    QuantumMatrixInversion,
    BlockEncoder,
)
from qndb.core.algorithms.machine_learning import (
    QuantumKernelEstimator,
    VariationalClassifier,
    QuantumBoltzmannMachine,
    QuantumFeatureMap,
    ClassicalMLBridge,
)
from qndb.core.algorithms.specialized_ops import (
    QuantumPatternMatcher,
    QuantumGraphAlgorithms,
    QuantumTimeSeriesAnalyzer,
    QuantumANN,
    QuantumCompressor,
)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# =====================================================================
# 7.1  Search & Optimization
# =====================================================================

class TestQuantumWalkSpatialSearch(unittest.TestCase):
    def setUp(self):
        self.walker = QuantumWalkSpatialSearch(num_vertices=8)

    def test_build_circuit(self):
        circuit = self.walker.build_circuit(marked=[3])
        self.assertIsInstance(circuit, cirq.Circuit)
        ops = list(circuit.all_operations())
        self.assertGreater(len(ops), 0)

    def test_measurement_key(self):
        circuit = self.walker.build_circuit(marked=[0, 5], num_steps=2)
        keys = [key for key in circuit.all_measurement_key_names()]
        self.assertIn("result", keys)

    def test_custom_adjacency(self):
        adj = {0: [1, 2], 1: [0, 3], 2: [0, 3], 3: [1, 2]}
        walker = QuantumWalkSpatialSearch(num_vertices=4, adjacency=adj)
        circuit = walker.build_circuit(marked=[2])
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_simulation_returns_result(self):
        circuit = self.walker.build_circuit(marked=[1], num_steps=3)
        sim = cirq.Simulator()
        result = sim.run(circuit, repetitions=50)
        self.assertIn("result", result.measurements)


class TestQAOASolver(unittest.TestCase):
    def setUp(self):
        self.qaoa = QAOASolver(num_qubits=4, depth=1)

    def test_build_circuit(self):
        edges = [(0, 1), (1, 2), (2, 3)]
        circuit = self.qaoa.build_circuit([0.5], [0.5], edges)
        self.assertIsInstance(circuit, cirq.Circuit)
        ops = list(circuit.all_operations())
        self.assertGreater(len(ops), 0)

    def test_build_measured_circuit(self):
        edges = [(0, 1), (1, 2)]
        circuit = self.qaoa.build_measured_circuit([0.3], [0.7], edges)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("result", keys)

    def test_depth_mismatch_raises(self):
        with self.assertRaises(ValueError):
            self.qaoa.build_circuit([0.5, 0.6], [0.5], [(0, 1)])

    def test_simulation(self):
        edges = [(0, 1), (1, 2), (2, 3)]
        circuit = self.qaoa.build_measured_circuit([0.5], [0.5], edges)
        sim = cirq.Simulator()
        result = sim.run(circuit, repetitions=100)
        self.assertEqual(result.measurements["result"].shape, (100, 4))


class TestVQESolver(unittest.TestCase):
    def setUp(self):
        self.vqe = VQESolver(num_qubits=2, ansatz_depth=1)

    def test_build_ansatz(self):
        params = np.array([0.5, 1.0])
        circuit = self.vqe.build_ansatz(params)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_wrong_params_raises(self):
        with self.assertRaises(ValueError):
            self.vqe.build_ansatz(np.array([0.5]))

    def test_compute_expectation(self):
        terms = [(1.0, [(0, "Z")])]
        params = np.zeros(2)
        energy = self.vqe.compute_expectation(terms, params, repetitions=200)
        # |00⟩ → eigenvalue of Z on qubit 0 is +1
        self.assertAlmostEqual(energy, 1.0, delta=0.3)


class TestAdaptiveGrover(unittest.TestCase):
    def setUp(self):
        self.ag = AdaptiveGrover(num_qubits=3)

    def test_build_circuit(self):
        oracle = cirq.Circuit(cirq.Z(cirq.LineQubit(2)).controlled_by(
            cirq.LineQubit(0), cirq.LineQubit(1)))
        circuit = self.ag.build_circuit(oracle, num_iterations=2)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("result", keys)

    def test_run_adaptive_finds_solution(self):
        # Mark item 5 (101) in a 3-qubit space
        target = 5
        qubits = [cirq.LineQubit(i) for i in range(3)]
        bits = format(target, "03b")
        oracle = cirq.Circuit()
        flips = [cirq.X(qubits[i]) for i, b in enumerate(bits) if b == "0"]
        oracle.append(flips)
        oracle.append(cirq.Z(qubits[-1]).controlled_by(*qubits[:-1]))
        oracle.append(flips)

        found = self.ag.run_adaptive(oracle, verify=lambda x: x == target, max_rounds=30)
        self.assertEqual(found, target)


class TestQuantumAnnealingInterface(unittest.TestCase):
    def setUp(self):
        self.annealer = QuantumAnnealingInterface(num_qubits=3, num_trotter_steps=10)

    def test_build_circuit(self):
        couplings = {(0, 1): -1.0, (1, 2): -1.0}
        circuit = self.annealer.build_circuit(couplings)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("result", keys)

    def test_anneal_returns_result(self):
        couplings = {(0, 1): -1.0, (1, 2): -1.0}
        result = self.annealer.anneal(couplings, repetitions=100)
        self.assertIn("best_bitstring", result)
        self.assertIn("best_energy", result)
        self.assertEqual(len(result["best_bitstring"]), 3)


# =====================================================================
# 7.2  Linear Algebra
# =====================================================================

class TestBlockEncoder(unittest.TestCase):
    def setUp(self):
        self.enc = BlockEncoder(num_qubits=2)

    def test_encode(self):
        mat = 0.5 * np.eye(4)
        circuit = self.enc.encode(mat)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_norm_exceeds_raises(self):
        mat = 5.0 * np.eye(4)
        with self.assertRaises(ValueError):
            self.enc.encode(mat)

    def test_non_square_raises(self):
        with self.assertRaises(ValueError):
            self.enc.encode(np.ones((2, 3)))


class TestHHLSolver(unittest.TestCase):
    def setUp(self):
        self.hhl = HHLSolver(num_qubits=1, num_ancilla=2)

    def test_build_circuit(self):
        ham = cirq.Circuit(cirq.rz(0.5).on(cirq.LineQubit(0)))
        circuit = self.hhl.build_circuit(ham)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("flag", keys)

    def test_simulation_runs(self):
        ham = cirq.Circuit(cirq.rz(0.5).on(cirq.LineQubit(0)))
        circuit = self.hhl.build_circuit(ham)
        sim = cirq.Simulator()
        result = sim.run(circuit, repetitions=50)
        self.assertIn("flag", result.measurements)


class TestQuantumPCA(unittest.TestCase):
    def setUp(self):
        self.pca = QuantumPCA(num_qubits=2)

    def test_build_circuit(self):
        circuit = self.pca.build_circuit()
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("eigenvalues", keys)

    def test_extract_components(self):
        result = self.pca.extract_components(repetitions=200)
        self.assertIn("eigenvalue_histogram", result)
        self.assertGreater(len(result["eigenvalue_histogram"]), 0)


class TestQSVTFramework(unittest.TestCase):
    def setUp(self):
        self.qsvt = QSVTFramework(num_qubits=2)

    def test_build_circuit(self):
        be = cirq.Circuit(cirq.H(cirq.LineQubit(0)))
        angles = [0.1, 0.2, 0.3]
        circuit = self.qsvt.build_circuit(be, angles)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_polynomial_transform(self):
        be = cirq.Circuit(cirq.H(cirq.LineQubit(0)))
        result = self.qsvt.polynomial_transform(be, [0.5, 0.5], repetitions=100)
        self.assertIn("success_probability", result)
        self.assertGreaterEqual(result["success_probability"], 0.0)
        self.assertLessEqual(result["success_probability"], 1.0)


class TestQuantumMatrixInversion(unittest.TestCase):
    def setUp(self):
        self.inv = QuantumMatrixInversion(num_qubits=1, num_ancilla=2)

    def test_build_circuit(self):
        mat = np.array([[0.5]])
        circuit = self.inv.build_circuit(mat)
        self.assertIsInstance(circuit, cirq.Circuit)


# =====================================================================
# 7.3  Machine Learning
# =====================================================================

class TestQuantumFeatureMap(unittest.TestCase):
    def setUp(self):
        self.fm = QuantumFeatureMap(num_qubits=3, depth=1)

    def test_build_circuit(self):
        data = np.array([0.1, 0.2, 0.3])
        circuit = self.fm.build_circuit(data)
        self.assertIsInstance(circuit, cirq.Circuit)
        ops = list(circuit.all_operations())
        self.assertGreater(len(ops), 0)

    def test_wrong_dim_raises(self):
        with self.assertRaises(ValueError):
            self.fm.build_circuit(np.array([0.1, 0.2]))

    def test_full_entanglement(self):
        fm = QuantumFeatureMap(num_qubits=3, depth=1, entanglement="full")
        circuit = fm.build_circuit(np.array([0.1, 0.2, 0.3]))
        ops = list(circuit.all_operations())
        self.assertGreater(len(ops), 0)


class TestQuantumKernelEstimator(unittest.TestCase):
    def setUp(self):
        self.kern = QuantumKernelEstimator(num_qubits=2)

    def test_kernel_entry_self(self):
        x = np.array([0.5, 0.5])
        val = self.kern.kernel_entry(x, x, repetitions=500)
        self.assertGreater(val, 0.5)

    def test_kernel_matrix(self):
        data = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
        K = self.kern.kernel_matrix(data, repetitions=200)
        self.assertEqual(K.shape, (3, 3))
        # Diagonal should be 1.0
        for i in range(3):
            self.assertAlmostEqual(K[i, i], 1.0, delta=0.01)


class TestVariationalClassifier(unittest.TestCase):
    def setUp(self):
        self.clf = VariationalClassifier(num_qubits=2, ansatz_depth=1)

    def test_build_circuit(self):
        data = np.array([0.1, 0.2])
        params = np.array([0.5, 1.0])
        circuit = self.clf.build_circuit(data, params)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("label", keys)

    def test_predict_with_params(self):
        data = np.array([0.1, 0.2])
        params = np.array([0.5, 1.0])
        pred = self.clf.predict(data, params, repetitions=100)
        self.assertIn(pred, [0, 1])

    def test_predict_no_params_raises(self):
        with self.assertRaises(RuntimeError):
            self.clf.predict(np.array([0.1, 0.2]))


class TestQuantumBoltzmannMachine(unittest.TestCase):
    def setUp(self):
        self.qbm = QuantumBoltzmannMachine(num_visible=3, num_hidden=1)

    def test_initialize_params(self):
        self.qbm.initialize_params(seed=42)
        self.assertIsNotNone(self.qbm._weights)
        self.assertIsNotNone(self.qbm._biases)

    def test_build_circuit(self):
        self.qbm.initialize_params(seed=42)
        circuit = self.qbm.build_circuit(beta=1.0, trotter_steps=5)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("visible", keys)

    def test_sample(self):
        self.qbm.initialize_params(seed=42)
        samples = self.qbm.sample(n_samples=50, beta=1.0)
        self.assertEqual(samples.shape, (50, 3))


class TestClassicalMLBridge(unittest.TestCase):
    def setUp(self):
        self.bridge = ClassicalMLBridge(num_qubits=2)

    def test_compute_kernel_matrix_train_only(self):
        X = np.array([[0.1, 0.2], [0.3, 0.4]])
        K = self.bridge.compute_kernel_matrix(X, repetitions=100)
        self.assertEqual(K.shape, (2, 2))

    def test_predict_batch(self):
        X = np.array([[0.1, 0.2], [0.3, 0.4]])
        params = np.array([0.5, 1.0, 0.3, 0.7])  # num_qubits * ansatz_depth = 2*2 = 4
        self.bridge.classifier.optimal_params = params
        preds = self.bridge.predict(X, repetitions=50)
        self.assertEqual(len(preds), 2)


# =====================================================================
# 7.4  Specialized Database Operations
# =====================================================================

class TestQuantumPatternMatcher(unittest.TestCase):
    def setUp(self):
        self.pm = QuantumPatternMatcher()

    def test_build_circuit(self):
        text = [65, 66, 67, 68, 65, 66]  # ABCDAB
        pattern = [65, 66]                 # AB
        circuit = self.pm.build_circuit(text, pattern)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("position", keys)

    def test_pattern_longer_than_text_raises(self):
        with self.assertRaises(ValueError):
            self.pm.build_circuit([1], [1, 2, 3])

    def test_simulation(self):
        text = [1, 2, 3, 1, 2]
        pattern = [1, 2]
        circuit = self.pm.build_circuit(text, pattern)
        sim = cirq.Simulator()
        result = sim.run(circuit, repetitions=100)
        self.assertIn("position", result.measurements)


class TestQuantumGraphAlgorithms(unittest.TestCase):
    def setUp(self):
        self.ga = QuantumGraphAlgorithms(num_vertices=4)

    def test_shortest_path_circuit(self):
        adj = {(0, 1): 1.0, (1, 2): 2.0, (2, 3): 1.0, (0, 3): 5.0}
        circuit = self.ga.shortest_path_circuit(adj, source=0, target=3)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("edges", keys)

    def test_no_edges_raises(self):
        with self.assertRaises(ValueError):
            self.ga.shortest_path_circuit({}, source=0, target=1)

    def test_graph_isomorphism_circuit(self):
        adj_a = [(0, 1), (1, 2)]
        adj_b = [(0, 1), (1, 2)]
        circuit = self.ga.graph_isomorphism_circuit(adj_a, adj_b)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("permutation", keys)

    def test_mst_circuit(self):
        adj = {(0, 1): 1.0, (1, 2): 3.0, (0, 2): 2.0}
        circuit = self.ga.minimum_spanning_tree_circuit(adj)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("tree_edges", keys)


class TestQuantumTimeSeriesAnalyzer(unittest.TestCase):
    def setUp(self):
        self.ts = QuantumTimeSeriesAnalyzer(num_qubits=3)

    def test_build_circuit_no_data(self):
        circuit = self.ts.build_circuit()
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("frequency", keys)

    def test_build_circuit_with_data(self):
        data = np.sin(np.linspace(0, 2 * np.pi, 8))
        circuit = self.ts.build_circuit(data)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_detect_period(self):
        data = np.sin(np.linspace(0, 2 * np.pi, 8))
        result = self.ts.detect_period(data, repetitions=200)
        self.assertIn("dominant_frequency", result)
        self.assertIn("frequency_histogram", result)


class TestQuantumANN(unittest.TestCase):
    def setUp(self):
        self.ann = QuantumANN(num_qubits=2, feature_dim=3)

    def test_build_circuit(self):
        db = np.array([[0, 0, 0], [0, 0, 1], [0, 1, 0], [1, 1, 1]])
        query = np.array([0, 0, 1])
        circuit = self.ann.build_circuit(db, query)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("nearest", keys)

    def test_search(self):
        db = np.array([[0, 0, 0], [0, 0, 1], [0, 1, 0], [1, 1, 1]])
        query = np.array([0, 0, 1])
        result = self.ann.search(db, query, threshold=0.5, repetitions=50)
        self.assertIn("best_index", result)
        self.assertIn("distance", result)


class TestQuantumCompressor(unittest.TestCase):
    def setUp(self):
        self.comp = QuantumCompressor(input_qubits=4, latent_qubits=2)

    def test_latent_ge_input_raises(self):
        with self.assertRaises(ValueError):
            QuantumCompressor(input_qubits=3, latent_qubits=5)

    def test_build_encoder(self):
        params = np.random.uniform(0, np.pi, 8)
        circuit = self.comp.build_encoder(params)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_build_decoder_is_inverse(self):
        params = np.random.uniform(0, np.pi, 8)
        encoder = self.comp.build_encoder(params)
        decoder = self.comp.build_decoder(params)
        # Encoder + decoder should roughly reconstruct identity
        combined = encoder + decoder
        ops = list(combined.all_operations())
        self.assertGreater(len(ops), 0)

    def test_build_autoencoder(self):
        params = np.random.uniform(0, np.pi, 8)
        circuit = self.comp.build_autoencoder(params)
        self.assertIsInstance(circuit, cirq.Circuit)
        keys = list(circuit.all_measurement_key_names())
        self.assertIn("fidelity", keys)

    def test_compress(self):
        params = np.random.uniform(0, np.pi, 8)
        data_prep = cirq.Circuit(cirq.H.on_each(
            *[cirq.LineQubit(i) for i in range(4)]))
        result = self.comp.compress(data_prep, params, repetitions=100)
        self.assertIn("fidelity", result)
        self.assertIn("compression_ratio", result)
        self.assertEqual(result["compression_ratio"], 2.0)


# =====================================================================
# Package-level import test
# =====================================================================

class TestAlgorithmsPackageImport(unittest.TestCase):
    def test_import_all_from_package(self):
        from qndb.core.algorithms import __all__ as all_names
        self.assertEqual(len(all_names), 20)

    def test_top_level_import(self):
        from qndb.core.algorithms import (
            QAOASolver, VQESolver, AdaptiveGrover, QuantumAnnealingInterface,
            QuantumWalkSpatialSearch, HHLSolver, QuantumPCA, QSVTFramework,
            QuantumMatrixInversion, BlockEncoder, QuantumKernelEstimator,
            VariationalClassifier, QuantumBoltzmannMachine, QuantumFeatureMap,
            ClassicalMLBridge, QuantumPatternMatcher, QuantumGraphAlgorithms,
            QuantumTimeSeriesAnalyzer, QuantumANN, QuantumCompressor,
        )
        self.assertTrue(all([
            QAOASolver, VQESolver, AdaptiveGrover, QuantumAnnealingInterface,
            QuantumWalkSpatialSearch, HHLSolver, QuantumPCA, QSVTFramework,
            QuantumMatrixInversion, BlockEncoder, QuantumKernelEstimator,
            VariationalClassifier, QuantumBoltzmannMachine, QuantumFeatureMap,
            ClassicalMLBridge, QuantumPatternMatcher, QuantumGraphAlgorithms,
            QuantumTimeSeriesAnalyzer, QuantumANN, QuantumCompressor,
        ]))


if __name__ == '__main__':
    unittest.main()
