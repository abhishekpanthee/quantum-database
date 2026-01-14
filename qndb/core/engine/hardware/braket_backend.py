"""Amazon Braket backend — multi-hardware cloud access.

Requires ``amazon-braket-sdk`` to be installed.  When the SDK is
absent or ``QNDB_BRAKET_ENABLED`` is ``"0"``, all calls fall back to
the local Cirq simulator.
"""

import cirq
import logging
import os
import time
from typing import Any, Dict, Optional

from qndb.core.engine.hardware.backend_registry import (
    BackendCapabilities,
    HardwareBackendBase,
    TopologyType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK availability probe
# ---------------------------------------------------------------------------

_BRAKET_AVAILABLE = False
try:
    from braket.aws import AwsDevice, AwsQuantumTask  # type: ignore[import-untyped]
    from braket.circuits import Circuit as BraketCircuit  # type: ignore[import-untyped]
    _BRAKET_AVAILABLE = True
except ImportError:
    AwsDevice = None  # type: ignore[assignment,misc]
    AwsQuantumTask = None  # type: ignore[assignment,misc]
    BraketCircuit = None  # type: ignore[assignment,misc]

_BRAKET_FLAG = os.environ.get("QNDB_BRAKET_ENABLED", "0") == "1"


class BraketBackend(HardwareBackendBase):
    """Amazon Braket backend.

    Supports multiple QPU families through Braket's unified API:
    IonQ, Rigetti, OQC, QuEra, etc.  Falls back to the local
    simulator when the SDK is missing or the feature flag is off.
    """

    _SDK_AVAILABLE: bool = _BRAKET_AVAILABLE and _BRAKET_FLAG

    def __init__(
        self,
        device_arn: str = "arn:aws:braket:us-east-1::device/qpu/ionq/Aria-1",
        s3_bucket: str = "",
        s3_prefix: str = "qndb-results",
    ) -> None:
        super().__init__()
        self._device_arn = device_arn
        self._s3_bucket = s3_bucket
        self._s3_prefix = s3_prefix
        self._device = None  # AwsDevice

        self._capabilities = BackendCapabilities(
            provider="braket",
            device_name=device_arn.split("/")[-1] if "/" in device_arn else device_arn,
            num_qubits=25,
            max_circuit_depth=500,
            topology=TopologyType.ALL_TO_ALL,
            coupling_map=None,
            native_gates={"H", "X", "Y", "Z", "CNOT", "CZ", "Rx", "Ry", "Rz", "SWAP"},
            single_qubit_error=3e-4,
            two_qubit_error=6e-3,
            readout_error=5e-3,
            supports_mid_circuit_measurement=False,
            supports_classical_feedforward=False,
            supports_dynamic_circuits=False,
            supports_pulse_level=False,
            supports_parametric=True,
            max_shots=10_000,
            max_experiments=1,
            is_simulator=False,
        )

    # -- Connection ---------------------------------------------------------

    def _do_connect(self, **credentials: Any) -> bool:
        if AwsDevice is None:
            return False
        try:
            self._device = AwsDevice(self._device_arn)
            props = self._device.properties
            if hasattr(props, "paradigm") and hasattr(props.paradigm, "qubitCount"):
                self._capabilities.num_qubits = props.paradigm.qubitCount
            logger.info(
                "BraketBackend: connected to %s (%d qubits)",
                self._device_arn,
                self._capabilities.num_qubits,
            )
            return True
        except Exception as exc:
            logger.warning("BraketBackend: connection failed — %s", exc)
            return False

    def _do_disconnect(self) -> None:
        self._device = None

    # -- Execution ----------------------------------------------------------

    def _hardware_run(self, circuit: cirq.Circuit, repetitions: int) -> cirq.Result:
        if self._device is None:
            return self._fallback.run(circuit, repetitions=repetitions)
        try:
            braket_circuit = self._cirq_to_braket(circuit)
            s3 = (self._s3_bucket, self._s3_prefix) if self._s3_bucket else None
            task = self._device.run(braket_circuit, shots=repetitions, s3_destination_folder=s3)
            braket_result = task.result()
            return self._braket_result_to_cirq(braket_result, circuit, repetitions)
        except Exception as exc:
            logger.error("BraketBackend: run failed (%s) — falling back", exc)
            return self._fallback.run(circuit, repetitions=repetitions)

    def _hardware_simulate(self, circuit: cirq.Circuit):
        return self._fallback.simulate(circuit)

    # -- Calibration --------------------------------------------------------

    def _fetch_calibration(self) -> Dict[str, Any]:
        if self._device is None:
            return self._default_calibration()
        try:
            props = self._device.properties
            cal: Dict[str, Any] = {
                "timestamp": time.time(),
                "device_arn": self._device_arn,
                "provider": getattr(props, "provider", {}).get("name", "unknown")
                    if isinstance(getattr(props, "provider", None), dict) else "unknown",
            }
            self._last_calibration = cal["timestamp"]
            return cal
        except Exception:
            return self._default_calibration()

    # -- Conversion ---------------------------------------------------------

    @staticmethod
    def _cirq_to_braket(circuit: cirq.Circuit) -> Any:
        """Convert a Cirq circuit to an Amazon Braket circuit.

        Maps common Cirq gates to Braket equivalents including
        rotation gates.  Requires the ``amazon-braket-sdk``.
        """
        if BraketCircuit is None:
            raise ImportError("Braket SDK not available")

        import math

        bc = BraketCircuit()
        qubit_map: Dict[cirq.Qid, int] = {}
        idx = 0
        for q in sorted(circuit.all_qubits()):
            qubit_map[q] = idx
            idx += 1

        for op in circuit.all_operations():
            targets = [qubit_map[q] for q in op.qubits]
            gate = op.gate

            if cirq.is_measurement(op):
                # Braket measures via result_types or per-qubit measurement
                for t in targets:
                    bc.measure(t)
            elif isinstance(gate, cirq.HPowGate) and gate.exponent == 1:
                bc.h(targets[0])
            elif isinstance(gate, cirq.XPowGate) and gate.exponent == 1:
                bc.x(targets[0])
            elif isinstance(gate, cirq.YPowGate) and gate.exponent == 1:
                bc.y(targets[0])
            elif isinstance(gate, cirq.ZPowGate) and gate.exponent == 1:
                bc.z(targets[0])
            elif isinstance(gate, cirq.XPowGate):
                bc.rx(targets[0], float(gate.exponent) * math.pi)
            elif isinstance(gate, cirq.YPowGate):
                bc.ry(targets[0], float(gate.exponent) * math.pi)
            elif isinstance(gate, cirq.ZPowGate):
                bc.rz(targets[0], float(gate.exponent) * math.pi)
            elif isinstance(gate, cirq.CNotPowGate) and gate.exponent == 1:
                bc.cnot(targets[0], targets[1])
            elif isinstance(gate, cirq.CZPowGate) and gate.exponent == 1:
                bc.cz(targets[0], targets[1])
            elif isinstance(gate, cirq.SwapPowGate) and gate.exponent == 1:
                bc.swap(targets[0], targets[1])
            elif isinstance(gate, cirq.CCXPowGate) and gate.exponent == 1:
                bc.ccnot(targets[0], targets[1], targets[2])
            else:
                # Try decomposition into supported gates
                decomposed = cirq.decompose_once(op, default=None)
                if decomposed:
                    sub = cirq.Circuit(decomposed)
                    sub_bc = BraketBackend._cirq_to_braket(sub)
                    # Compose the sub-circuit instructions
                    for instr in sub_bc.instructions:
                        bc.add_instruction(instr)
                else:
                    logger.warning("Skipping unsupported gate for Braket: %s", gate)
        return bc

    @staticmethod
    def _braket_result_to_cirq(
        braket_result: Any,
        original_circuit: cirq.Circuit,
        repetitions: int,
    ) -> cirq.Result:
        """Convert an Amazon Braket result to a ``cirq.Result``.

        Reads measured bit-string arrays from the Braket result object
        and packages them into a ``cirq.ResultDict``.
        """
        import numpy as np

        n_qubits = len(list(original_circuit.all_qubits()))
        meas_keys = [
            cirq.measurement_key_name(op)
            for op in original_circuit.all_operations()
            if cirq.is_measurement(op)
        ]
        key = meas_keys[0] if meas_keys else "result"

        # Braket result.measurements is an ndarray of shape (shots, n_qubits)
        measurements = getattr(braket_result, "measurements", None)
        if measurements is not None:
            arr = np.array(measurements, dtype=np.uint8)
            if arr.ndim == 1:
                arr = arr.reshape(-1, n_qubits)
        else:
            arr = np.zeros((repetitions, n_qubits), dtype=np.uint8)

        return cirq.ResultDict(params=cirq.ParamResolver(), records={
            key: arr.reshape((arr.shape[0], 1, n_qubits)),
        })
