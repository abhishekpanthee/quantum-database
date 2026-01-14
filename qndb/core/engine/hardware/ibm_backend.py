"""IBM Quantum backend — Qiskit Runtime integration.

Requires ``qiskit`` and ``qiskit-ibm-runtime`` to be installed.
When the SDK is absent or ``QNDB_IBM_ENABLED`` is ``"0"``, all calls
transparently fall back to the local Cirq simulator.
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

_QISKIT_AVAILABLE = False
try:
    import qiskit  # type: ignore[import-untyped]
    _QISKIT_AVAILABLE = True
except ImportError:
    qiskit = None  # type: ignore[assignment]

_IBM_FLAG = os.environ.get("QNDB_IBM_ENABLED", "0") == "1"


class IBMBackend(HardwareBackendBase):
    """IBM Quantum backend via Qiskit Runtime.

    When the Qiskit SDK is not installed or the feature flag
    ``QNDB_IBM_ENABLED`` is off, every method silently uses the local
    Cirq simulator so that the rest of the stack remains functional.
    """

    _SDK_AVAILABLE: bool = _QISKIT_AVAILABLE and _IBM_FLAG

    def __init__(self, instance: str = "ibm_quantum", backend_name: str = "ibm_brisbane") -> None:
        super().__init__()
        self._instance = instance
        self._backend_name = backend_name
        self._service = None  # qiskit_ibm_runtime.QiskitRuntimeService
        self._hw_backend = None  # qiskit backend handle

        self._capabilities = BackendCapabilities(
            provider="ibm",
            device_name=backend_name,
            num_qubits=127,
            max_circuit_depth=300,
            topology=TopologyType.HEAVY_HEX,
            coupling_map=None,
            native_gates={"X", "Rz", "CNOT", "ECR", "SX"},
            single_qubit_gate_time_ns=35.0,
            two_qubit_gate_time_ns=660.0,
            readout_time_ns=1200.0,
            t1_us=250.0,
            t2_us=150.0,
            single_qubit_error=3e-4,
            two_qubit_error=8e-3,
            readout_error=1.2e-2,
            supports_mid_circuit_measurement=True,
            supports_classical_feedforward=True,
            supports_dynamic_circuits=True,
            supports_pulse_level=True,
            supports_parametric=True,
            max_shots=100_000,
            max_experiments=300,
            is_simulator=False,
        )

    # -- Connection ---------------------------------------------------------

    def _do_connect(self, **credentials: Any) -> bool:
        if not _QISKIT_AVAILABLE:
            return False
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService  # type: ignore[import-untyped]
            token = credentials.get("api_key") or os.environ.get("QNDB_IBM_API_KEY")
            if not token:
                logger.warning("IBMBackend: no API key provided")
                return False
            self._service = QiskitRuntimeService(
                channel="ibm_quantum",
                instance=self._instance,
                token=token,
            )
            self._hw_backend = self._service.backend(self._backend_name)
            # Refresh capabilities from live config
            config = self._hw_backend.configuration()
            self._capabilities.num_qubits = config.n_qubits
            self._capabilities.coupling_map = list(config.coupling_map) if config.coupling_map else None
            logger.info("IBMBackend: connected to %s (%d qubits)", self._backend_name, config.n_qubits)
            return True
        except Exception as exc:
            logger.warning("IBMBackend: connection failed — %s", exc)
            return False

    def _do_disconnect(self) -> None:
        self._service = None
        self._hw_backend = None

    # -- Execution ----------------------------------------------------------

    def _hardware_run(self, circuit: cirq.Circuit, repetitions: int) -> cirq.Result:
        """Convert Cirq circuit → Qiskit, run on IBM hardware, convert back."""
        if self._hw_backend is None:
            return self._fallback.run(circuit, repetitions=repetitions)
        try:
            from qiskit_ibm_runtime import SamplerV2  # type: ignore[import-untyped]
            qiskit_circuit = self._cirq_to_qiskit(circuit)
            sampler = SamplerV2(self._hw_backend)
            job = sampler.run([qiskit_circuit], shots=repetitions)
            result = job.result()
            return self._qiskit_result_to_cirq(result, circuit, repetitions)
        except Exception as exc:
            logger.error("IBMBackend: hardware run failed (%s) — falling back", exc)
            return self._fallback.run(circuit, repetitions=repetitions)

    def _hardware_simulate(self, circuit: cirq.Circuit):
        """IBM has no native statevector on device; use local sim."""
        return self._fallback.simulate(circuit)

    # -- Calibration --------------------------------------------------------

    def _fetch_calibration(self) -> Dict[str, Any]:
        if self._hw_backend is None:
            return self._default_calibration()
        try:
            props = self._hw_backend.properties()
            cal: Dict[str, Any] = {
                "timestamp": time.time(),
                "backend": self._backend_name,
                "t1_us": props.t1(0) * 1e6 if props.t1(0) else self._capabilities.t1_us,
                "t2_us": props.t2(0) * 1e6 if props.t2(0) else self._capabilities.t2_us,
            }
            self._last_calibration = cal["timestamp"]
            return cal
        except Exception:
            return self._default_calibration()

    # -- Cirq ↔ Qiskit conversion ------------------------------------------

    @staticmethod
    def _cirq_to_qiskit(circuit: cirq.Circuit) -> Any:
        """Convert a Cirq circuit to a Qiskit ``QuantumCircuit``.

        Maps common Cirq gates to their Qiskit equivalents.  Requires
        ``qiskit`` to be installed (guaranteed when this path is
        reached, since ``_hardware_run`` is only called when the SDK
        is available).
        """
        from qiskit import QuantumCircuit as QC  # type: ignore[import-untyped]

        qubit_map: Dict[cirq.Qid, int] = {}
        idx = 0
        for q in sorted(circuit.all_qubits()):
            qubit_map[q] = idx
            idx += 1

        n_qubits = len(qubit_map)
        # Count measurement keys to determine classical register size
        meas_keys = set()
        for op in circuit.all_operations():
            if cirq.is_measurement(op):
                meas_keys.add(cirq.measurement_key_name(op))
        n_clbits = max(n_qubits, 1)  # at least 1 classical bit
        qc = QC(n_qubits, n_clbits)

        clbit_idx = 0
        for op in circuit.all_operations():
            targets = [qubit_map[q] for q in op.qubits]
            gate = op.gate

            if cirq.is_measurement(op):
                for t in targets:
                    if clbit_idx < n_clbits:
                        qc.measure(t, clbit_idx)
                        clbit_idx += 1
            elif isinstance(gate, cirq.HPowGate) and gate.exponent == 1:
                qc.h(targets[0])
            elif isinstance(gate, cirq.XPowGate) and gate.exponent == 1:
                qc.x(targets[0])
            elif isinstance(gate, cirq.YPowGate) and gate.exponent == 1:
                qc.y(targets[0])
            elif isinstance(gate, cirq.ZPowGate) and gate.exponent == 1:
                qc.z(targets[0])
            elif isinstance(gate, cirq.CNotPowGate) and gate.exponent == 1:
                qc.cx(targets[0], targets[1])
            elif isinstance(gate, cirq.CZPowGate) and gate.exponent == 1:
                qc.cz(targets[0], targets[1])
            elif isinstance(gate, cirq.SwapPowGate) and gate.exponent == 1:
                qc.swap(targets[0], targets[1])
            elif isinstance(gate, (cirq.XPowGate, cirq.YPowGate, cirq.ZPowGate)):
                import math
                angle = float(gate.exponent) * math.pi
                if isinstance(gate, cirq.XPowGate):
                    qc.rx(angle, targets[0])
                elif isinstance(gate, cirq.YPowGate):
                    qc.ry(angle, targets[0])
                else:
                    qc.rz(angle, targets[0])
            else:
                # Decompose unknown gate into known primitives
                decomposed = cirq.decompose_once(op, default=None)
                if decomposed:
                    sub_circuit = cirq.Circuit(decomposed)
                    sub_qc = IBMBackend._cirq_to_qiskit(sub_circuit)
                    qc = qc.compose(sub_qc)
                else:
                    logger.warning("Skipping unsupported gate: %s", gate)

        return qc

    @staticmethod
    def _qiskit_result_to_cirq(
        qiskit_result: Any,
        original_circuit: cirq.Circuit,
        repetitions: int,
    ) -> cirq.Result:
        """Convert a Qiskit ``SamplerV2`` result into a ``cirq.Result``.

        Parses the measurement bit-arrays from the Qiskit result object
        and reconstructs a ``cirq.ResultDict`` keyed by the original
        Cirq measurement keys.
        """
        import numpy as np

        # SamplerV2 returns a PubResult per circuit; we submitted one
        pub_result = qiskit_result[0]
        data = pub_result.data

        meas_keys = [
            cirq.measurement_key_name(op)
            for op in original_circuit.all_operations()
            if cirq.is_measurement(op)
        ]

        records: Dict[str, np.ndarray] = {}
        # data attributes are named by classical register / measurement key
        for key in meas_keys:
            bitarray = getattr(data, key, None)
            if bitarray is None:
                # fall back to default register name
                bitarray = getattr(data, "meas", None) or getattr(data, "c", None)
            if bitarray is not None:
                # bitarray.array is a numpy uint8 packed array; unpack it
                arr = np.array(bitarray.get_int_counts() if hasattr(bitarray, "get_int_counts") else [])
                if hasattr(bitarray, "array"):
                    records[key] = np.unpackbits(
                        bitarray.array, axis=-1, bitorder="big",
                    )[:, :len([op for op in original_circuit.all_operations()
                               if cirq.is_measurement(op) and cirq.measurement_key_name(op) == key][0].qubits)]
                else:
                    records[key] = np.zeros((repetitions, 1), dtype=np.uint8)
            else:
                records[key] = np.zeros((repetitions, 1), dtype=np.uint8)

        return cirq.ResultDict(params=cirq.ParamResolver(), records={
            k: v.reshape((v.shape[0], 1, -1)) if v.ndim == 2 else v
            for k, v in records.items()
        })
