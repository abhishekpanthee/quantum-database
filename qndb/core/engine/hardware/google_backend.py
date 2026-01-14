"""Google Quantum AI backend — native Cirq integration.

Google's quantum hardware is accessed directly through Cirq's
``cirq_google`` module.  When the module is absent or
``QNDB_GOOGLE_ENABLED`` is ``"0"``, calls fall back to the local
simulator.
"""

import cirq
import logging
import os
import time
from typing import Any, Dict

from qndb.core.engine.hardware.backend_registry import (
    BackendCapabilities,
    HardwareBackendBase,
    TopologyType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK availability probe
# ---------------------------------------------------------------------------

_CIRQ_GOOGLE_AVAILABLE = False
try:
    import cirq_google  # type: ignore[import-untyped]
    _CIRQ_GOOGLE_AVAILABLE = True
except ImportError:
    cirq_google = None  # type: ignore[assignment]

_GOOGLE_FLAG = os.environ.get("QNDB_GOOGLE_ENABLED", "0") == "1"


class GoogleBackend(HardwareBackendBase):
    """Google Quantum AI backend via ``cirq_google``.

    Falls back to the local simulator when the SDK is missing or the
    feature flag is off.
    """

    _SDK_AVAILABLE: bool = _CIRQ_GOOGLE_AVAILABLE and _GOOGLE_FLAG

    def __init__(
        self,
        processor_id: str = "rainbow",
        project_id: str = "",
    ) -> None:
        super().__init__()
        self._processor_id = processor_id
        self._project_id = project_id
        self._engine = None  # cirq_google.Engine
        self._processor = None

        self._capabilities = BackendCapabilities(
            provider="google",
            device_name=processor_id,
            num_qubits=72,
            max_circuit_depth=800,
            topology=TopologyType.GRID,
            coupling_map=None,
            native_gates={"SYC", "PhasedXZ", "Rz", "CZ", "ISWAP"},
            single_qubit_gate_time_ns=25.0,
            two_qubit_gate_time_ns=32.0,
            readout_time_ns=500.0,
            t1_us=20.0,
            t2_us=15.0,
            single_qubit_error=5e-4,
            two_qubit_error=5e-3,
            readout_error=3e-3,
            supports_mid_circuit_measurement=False,
            supports_classical_feedforward=False,
            supports_dynamic_circuits=False,
            supports_pulse_level=False,
            supports_parametric=True,
            max_shots=1_000_000,
            max_experiments=100,
            is_simulator=False,
        )

    # -- Connection ---------------------------------------------------------

    def _do_connect(self, **credentials: Any) -> bool:
        if not _CIRQ_GOOGLE_AVAILABLE:
            return False
        try:
            project = credentials.get("project_id") or self._project_id or os.environ.get("QNDB_GOOGLE_PROJECT_ID", "")
            if not project:
                logger.warning("GoogleBackend: no project_id provided")
                return False
            self._engine = cirq_google.Engine(project_id=project)
            self._processor = self._engine.get_processor(self._processor_id)
            device = self._processor.get_device()
            qubits = sorted(device.qubit_set())
            self._capabilities.num_qubits = len(qubits)
            logger.info(
                "GoogleBackend: connected to %s (%d qubits)",
                self._processor_id, len(qubits),
            )
            return True
        except Exception as exc:
            logger.warning("GoogleBackend: connection failed — %s", exc)
            return False

    def _do_disconnect(self) -> None:
        self._engine = None
        self._processor = None

    # -- Execution ----------------------------------------------------------

    def _hardware_run(self, circuit: cirq.Circuit, repetitions: int) -> cirq.Result:
        if self._engine is None or self._processor is None:
            return self._fallback.run(circuit, repetitions=repetitions)
        try:
            result = self._engine.run(
                program=circuit,
                processor_ids=[self._processor_id],
                repetitions=repetitions,
            )
            return result
        except Exception as exc:
            logger.error("GoogleBackend: hardware run failed (%s) — falling back", exc)
            return self._fallback.run(circuit, repetitions=repetitions)

    def _hardware_simulate(self, circuit: cirq.Circuit):
        return self._fallback.simulate(circuit)

    # -- Calibration --------------------------------------------------------

    def _fetch_calibration(self) -> Dict[str, Any]:
        if self._processor is None:
            return self._default_calibration()
        try:
            cal = self._processor.get_current_calibration()
            return {
                "timestamp": time.time(),
                "processor": self._processor_id,
                "raw_calibration": str(cal)[:500],
            }
        except Exception:
            return self._default_calibration()
