"""Backend registry, capability negotiation, and abstract hardware base."""

import cirq
import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Type

from qndb.core.engine.backends import BackendBase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Topology descriptors
# ---------------------------------------------------------------------------

class TopologyType(enum.Enum):
    """Common QPU connectivity topologies."""
    LINEAR = "linear"
    RING = "ring"
    GRID = "grid"
    HEAVY_HEX = "heavy_hex"
    ALL_TO_ALL = "all_to_all"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Backend capabilities
# ---------------------------------------------------------------------------

@dataclass
class BackendCapabilities:
    """Declarative capability profile of a quantum backend.

    Every hardware backend publishes a *BackendCapabilities* instance so
    that the compiler and scheduler can make hardware-aware decisions
    without coupling to vendor-specific APIs.
    """

    # Identity
    provider: str = "simulator"
    device_name: str = "default"

    # Qubit budget
    num_qubits: int = 32
    max_circuit_depth: int = 1000

    # Connectivity
    topology: TopologyType = TopologyType.ALL_TO_ALL
    coupling_map: Optional[List[tuple]] = None  # list of (q_i, q_j) pairs

    # Gate set
    native_gates: Set[str] = field(default_factory=lambda: {
        "H", "X", "Y", "Z", "CNOT", "CZ", "Rx", "Ry", "Rz",
    })

    # Performance characteristics
    single_qubit_gate_time_ns: float = 25.0
    two_qubit_gate_time_ns: float = 200.0
    readout_time_ns: float = 500.0
    t1_us: float = 100.0
    t2_us: float = 80.0

    # Error rates
    single_qubit_error: float = 1e-3
    two_qubit_error: float = 1e-2
    readout_error: float = 1e-2

    # Feature support
    supports_mid_circuit_measurement: bool = False
    supports_classical_feedforward: bool = False
    supports_dynamic_circuits: bool = False
    supports_pulse_level: bool = False
    supports_parametric: bool = True

    # Runtime
    max_shots: int = 100_000
    max_experiments: int = 300
    is_simulator: bool = True

    def meets_requirements(
        self,
        min_qubits: int = 1,
        max_depth: int = 1,
        required_gates: Optional[Set[str]] = None,
    ) -> bool:
        """Check whether this backend satisfies the given requirements."""
        if self.num_qubits < min_qubits:
            return False
        if self.max_circuit_depth < max_depth:
            return False
        if required_gates and not required_gates.issubset(self.native_gates):
            return False
        return True

    def estimated_fidelity(self, num_single: int, num_two: int, num_readout: int) -> float:
        """Rough fidelity estimate for a circuit of known gate counts."""
        f = (
            (1 - self.single_qubit_error) ** num_single
            * (1 - self.two_qubit_error) ** num_two
            * (1 - self.readout_error) ** num_readout
        )
        return max(0.0, min(1.0, f))


# ---------------------------------------------------------------------------
# Abstract hardware backend
# ---------------------------------------------------------------------------

class HardwareBackendBase(BackendBase):
    """Extended backend interface for real quantum hardware.

    Sub-classes implement vendor-specific logic.  When the hardware is
    unavailable (SDK missing, feature flag off, credentials missing)
    the backend transparently falls back to the local simulator.
    """

    _SDK_AVAILABLE: bool = False  # overridden by subclass at import time

    def __init__(self) -> None:
        self._capabilities = BackendCapabilities()
        self._fallback = cirq.Simulator()
        self._connected = False
        self._last_calibration: Optional[float] = None

    # -- Identity -----------------------------------------------------------

    @property
    def name(self) -> str:
        return f"hardware-{self._capabilities.provider}"

    @property
    def capabilities(self) -> BackendCapabilities:
        return self._capabilities

    @property
    def is_available(self) -> bool:
        """True if the vendor SDK is importable *and* the feature flag is on."""
        return self._SDK_AVAILABLE and self._connected

    # -- Connection lifecycle -----------------------------------------------

    def connect(self, **credentials: Any) -> bool:
        """Authenticate with the hardware provider.

        Returns ``True`` on success, ``False`` if the backend is not
        available (falls back to simulator silently).
        """
        if not self._SDK_AVAILABLE:
            logger.info(
                "%s: SDK not installed — using simulator fallback", self.name
            )
            self._connected = False
            return False
        try:
            self._connected = self._do_connect(**credentials)
        except Exception as exc:
            logger.warning("%s: connection failed (%s) — simulator fallback", self.name, exc)
            self._connected = False
        return self._connected

    def disconnect(self) -> None:
        self._do_disconnect()
        self._connected = False

    # -- Execution (delegates to vendor or falls back) ----------------------

    def run(self, circuit: cirq.Circuit, repetitions: int = 1000) -> cirq.Result:
        if self.is_available:
            return self._hardware_run(circuit, repetitions)
        return self._fallback.run(circuit, repetitions=repetitions)

    def simulate(self, circuit: cirq.Circuit):
        if self.is_available:
            return self._hardware_simulate(circuit)
        return self._fallback.simulate(circuit)

    def get_calibration(self) -> Dict[str, Any]:
        """Fetch latest calibration data from the device."""
        if not self.is_available:
            return self._default_calibration()
        return self._fetch_calibration()

    # -- Subclass hooks (template-method pattern) ---------------------------

    def _do_connect(self, **credentials: Any) -> bool:
        """Vendor-specific connect.  Return True on success."""
        return False

    def _do_disconnect(self) -> None:
        pass

    def _hardware_run(self, circuit: cirq.Circuit, repetitions: int) -> cirq.Result:
        raise NotImplementedError

    def _hardware_simulate(self, circuit: cirq.Circuit):
        raise NotImplementedError

    def _fetch_calibration(self) -> Dict[str, Any]:
        return self._default_calibration()

    def _default_calibration(self) -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "t1_us": self._capabilities.t1_us,
            "t2_us": self._capabilities.t2_us,
            "single_qubit_error": self._capabilities.single_qubit_error,
            "two_qubit_error": self._capabilities.two_qubit_error,
            "readout_error": self._capabilities.readout_error,
        }


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------

