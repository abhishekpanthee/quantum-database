"""
Machine Learning Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Quantum-enhanced machine-learning primitives:

* **QuantumKernelEstimator** — Kernel matrix from quantum feature maps
* **VariationalClassifier** — Parameterised circuit classifier
* **QuantumBoltzmannMachine** — Generative model via thermal-state sampling
* **QuantumFeatureMap** — ZZ / ZZZ feature maps for high-dimensional data
* **ClassicalMLBridge** — Integration with scikit-learn / NumPy pipelines
"""

import cirq
import math
import logging
import numpy as np
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ======================================================================
# Quantum Feature Map
# ======================================================================

class QuantumFeatureMap:
    """Encode classical data into quantum states via feature maps.

    Supports first-order (Z) and second-order (ZZ) Pauli feature maps
    with configurable depth.

    Args:
        num_qubits: Number of data qubits.
        depth: Number of feature-map repetitions.
        entanglement: ``"linear"`` or ``"full"`` connectivity for
            ZZ interactions.
    """

    def __init__(
        self,
        num_qubits: int,
        depth: int = 2,
        entanglement: str = "linear",
    ) -> None:
        self.num_qubits = num_qubits
        self.depth = depth
        self.entanglement = entanglement

    def build_circuit(self, data: np.ndarray) -> cirq.Circuit:
        """Build the feature-map circuit for a single data point.

        Args:
            data: 1-D array of length ``num_qubits``.

        Returns:
            ``cirq.Circuit``.
        """
        data = np.asarray(data, dtype=float)
        if len(data) != self.num_qubits:
            raise ValueError(f"Expected {self.num_qubits} features, got {len(data)}")

        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = cirq.Circuit()

        for _rep in range(self.depth):
            # Hadamard layer
            circuit.append(cirq.H.on_each(*qubits))
            # Z-rotation encoding
            for i, q in enumerate(qubits):
                circuit.append(cirq.rz(2 * data[i]).on(q))
            # ZZ entangling layer
            pairs = self._entanglement_pairs()
            for i, j in pairs:
                angle = (math.pi - data[i]) * (math.pi - data[j])
                circuit.append(cirq.CNOT(qubits[i], qubits[j]))
                circuit.append(cirq.rz(2 * angle).on(qubits[j]))
                circuit.append(cirq.CNOT(qubits[i], qubits[j]))

        return circuit

    def _entanglement_pairs(self) -> List[Tuple[int, int]]:
        if self.entanglement == "full":
            return [(i, j) for i in range(self.num_qubits)
                    for j in range(i + 1, self.num_qubits)]
        # linear
        return [(i, i + 1) for i in range(self.num_qubits - 1)]


# ======================================================================
# Quantum Kernel Estimator
# ======================================================================

class QuantumKernelEstimator:
    """Compute kernel matrix K(x_i, x_j) = |⟨φ(x_i)|φ(x_j)⟩|².

    Uses a :class:`QuantumFeatureMap` to encode data and estimates the
    overlap via the SWAP test or compute-uncompute method.

    Args:
        num_qubits: Feature dimensionality.
        feature_map: Optional custom :class:`QuantumFeatureMap`.
            Uses a default ZZ map when *None*.
    """

    def __init__(
        self,
        num_qubits: int,
        feature_map: Optional[QuantumFeatureMap] = None,
    ) -> None:
        self.num_qubits = num_qubits
        self.feature_map = feature_map or QuantumFeatureMap(num_qubits)

    def kernel_entry(
        self, x: np.ndarray, y: np.ndarray, repetitions: int = 1000,
    ) -> float:
        """Estimate a single kernel entry K(x, y).

        Uses the *compute-uncompute* method:
        ``|⟨0|U(y)† U(x)|0⟩|²``.

        Returns:
            Estimated kernel value in [0, 1].
        """
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]

        circuit = self.feature_map.build_circuit(x)
        circuit += cirq.inverse(self.feature_map.build_circuit(y))
        circuit.append(cirq.measure(*qubits, key="result"))

        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)
        bits = result.measurements["result"]
        all_zero = np.sum(np.all(bits == 0, axis=1))
        return float(all_zero / repetitions)

    def kernel_matrix(
        self,
        dataset: np.ndarray,
        repetitions: int = 1000,
    ) -> np.ndarray:
        """Compute the full kernel Gram matrix.

        Args:
            dataset: Shape ``(n_samples, num_qubits)``.
            repetitions: Shots per entry.

        Returns:
            ``(n_samples, n_samples)`` NumPy array.
        """
        n = len(dataset)
        K = np.zeros((n, n))
        for i in range(n):
            K[i, i] = 1.0
            for j in range(i + 1, n):
                val = self.kernel_entry(dataset[i], dataset[j], repetitions)
                K[i, j] = val
                K[j, i] = val
        logger.info("Kernel matrix (%d×%d) computed", n, n)
        return K


