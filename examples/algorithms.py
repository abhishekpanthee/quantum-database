"""
Quantum Algorithms — Advanced Search, Linear Algebra & ML
==========================================================

Demonstrates the Phase 7 quantum algorithms: Grover variants,
QAOA, VQE, HHL, quantum PCA, kernel methods, and pattern matching.
"""

from qndb.core.algorithms import (
    AdaptiveGrover,
    QAOASolver,
    VQESolver,
    QuantumWalkSpatialSearch,
    HHLSolver,
    QuantumPCA,
    QSVTFramework,
    QuantumKernelEstimator,
    VariationalClassifier,
    QuantumPatternMatcher,
    QuantumGraphAlgorithms,
    QuantumCompressor,
)


def search_and_optimization():
    """Grover, QAOA, VQE demos."""
    print("=== Search & Optimization ===\n")

    # Adaptive Grover search
    grover = AdaptiveGrover(num_qubits=6)
    result = grover.search(target_state=42, max_iterations=100)
    print(f"Grover found state={result.state}, p={result.probability:.4f}")

    # QAOA for combinatorial optimization
    qaoa = QAOASolver(num_qubits=4, num_layers=3)
    cost_terms = [(0, 1, 1.0), (1, 2, -0.5), (2, 3, 0.8)]
    result = qaoa.solve(cost_terms, steps=50)
    print(f"QAOA optimal: {result.optimal_params}, energy={result.energy:.4f}")

    # VQE for ground-state energy
    vqe = VQESolver(num_qubits=4, ansatz="hardware_efficient")
    hamiltonian = {"ZZ": [(0, 1, 1.0)], "X": [(0, 0.5), (1, 0.5)]}
    result = vqe.compute_ground_state(hamiltonian, max_iterations=100)
    print(f"VQE ground-state energy: {result.energy:.4f}")

    # Quantum walk search
    walk = QuantumWalkSpatialSearch(num_nodes=16)
    result = walk.search(marked_node=7, steps=20)
    print(f"Walk search found node={result.found_node}, steps={result.steps_taken}")


def linear_algebra():
    """HHL, quantum PCA, QSVT demos."""
    print("\n=== Linear Algebra ===\n")

    # HHL for solving Ax = b
    hhl = HHLSolver(num_qubits=4)
    A = [[1.0, 0.5], [0.5, 1.0]]
    b = [1.0, 0.0]
    result = hhl.solve(A, b)
    print(f"HHL solution: {result.solution}")
    print(f"Condition number: {result.condition_number:.2f}")

    # Quantum PCA
    pca = QuantumPCA(num_qubits=4)
    data_matrix = [[1.0, 0.8], [0.8, 1.0]]
    result = pca.analyze(data_matrix, num_components=2)
    print(f"Principal eigenvalues: {result.eigenvalues}")

    # QSVT framework
    qsvt = QSVTFramework(num_qubits=6)
    poly_coeffs = [1.0, 0.0, -0.5]  # polynomial transformation
    result = qsvt.apply_polynomial(poly_coeffs, precision=1e-3)
    print(f"QSVT circuit depth: {result.circuit_depth}")


def machine_learning():
    """Quantum kernel estimation and variational classifier."""
    print("\n=== Machine Learning ===\n")

    # Quantum kernel
    kernel = QuantumKernelEstimator(num_qubits=4, feature_map="ZZFeatureMap")
    X_train = [[0.1, 0.2], [0.8, 0.9], [0.3, 0.7]]
    kernel_matrix = kernel.compute_kernel(X_train)
    print(f"Kernel matrix shape: {kernel_matrix.shape}")

    # Variational classifier
    clf = VariationalClassifier(num_qubits=4, num_layers=2)
    X = [[0.1, 0.2], [0.8, 0.9], [0.3, 0.7], [0.6, 0.1]]
    y = [0, 1, 1, 0]
    clf.fit(X, y, epochs=50)
    predictions = clf.predict([[0.5, 0.5]])
    print(f"Classifier prediction: {predictions}")


def specialized_ops():
    """Pattern matching, graph algorithms, compression."""
    print("\n=== Specialized Operations ===\n")

    # Pattern matching
    matcher = QuantumPatternMatcher(num_qubits=8)
    text = "quantum database engine"
    matches = matcher.find_pattern(text, pattern="data")
    print(f"Pattern matches: {matches}")

    # Graph algorithms
    graph = QuantumGraphAlgorithms(num_qubits=6)
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (0, 2)]
    coloring = graph.graph_coloring(edges, num_colors=3)
    print(f"Graph coloring: {coloring}")

    # Quantum compression
    compressor = QuantumCompressor(num_qubits=8)
    data = [1.0, 2.0, 3.0, 2.0, 1.0, 3.0, 2.0, 1.0]
    compressed = compressor.compress(data, target_ratio=0.5)
    print(f"Compression ratio: {compressed.ratio:.2f}")


def main():
    search_and_optimization()
    linear_algebra()
    machine_learning()
    specialized_ops()


if __name__ == "__main__":
    main()
