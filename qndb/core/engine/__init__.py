"""
qndb.core.engine — Quantum Engine Subpackage
==============================================

Modular quantum engine: backends, noise, circuit parameterisation,
qubit allocation, checkpointing, and hardware integration.
"""

from qndb.core.engine.backends import BackendBase, SimulatorBackend, CloudBackend  # noqa: F401
from qndb.core.engine.noise import NoiseConfig                                     # noqa: F401
from qndb.core.engine.quantum_engine import QuantumEngine                          # noqa: F401

# Hardware integration (feature-flagged)
from qndb.core.engine.hardware import (                                             # noqa: F401
    HARDWARE_ENABLED, IBM_ENABLED, GOOGLE_ENABLED, IONQ_ENABLED, BRAKET_ENABLED,
    BackendCapabilities, BackendRegistry, HardwareBackendBase,
    IBMBackend, GoogleBackend, IonQBackend, BraketBackend,
    HardwareCompiler, TopologyMapper, GateDecomposer, CalibrationData,
    HybridExecutor, WorkloadPartitioner, CircuitKnitter, ErrorBudgetManager,
    CalibrationMonitor, ErrorMitigator, HardwareNoiseModel,
    FidelityScorer, CircuitRetryManager,
)

__all__ = [
    # Core
    "BackendBase", "SimulatorBackend", "CloudBackend",
    "NoiseConfig", "QuantumEngine",
    # Feature flags
    "HARDWARE_ENABLED", "IBM_ENABLED", "GOOGLE_ENABLED",
    "IONQ_ENABLED", "BRAKET_ENABLED",
    # Registry
    "BackendCapabilities", "BackendRegistry", "HardwareBackendBase",
    # Backends
    "IBMBackend", "GoogleBackend", "IonQBackend", "BraketBackend",
    # Compilation
    "HardwareCompiler", "TopologyMapper", "GateDecomposer", "CalibrationData",
    # Hybrid execution
    "HybridExecutor", "WorkloadPartitioner", "CircuitKnitter", "ErrorBudgetManager",
    # Error management
    "CalibrationMonitor", "ErrorMitigator", "HardwareNoiseModel",
    "FidelityScorer", "CircuitRetryManager",
]
