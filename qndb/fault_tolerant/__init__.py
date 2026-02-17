"""
Fault-Tolerant Quantum Database  (Phase 9)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Provides fault-tolerant operations, scalable architecture,
quantum networking, and production-grade performance primitives.

Submodules
----------
* :mod:`~qndb.fault_tolerant.operations`   — 9.1 surface codes, logical qubits, magic states, lattice surgery, error budgets
* :mod:`~qndb.fault_tolerant.scalable`     — 9.2 large-scale qubit management, multi-zone QPU, quantum memory, modular QPU, PB-scale indexing
* :mod:`~qndb.fault_tolerant.networking`   — 9.3 quantum internet, entanglement distribution, repeaters, Bell-pair locking, QKD links
* :mod:`~qndb.fault_tolerant.performance`  — 9.4 batch query engine, circuit cache, horizontal scaler, quantum advantage benchmarks
"""

from qndb.fault_tolerant.operations import (  # noqa: F401
    SurfaceCodeStorageLayer,
    LogicalQubit,
    MagicStateDistillery,
    LatticeSurgeryEngine,
    ErrorBudgetTracker,
)
from qndb.fault_tolerant.scalable import (  # noqa: F401
    LogicalQubitManager,
    MultiZoneProcessor,
    QuantumMemoryBank,
    ModularQPUConnector,
    PetabyteQuantumIndex,
)
from qndb.fault_tolerant.networking import (  # noqa: F401
    QuantumInternetGateway,
    EntanglementDistributor,
    QuantumRepeaterChain,
    BellPairLocker,
    QuantumSecureLink,
)
from qndb.fault_tolerant.performance import (  # noqa: F401
    BatchQueryEngine,
    CircuitCacheLayer,
    HorizontalScaler,
    QuantumAdvantageBenchmark,
)

__all__ = [
    # 9.1
    "SurfaceCodeStorageLayer",
    "LogicalQubit",
    "MagicStateDistillery",
    "LatticeSurgeryEngine",
    "ErrorBudgetTracker",
    # 9.2
    "LogicalQubitManager",
    "MultiZoneProcessor",
    "QuantumMemoryBank",
    "ModularQPUConnector",
    "PetabyteQuantumIndex",
    # 9.3
    "QuantumInternetGateway",
    "EntanglementDistributor",
    "QuantumRepeaterChain",
    "BellPairLocker",
    "QuantumSecureLink",
    # 9.4
    "BatchQueryEngine",
    "CircuitCacheLayer",
    "HorizontalScaler",
    "QuantumAdvantageBenchmark",
]