# ======================================================================
# Variational Classifier
# ======================================================================

class VariationalClassifier:
    """Parameterised quantum circuit for binary classification.

    Architecture: feature-map → variational ansatz → Z-measurement
    on the first qubit.  The label is determined by the sign of ⟨Z⟩.

    Args:
        num_qubits: Number of feature/data qubits.
        ansatz_depth: Number of variational layers.
    """

    def __init__(self, num_qubits: int, ansatz_depth: int = 2) -> None:
        self.num_qubits = num_qubits
        self.ansatz_depth = ansatz_depth
        self.feature_map = QuantumFeatureMap(num_qubits, depth=1)
        self.optimal_params: Optional[np.ndarray] = None
        self._n_params = num_qubits * ansatz_depth

    def build_circuit(
        self, data: np.ndarray, params: np.ndarray,
    ) -> cirq.Circuit:
        """Build classifier circuit for one sample.

        Args:
            data: Feature vector (length ``num_qubits``).
            params: Flat variational parameters.

        Returns:
            Measured ``cirq.Circuit``.
        """
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = self.feature_map.build_circuit(data)

        idx = 0
        for _ in range(self.ansatz_depth):
            for q in qubits:
                circuit.append(cirq.ry(params[idx]).on(q))
                idx += 1
            for i in range(self.num_qubits - 1):
                circuit.append(cirq.CNOT(qubits[i], qubits[i + 1]))

        circuit.append(cirq.measure(qubits[0], key="label"))
        return circuit

    def predict(
        self,
        data: np.ndarray,
        params: Optional[np.ndarray] = None,
        repetitions: int = 1000,
    ) -> int:
        """Predict a binary label (0 or 1) for one sample."""
        params = params if params is not None else self.optimal_params
        if params is None:
            raise RuntimeError("No parameters set — train the classifier first")

        circuit = self.build_circuit(data, params)
        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)
        counts = result.measurements["label"]
        return int(np.mean(counts) >= 0.5)

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        repetitions: int = 200,
        max_iterations: int = 100,
    ) -> Dict[str, Any]:
        """Train the classifier on labelled data.

        Uses COBYLA to minimise the mean squared error.

        Returns:
            Dict with ``optimal_params`` and ``final_loss``.
        """
        from scipy.optimize import minimize as sp_minimize

        def _loss(params: np.ndarray) -> float:
            total = 0.0
            for xi, yi in zip(X, y):
                pred = self.predict(xi, params, repetitions)
                total += (pred - yi) ** 2
            return total / len(X)

        x0 = np.random.uniform(0, 2 * math.pi, self._n_params)
        opt = sp_minimize(_loss, x0, method="COBYLA",
                          options={"maxiter": max_iterations})
        self.optimal_params = opt.x
        logger.info("Classifier trained: loss=%.4f", opt.fun)
        return {"optimal_params": opt.x.tolist(), "final_loss": float(opt.fun)}


# ======================================================================
# Quantum Boltzmann Machine
# ======================================================================

