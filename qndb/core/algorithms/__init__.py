"""
qndb.core.algorithms — Advanced Quantum Algorithms
====================================================

Quantum algorithms providing genuine speedup for database operations:

* **search_optimization** — QAOA, VQE, adaptive Grover, quantum annealing
* **linear_algebra** — HHL, qPCA, QSVT, block-encoding
* **machine_learning** — quantum kernels, variational classifiers, feature maps
* **specialized_ops** — graph algorithms, pattern matching, ANN, compression
"""

from qndb.core.algorithms.search_optimization import (  # noqa: F401
    QAOASolver,
    VQESolver,
    AdaptiveGrover,
    QuantumAnnealingInterface,
    QuantumWalkSpatialSearch,
)
from qndb.core.algorithms.linear_algebra import (  # noqa: F401
    HHLSolver,
    QuantumPCA,
    QSVTFramework,
    QuantumMatrixInversion,
    BlockEncoder,
)
from qndb.core.algorithms.machine_learning import (  # noqa: F401
    QuantumKernelEstimator,
    VariationalClassifier,
    QuantumBoltzmannMachine,
    QuantumFeatureMap,
    ClassicalMLBridge,
)
from qndb.core.algorithms.specialized_ops import (  # noqa: F401
    QuantumPatternMatcher,
    QuantumGraphAlgorithms,
    QuantumTimeSeriesAnalyzer,
    QuantumANN,
    QuantumCompressor,
)

__all__ = [
    # 7.1 Search & Optimization
    "QAOASolver", "VQESolver", "AdaptiveGrover",
    "QuantumAnnealingInterface", "QuantumWalkSpatialSearch",
    # 7.2 Linear Algebra
    "HHLSolver", "QuantumPCA", "QSVTFramework",
    "QuantumMatrixInversion", "BlockEncoder",
    # 7.3 Machine Learning
    "QuantumKernelEstimator", "VariationalClassifier",
    "QuantumBoltzmannMachine", "QuantumFeatureMap", "ClassicalMLBridge",
    # 7.4 Specialized Database Ops
    "QuantumPatternMatcher", "QuantumGraphAlgorithms",
    "QuantumTimeSeriesAnalyzer", "QuantumANN", "QuantumCompressor",
]
