"""
qndb.core.engine.hardware — Quantum Hardware Integration Subpackage
=====================================================================

Feature-flagged hardware backends for real quantum processors.
All backends fall back to the local Cirq simulator when the corresponding
SDK is not installed or the feature flag is disabled.

Feature Flags (environment variables)
--------------------------------------
- ``QNDB_HARDWARE_ENABLED``  — Master switch (default: ``0`` = off)
- ``QNDB_IBM_ENABLED``       — IBM Quantum / Qiskit Runtime
- ``QNDB_GOOGLE_ENABLED``    — Google Quantum AI
- ``QNDB_IONQ_ENABLED``      — IonQ
- ``QNDB_BRAKET_ENABLED``    — Amazon Braket

Set any flag to ``"1"`` to activate the corresponding backend.
When a flag is off or the SDK is missing, the backend transparently
falls back to the local simulator.
"""

import os

# ---------------------------------------------------------------------------
# Feature flags — controlled via environment variables
# ---------------------------------------------------------------------------

HARDWARE_ENABLED: bool = os.environ.get("QNDB_HARDWARE_ENABLED", "0") == "1"
IBM_ENABLED: bool = os.environ.get("QNDB_IBM_ENABLED", "0") == "1"
GOOGLE_ENABLED: bool = os.environ.get("QNDB_GOOGLE_ENABLED", "0") == "1"
IONQ_ENABLED: bool = os.environ.get("QNDB_IONQ_ENABLED", "0") == "1"
BRAKET_ENABLED: bool = os.environ.get("QNDB_BRAKET_ENABLED", "0") == "1"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

from qndb.core.engine.hardware.backend_registry import (  # noqa: E402, F401
    BackendCapabilities,
    BackendRegistry,
    HardwareBackendBase,
)
from qndb.core.engine.hardware.ibm_backend import IBMBackend          # noqa: E402, F401
from qndb.core.engine.hardware.google_backend import GoogleBackend      # noqa: E402, F401
from qndb.core.engine.hardware.ionq_backend import IonQBackend          # noqa: E402, F401
from qndb.core.engine.hardware.braket_backend import BraketBackend      # noqa: E402, F401
from qndb.core.engine.hardware.compilation import (                     # noqa: E402, F401
    HardwareCompiler,
    TopologyMapper,
    GateDecomposer,
    CalibrationData,
)
from qndb.core.engine.hardware.hybrid_executor import (                 # noqa: E402, F401
    HybridExecutor,
    WorkloadPartitioner,
    CircuitKnitter,
    ErrorBudgetManager,
)
from qndb.core.engine.hardware.error_management import (                # noqa: E402, F401
    CalibrationMonitor,
    ErrorMitigator,
    HardwareNoiseModel,
    FidelityScorer,
    CircuitRetryManager,
)

__all__ = [
    # Feature flags
    "HARDWARE_ENABLED", "IBM_ENABLED", "GOOGLE_ENABLED",
    "IONQ_ENABLED", "BRAKET_ENABLED",
    # Registry
    "BackendCapabilities", "BackendRegistry", "HardwareBackendBase",
    # Backends
    "IBMBackend", "GoogleBackend", "IonQBackend", "BraketBackend",
    # Compilation (6.2)
    "HardwareCompiler", "TopologyMapper", "GateDecomposer", "CalibrationData",
    # Hybrid execution (6.3)
    "HybridExecutor", "WorkloadPartitioner", "CircuitKnitter", "ErrorBudgetManager",
    # Error management (6.4)
    "CalibrationMonitor", "ErrorMitigator", "HardwareNoiseModel",
    "FidelityScorer", "CircuitRetryManager",
]