class BackendRegistry:
    """Central registry for quantum backends.

    Keeps track of all available (registered) backends and provides
    helpers for selecting the best backend for a given workload.
    """

    def __init__(self) -> None:
        self._backends: Dict[str, HardwareBackendBase] = {}

    # -- Registration -------------------------------------------------------

    def register(self, key: str, backend: HardwareBackendBase) -> None:
        self._backends[key] = backend
        logger.info("Registered backend: %s (%s)", key, backend.name)

    def unregister(self, key: str) -> None:
        self._backends.pop(key, None)

    # -- Discovery ----------------------------------------------------------

    def get(self, key: str) -> Optional[HardwareBackendBase]:
        return self._backends.get(key)

    def list_backends(self) -> List[str]:
        return list(self._backends.keys())

    def list_available(self) -> List[str]:
        """Return keys of backends whose SDK is installed + connected."""
        return [k for k, b in self._backends.items() if b.is_available]

    # -- Capability-based selection -----------------------------------------

    def select_backend(
        self,
        min_qubits: int = 1,
        max_depth: int = 1,
        required_gates: Optional[Set[str]] = None,
        prefer_hardware: bool = True,
    ) -> Optional[HardwareBackendBase]:
        """Select the best backend matching the given requirements.

        Prefer real hardware if *prefer_hardware* is True and any
        hardware backend satisfies the constraints.
        """
        candidates: List[HardwareBackendBase] = []
        for b in self._backends.values():
            if b.capabilities.meets_requirements(min_qubits, max_depth, required_gates):
                candidates.append(b)

        if not candidates:
            return None

        if prefer_hardware:
            hw = [c for c in candidates if not c.capabilities.is_simulator and c.is_available]
            if hw:
                # pick the one with lowest two-qubit error
                return min(hw, key=lambda b: b.capabilities.two_qubit_error)

        # fall back to any matching backend (prefer lower error)
        return min(candidates, key=lambda b: b.capabilities.two_qubit_error)

    def auto_register_defaults(self) -> None:
        """Register all built-in backends (called once at import time)."""
        from qndb.core.engine.hardware.ibm_backend import IBMBackend
        from qndb.core.engine.hardware.google_backend import GoogleBackend
        from qndb.core.engine.hardware.ionq_backend import IonQBackend
        from qndb.core.engine.hardware.braket_backend import BraketBackend

        self.register("ibm", IBMBackend())
        self.register("google", GoogleBackend())
        self.register("ionq", IonQBackend())
        self.register("braket", BraketBackend())
        # Always keep a plain simulator
        from qndb.core.engine.backends import SimulatorBackend
        # Wrap SimulatorBackend as a HardwareBackendBase-compatible entry
        sim = _SimulatorWrapper()
        self.register("simulator", sim)
        logger.info("Auto-registered %d backends", len(self._backends))


class _SimulatorWrapper(HardwareBackendBase):
    """Thin wrapper so the local simulator participates in the registry."""

    _SDK_AVAILABLE = True

    def __init__(self) -> None:
        super().__init__()
        self._capabilities = BackendCapabilities(
            provider="cirq",
            device_name="local-simulator",
            num_qubits=30,
            max_circuit_depth=10_000,
            topology=TopologyType.ALL_TO_ALL,
            is_simulator=True,
        )
        self._connected = True

    @property
    def name(self) -> str:
        return "simulator"

    def _hardware_run(self, circuit: cirq.Circuit, repetitions: int) -> cirq.Result:
        return self._fallback.run(circuit, repetitions=repetitions)

    def _hardware_simulate(self, circuit: cirq.Circuit):
        return self._fallback.simulate(circuit)
