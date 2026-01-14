"""IonQ backend — trapped-ion quantum hardware.

Requires the ``amazon-braket-sdk`` or direct IonQ REST API access.
When unavailable or ``QNDB_IONQ_ENABLED`` is ``"0"``, all calls fall
back to the local Cirq simulator.
"""

import cirq
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from qndb.core.engine.hardware.backend_registry import (
    BackendCapabilities,
    HardwareBackendBase,
    TopologyType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SDK availability probe
# ---------------------------------------------------------------------------

_IONQ_AVAILABLE = False
try:
    import requests as _requests_mod  # type: ignore[import-untyped]
    _IONQ_AVAILABLE = True
except ImportError:
    _requests_mod = None  # type: ignore[assignment]

_IONQ_FLAG = os.environ.get("QNDB_IONQ_ENABLED", "0") == "1"

_IONQ_API_BASE = "https://api.ionq.co/v0.3"


class IonQBackend(HardwareBackendBase):
    """IonQ trapped-ion quantum backend via REST API.

    Falls back to the local simulator when ``requests`` is missing,
    no API key is configured, or the feature flag is off.
    """

    _SDK_AVAILABLE: bool = _IONQ_AVAILABLE and _IONQ_FLAG

    def __init__(self, device: str = "ionq.qpu.aria-1") -> None:
        super().__init__()
        self._device = device
        self._api_key: Optional[str] = None
        self._session = None  # requests.Session

        self._capabilities = BackendCapabilities(
            provider="ionq",
            device_name=device,
            num_qubits=25,
            max_circuit_depth=500,
            topology=TopologyType.ALL_TO_ALL,
            coupling_map=None,
            native_gates={"GPI", "GPI2", "MS", "Rz", "Rx", "Ry", "CNOT", "H", "X", "Y", "Z"},
            single_qubit_gate_time_ns=135_000.0,  # ~135 µs
            two_qubit_gate_time_ns=600_000.0,      # ~600 µs
            readout_time_ns=300_000.0,
            t1_us=10_000_000.0,       # ~10 s (trapped ions)
            t2_us=1_000_000.0,        # ~1 s
            single_qubit_error=3e-5,
            two_qubit_error=5e-3,
            readout_error=3e-3,
            supports_mid_circuit_measurement=True,
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
        if _requests_mod is None:
            return False
        self._api_key = credentials.get("api_key") or os.environ.get("QNDB_IONQ_API_KEY")
        if not self._api_key:
            logger.warning("IonQBackend: no API key provided")
            return False
        self._session = _requests_mod.Session()
        self._session.headers.update({
            "Authorization": f"apiKey {self._api_key}",
            "Content-Type": "application/json",
        })
        # Verify connectivity
        try:
            resp = self._session.get(f"{_IONQ_API_BASE}/backends", timeout=10)
            resp.raise_for_status()
            logger.info("IonQBackend: connected (device=%s)", self._device)
            return True
        except Exception as exc:
            logger.warning("IonQBackend: connectivity check failed — %s", exc)
            return False

    def _do_disconnect(self) -> None:
        if self._session:
            self._session.close()
        self._session = None
        self._api_key = None

    # -- Execution ----------------------------------------------------------

    def _hardware_run(self, circuit: cirq.Circuit, repetitions: int) -> cirq.Result:
        if self._session is None:
            return self._fallback.run(circuit, repetitions=repetitions)
        try:
            payload = self._cirq_to_ionq_payload(circuit, repetitions)
            resp = self._session.post(
                f"{_IONQ_API_BASE}/jobs",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            job_data = resp.json()
            job_id = job_data.get("id")
            result = self._poll_job(job_id)
            return self._ionq_result_to_cirq(result, circuit, repetitions)
        except Exception as exc:
            logger.error("IonQBackend: run failed (%s) — falling back", exc)
            return self._fallback.run(circuit, repetitions=repetitions)

    def _hardware_simulate(self, circuit: cirq.Circuit):
        return self._fallback.simulate(circuit)

    def _poll_job(self, job_id: str, max_wait: int = 600) -> Dict[str, Any]:
        """Poll until the IonQ job completes or times out."""
        if self._session is None:
            return {}
        deadline = time.time() + max_wait
        while time.time() < deadline:
            resp = self._session.get(f"{_IONQ_API_BASE}/jobs/{job_id}", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")
            if status == "completed":
                return data
            if status in ("failed", "canceled"):
                raise RuntimeError(f"IonQ job {job_id} {status}")
            time.sleep(5)
        raise TimeoutError(f"IonQ job {job_id} did not complete within {max_wait}s")

    # -- Conversion helpers -------------------------------------------------

    @staticmethod
    def _cirq_to_ionq_payload(circuit: cirq.Circuit, shots: int) -> Dict[str, Any]:
        """Convert a Cirq circuit to an IonQ-compatible JSON payload.

        Maps Cirq gate types to IonQ native gate names and builds the
        ``ionq.circuit.v0`` request body.
        """
        _GATE_MAP: Dict[type, str] = {
            cirq.HPowGate: "h",
            cirq.XPowGate: "x",
            cirq.YPowGate: "y",
            cirq.ZPowGate: "z",
            cirq.CNotPowGate: "cnot",
            cirq.CZPowGate: "cz",
            cirq.SwapPowGate: "swap",
            cirq.CCXPowGate: "ccx",
        }

        gates: List[Dict[str, Any]] = []
        qubit_map: Dict[cirq.Qid, int] = {}
        idx = 0
        for q in sorted(circuit.all_qubits()):
            qubit_map[q] = idx
            idx += 1

        for op in circuit.all_operations():
            if cirq.is_measurement(op):
                continue  # IonQ measures all qubits automatically

            gate = op.gate
            targets = [qubit_map[q] for q in op.qubits]
            gate_type = type(gate)
            gate_name = _GATE_MAP.get(gate_type)

            if gate_name and gate_type in (
                cirq.HPowGate, cirq.XPowGate, cirq.YPowGate, cirq.ZPowGate,
            ):
                exp = getattr(gate, "exponent", 1)
                if exp == 1:
                    gates.append({"gate": gate_name, "target": targets[0]})
                else:
                    import math
                    rotation_map = {"x": "rx", "y": "ry", "z": "rz"}
                    rg = rotation_map.get(gate_name, gate_name)
                    gates.append({"gate": rg, "target": targets[0],
                                  "rotation": float(exp) * math.pi})
            elif gate_name and len(targets) == 2:
                gates.append({"gate": gate_name, "control": targets[0],
                              "target": targets[1]})
            elif gate_name and len(targets) == 3:
                gates.append({"gate": gate_name, "controls": targets[:2],
                              "target": targets[2]})
            else:
                # Attempt decomposition
                decomposed = cirq.decompose_once(op, default=None)
                if decomposed:
                    sub = cirq.Circuit(decomposed)
                    sub_payload = IonQBackend._cirq_to_ionq_payload(sub, shots)
                    gates.extend(sub_payload["input"]["circuit"])
                else:
                    logger.warning("Skipping unsupported gate for IonQ: %s", gate)

        return {
            "target": "qpu.aria-1",
            "shots": shots,
            "input": {
                "format": "ionq.circuit.v0",
                "qubits": len(qubit_map),
                "circuit": gates,
            },
        }

    @staticmethod
    def _ionq_result_to_cirq(
        result_data: Dict[str, Any],
        original_circuit: cirq.Circuit,
        repetitions: int,
    ) -> cirq.Result:
        """Convert IonQ result JSON to a ``cirq.Result``.

        IonQ returns a probability distribution keyed by bit-string
        integers.  We sample from this distribution to produce the
        requested number of repetitions.
        """
        import numpy as np

        probabilities = result_data.get("data", {}).get("histogram", {})
        n_qubits = len(list(original_circuit.all_qubits()))

        if not probabilities:
            # No results — return zeros
            meas_keys = [
                cirq.measurement_key_name(op)
                for op in original_circuit.all_operations()
                if cirq.is_measurement(op)
            ]
            key = meas_keys[0] if meas_keys else "result"
            return cirq.ResultDict(params=cirq.ParamResolver(), records={
                key: np.zeros((repetitions, 1, n_qubits), dtype=np.uint8),
            })

        # Build arrays for np.random.choice from histogram
        states = []
        probs = []
        for state_str, prob in probabilities.items():
            states.append(int(state_str))
            probs.append(float(prob))

        probs_arr = np.array(probs, dtype=np.float64)
        probs_arr /= probs_arr.sum()  # normalise

        rng = np.random.default_rng()
        samples_int = rng.choice(states, size=repetitions, p=probs_arr)

        # Convert integers to bit arrays
        bit_arrays = np.array([
            [(s >> (n_qubits - 1 - b)) & 1 for b in range(n_qubits)]
            for s in samples_int
        ], dtype=np.uint8)

        meas_keys = [
            cirq.measurement_key_name(op)
            for op in original_circuit.all_operations()
            if cirq.is_measurement(op)
        ]
        key = meas_keys[0] if meas_keys else "result"

        return cirq.ResultDict(params=cirq.ParamResolver(), records={
            key: bit_arrays.reshape((repetitions, 1, n_qubits)),
        })