class QuantumBoltzmannMachine:
    """Generative model based on thermal-state sampling.

    Implements a transverse-field Ising model whose thermal state
    is sampled via Trotterised imaginary-time evolution (approximated
    by real-time evolution with dissipation heuristic).

    Args:
        num_visible: Visible units.
        num_hidden: Hidden units.
    """

    def __init__(self, num_visible: int, num_hidden: int = 0) -> None:
        self.num_visible = num_visible
        self.num_hidden = num_hidden
        self.num_qubits = num_visible + num_hidden
        self._weights: Optional[np.ndarray] = None
        self._biases: Optional[np.ndarray] = None

    def initialize_params(self, seed: Optional[int] = None) -> None:
        """Randomly initialise weights and biases."""
        rng = np.random.default_rng(seed)
        self._weights = rng.normal(0, 0.1, (self.num_qubits, self.num_qubits))
        self._weights = (self._weights + self._weights.T) / 2  # symmetric
        np.fill_diagonal(self._weights, 0.0)
        self._biases = rng.normal(0, 0.1, self.num_qubits)

    def build_circuit(self, beta: float = 1.0, trotter_steps: int = 10) -> cirq.Circuit:
        """Build the thermal-state preparation circuit.

        Args:
            beta: Inverse temperature.
            trotter_steps: Trotter-decomposition steps.

        Returns:
            Measured ``cirq.Circuit``.
        """
        if self._weights is None:
            self.initialize_params()

        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*qubits))

        dt = beta / trotter_steps
        for _step in range(trotter_steps):
            # ZZ couplings
            for i in range(self.num_qubits):
                for j in range(i + 1, self.num_qubits):
                    w = float(self._weights[i, j])
                    if abs(w) > 1e-12:
                        circuit.append(cirq.ZZPowGate(exponent=w * dt / math.pi).on(
                            qubits[i], qubits[j],
                        ))
            # Local fields + transverse-field mixer
            for i in range(self.num_qubits):
                circuit.append(cirq.rz(2 * float(self._biases[i]) * dt).on(qubits[i]))
                circuit.append(cirq.rx(2 * dt).on(qubits[i]))

        circuit.append(cirq.measure(*qubits[:self.num_visible], key="visible"))
        return circuit

    def sample(
        self, n_samples: int = 100, beta: float = 1.0,
    ) -> np.ndarray:
        """Draw samples from the model.

        Returns:
            ``(n_samples, num_visible)`` binary array.
        """
        circuit = self.build_circuit(beta)
        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=n_samples)
        return result.measurements["visible"]


# ======================================================================
# Classical ML Bridge
# ======================================================================

class ClassicalMLBridge:
    """Bridge between quantum kernel/classifier and classical ML pipelines.

    Provides scikit-learn–compatible wrappers so that quantum kernels
    can be used with ``sklearn.svm.SVC`` (precomputed kernel) and quantum
    classifiers can be integrated via a uniform ``fit/predict`` API.

    Args:
        num_qubits: Feature dimensionality.
    """

    def __init__(self, num_qubits: int) -> None:
        self.num_qubits = num_qubits
        self.kernel_estimator = QuantumKernelEstimator(num_qubits)
        self.classifier = VariationalClassifier(num_qubits)

    def compute_kernel_matrix(
        self,
        X_train: np.ndarray,
        X_test: Optional[np.ndarray] = None,
        repetitions: int = 500,
    ) -> np.ndarray:
        """Compute a kernel matrix suitable for ``sklearn.svm.SVC(kernel='precomputed')``.

        Args:
            X_train: Training dataset ``(n, num_qubits)``.
            X_test: Optional test dataset.  If provided returns
                the ``(n_test, n_train)`` cross-kernel.

        Returns:
            NumPy kernel matrix.
        """
        if X_test is None:
            return self.kernel_estimator.kernel_matrix(X_train, repetitions)

        n_test = len(X_test)
        n_train = len(X_train)
        K = np.zeros((n_test, n_train))
        for i in range(n_test):
            for j in range(n_train):
                K[i, j] = self.kernel_estimator.kernel_entry(
                    X_test[i], X_train[j], repetitions,
                )
        return K

    def train_classifier(
        self,
        X: np.ndarray,
        y: np.ndarray,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Train the variational classifier.

        Returns:
            Training result dict from :meth:`VariationalClassifier.train`.
        """
        return self.classifier.train(X, y, **kwargs)

    def predict(self, X: np.ndarray, repetitions: int = 500) -> np.ndarray:
        """Predict labels for a batch of data points.

        Returns:
            1-D array of predicted labels.
        """
        return np.array([self.classifier.predict(x, repetitions=repetitions) for x in X])
