"""Hardware error management.

Real-time calibration monitoring, dynamic error mitigation strategy
selection, hardware noise model integration, automatic circuit retry,
and fidelity-aware confidence scoring.
"""

import cirq
import enum
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from qndb.core.engine.hardware.backend_registry import (
    BackendCapabilities,
    HardwareBackendBase,
)
from qndb.core.engine.hardware.compilation import CalibrationData

logger = logging.getLogger(__name__)


# ======================================================================
# Calibration monitor
# ======================================================================

class CalibrationMonitor:
    """Continuously track backend calibration data.

    Keeps a history of calibration snapshots and raises alerts when
    error rates drift beyond configurable thresholds.
    """

    def __init__(
        self,
        backend: HardwareBackendBase,
        refresh_interval_s: float = 300.0,
        error_threshold_factor: float = 2.0,
    ) -> None:
        self._backend = backend
        self._interval = refresh_interval_s
        self._threshold_factor = error_threshold_factor
        self._history: List[CalibrationData] = []
        self._baseline: Optional[CalibrationData] = None
        self._last_refresh: float = 0.0
        self._alerts: List[Dict[str, Any]] = []

    def refresh(self) -> CalibrationData:
        """Fetch fresh calibration data from the backend."""
        raw = self._backend.get_calibration()
        cal = CalibrationData(
            timestamp=raw.get("timestamp", time.time()),
            t1_us=raw.get("t1_us", {}) if isinstance(raw.get("t1_us"), dict) else {},
            t2_us=raw.get("t2_us", {}) if isinstance(raw.get("t2_us"), dict) else {},
            single_qubit_errors=raw.get("single_qubit_errors", {}),
            two_qubit_errors=raw.get("two_qubit_errors", {}),
            readout_errors=raw.get("readout_errors", {}),
        )
        self._history.append(cal)
        if self._baseline is None:
            self._baseline = cal
        self._last_refresh = time.time()
        self._check_drift(cal)
        return cal

    def needs_refresh(self) -> bool:
        return (time.time() - self._last_refresh) > self._interval

    @property
    def latest(self) -> Optional[CalibrationData]:
        return self._history[-1] if self._history else None

    @property
    def alerts(self) -> List[Dict[str, Any]]:
        return list(self._alerts)

    def clear_alerts(self) -> None:
        self._alerts.clear()

    def _check_drift(self, current: CalibrationData) -> None:
        """Compare current calibration against baseline."""
        if self._baseline is None:
            return
        for qubit, err in current.single_qubit_errors.items():
            baseline_err = self._baseline.single_qubit_errors.get(qubit, err)
            if baseline_err > 0 and err > baseline_err * self._threshold_factor:
                self._alerts.append({
                    "type": "single_qubit_drift",
                    "qubit": qubit,
                    "baseline": baseline_err,
                    "current": err,
                    "timestamp": current.timestamp,
                })
        for pair, err in current.two_qubit_errors.items():
            baseline_err = self._baseline.two_qubit_errors.get(pair, err)
            if baseline_err > 0 and err > baseline_err * self._threshold_factor:
                self._alerts.append({
                    "type": "two_qubit_drift",
                    "qubits": pair,
                    "baseline": baseline_err,
                    "current": err,
                    "timestamp": current.timestamp,
                })


# ======================================================================
# Error mitigation strategies
# ======================================================================

class MitigationStrategy(enum.Enum):
    NONE = "none"
    MEASUREMENT_ERROR_MITIGATION = "measurement_error_mitigation"
    ZERO_NOISE_EXTRAPOLATION = "zero_noise_extrapolation"
    PROBABILISTIC_ERROR_CANCELLATION = "probabilistic_error_cancellation"
    TWIRLED_READOUT = "twirled_readout"


class ErrorMitigator:
    """Select and apply error mitigation strategies.

    All strategies are implemented as classical post-processing on top
    of raw measurement results — no extra hardware required.
    """

    def __init__(self, capabilities: BackendCapabilities) -> None:
        self._caps = capabilities

    def select_strategy(
        self,
        circuit: cirq.Circuit,
        desired_fidelity: float = 0.95,
    ) -> MitigationStrategy:
        """Pick the best mitigation strategy for the given circuit + device."""
        ops = list(circuit.all_operations())
        n_two = sum(1 for o in ops if len(o.qubits) == 2)
        n_readout = sum(1 for o in ops if cirq.is_measurement(o))

        # Estimate raw fidelity
        depth = len(circuit)
        raw_fid = self._caps.estimated_fidelity(
            len(ops) - n_two - n_readout, n_two, n_readout
        )

        if raw_fid >= desired_fidelity:
            return MitigationStrategy.NONE

        # High readout error → measurement error mitigation
        if self._caps.readout_error > 5e-3 and n_readout > 0:
            return MitigationStrategy.MEASUREMENT_ERROR_MITIGATION

        # High gate error → zero noise extrapolation
        if self._caps.two_qubit_error > 1e-2:
            return MitigationStrategy.ZERO_NOISE_EXTRAPOLATION

        return MitigationStrategy.TWIRLED_READOUT

    def apply(
        self,
        strategy: MitigationStrategy,
        raw_counts: Dict[str, int],
        calibration: Optional[CalibrationData] = None,
    ) -> Dict[str, float]:
        """Apply the selected mitigation to raw measurement counts.

        Returns a corrected probability distribution.
        """
        total = sum(raw_counts.values())
        if total == 0:
            return {}

        probs = {k: v / total for k, v in raw_counts.items()}

        if strategy == MitigationStrategy.NONE:
            return probs

        if strategy == MitigationStrategy.MEASUREMENT_ERROR_MITIGATION:
            return self._measurement_error_mitigation(probs, calibration)

        if strategy == MitigationStrategy.ZERO_NOISE_EXTRAPOLATION:
            return self._zero_noise_extrapolation(probs)

        if strategy == MitigationStrategy.TWIRLED_READOUT:
            return self._twirled_readout(probs)

        return probs

    # -- Strategy implementations -------------------------------------------

    def _measurement_error_mitigation(
        self,
        probs: Dict[str, float],
        calibration: Optional[CalibrationData],
    ) -> Dict[str, float]:
        """Simple readout-error mitigation via inverse confusion matrix.

        For M-qubit readout, the full matrix is 2^M × 2^M which is
        impractical for large M.  We use a tensor-product approximation
        (per-qubit correction).
        """
        if calibration is None:
            return probs

        readout_err = self._caps.readout_error
        correction = 1.0 / max(1.0 - 2 * readout_err, 0.01)
        shift = readout_err * correction

        corrected: Dict[str, float] = {}
        for bitstring, p in probs.items():
            corrected[bitstring] = max(0.0, p * correction - shift * (1 - p))

        # Renormalise
        total = sum(corrected.values())
        if total > 0:
            corrected = {k: v / total for k, v in corrected.items()}
        return corrected

    @staticmethod
    def _zero_noise_extrapolation(probs: Dict[str, float]) -> Dict[str, float]:
        """Single-scale Richardson-lite noise extrapolation.

        Sharpens the probability distribution by raising each
        probability to a power > 1, which suppresses low-probability
        noise tails relative to the dominant outcomes.  The result is
        then renormalised.  For multi-scale ZNE, circuits must be re-run
        at different noise levels externally.
        """
        corrected: Dict[str, float] = {}
        beta = 1.2  # sharpening factor
        for k, p in probs.items():
            corrected[k] = p ** beta
        total = sum(corrected.values())
        if total > 0:
            corrected = {k: v / total for k, v in corrected.items()}
        return corrected

    @staticmethod
    def _twirled_readout(probs: Dict[str, float]) -> Dict[str, float]:
        """Twirled readout error mitigation.

        Symmetrises the probability distribution by averaging each
        bit-string outcome with its bit-flipped complement.  This
        converts asymmetric readout bias into symmetric noise,
        which is easier to correct downstream.
        """
        n_bits = max((len(k) for k in probs), default=0)
        if n_bits == 0:
            return dict(probs)

        # Build complement map
        def _flip(bs: str) -> str:
            return "".join("1" if c == "0" else "0" for c in bs)

        symmetrised: Dict[str, float] = {}
        seen: set = set()
        for bs, p in probs.items():
            if bs in seen:
                continue
            comp = _flip(bs)
            p_comp = probs.get(comp, 0.0)
            avg = (p + p_comp) / 2.0
            symmetrised[bs] = avg
            if comp != bs:
                symmetrised[comp] = avg
                seen.add(comp)
            seen.add(bs)

        # Renormalise
        total = sum(symmetrised.values())
        if total > 0:
            symmetrised = {k: v / total for k, v in symmetrised.items()}
        return symmetrised


# ======================================================================
# Hardware noise model
# ======================================================================

class HardwareNoiseModel:
    """Build Cirq noise models from live calibration data.

    Produces a ``cirq.NoiseModel`` customised to the current device
    state, enabling accurate local simulation of real hardware noise.
    """

    def __init__(self, capabilities: BackendCapabilities) -> None:
        self._caps = capabilities

    def build_noise_model(
        self,
        calibration: Optional[CalibrationData] = None,
    ) -> cirq.NoiseModel:
        """Build a Cirq noise model from calibration data."""
        depol_rate = self._caps.two_qubit_error
        if calibration and calibration.two_qubit_errors:
            depol_rate = float(np.mean(list(calibration.two_qubit_errors.values())))

        if depol_rate > 0:
            return cirq.ConstantQubitNoiseModel(
                qubit_noise_gate=cirq.depolarize(p=min(depol_rate, 0.5))
            )
        return cirq.UNCONSTRAINED_DEVICE

    def simulate_with_noise(
        self,
        circuit: cirq.Circuit,
        repetitions: int = 1000,
        calibration: Optional[CalibrationData] = None,
    ) -> cirq.Result:
        """Run a circuit through the noise model on a density matrix simulator."""
        noise_model = self.build_noise_model(calibration)
        if isinstance(noise_model, cirq.NoiseModel):
            noisy_circuit = cirq.Circuit(
                [noise_model.noisy_operation(op) for op in circuit.all_operations()]
            )
        else:
            noisy_circuit = circuit
        sim = cirq.DensityMatrixSimulator()
        return sim.run(noisy_circuit, repetitions=repetitions)


# ======================================================================
# Fidelity scorer
# ======================================================================

@dataclass
class FidelityReport:
    """Confidence assessment of a quantum execution result."""
    estimated_fidelity: float = 1.0
    confidence_level: str = "high"  # high / medium / low / very_low
    gate_error_contribution: float = 0.0
    readout_error_contribution: float = 0.0
    decoherence_contribution: float = 0.0
    mitigation_applied: str = "none"
    warnings: List[str] = field(default_factory=list)


class FidelityScorer:
    """Score the trustworthiness of quantum execution results."""

    THRESHOLDS = {
        "high": 0.95,
        "medium": 0.85,
        "low": 0.70,
    }

    def __init__(self, capabilities: BackendCapabilities) -> None:
        self._caps = capabilities

    def score(
        self,
        circuit: cirq.Circuit,
        mitigation: MitigationStrategy = MitigationStrategy.NONE,
        calibration: Optional[CalibrationData] = None,
    ) -> FidelityReport:
        """Produce a fidelity report for a circuit on the device."""
        ops = list(circuit.all_operations())
        n_single = sum(1 for o in ops if len(o.qubits) == 1 and not cirq.is_measurement(o))
        n_two = sum(1 for o in ops if len(o.qubits) == 2)
        n_readout = sum(1 for o in ops if cirq.is_measurement(o))
        depth = len(circuit)

        gate_err = (
            n_single * self._caps.single_qubit_error
            + n_two * self._caps.two_qubit_error
        )
        readout_err = n_readout * self._caps.readout_error

        total_time_us = depth * (self._caps.two_qubit_gate_time_ns / 1000.0)
        decoherence = 1.0 - math.exp(-total_time_us / max(self._caps.t2_us, 1e-6))

        raw_fidelity = max(0.0, 1.0 - gate_err - readout_err - decoherence)

        # Mitigation improvement estimates
        mitigation_boost = {
            MitigationStrategy.NONE: 0.0,
            MitigationStrategy.MEASUREMENT_ERROR_MITIGATION: 0.02,
            MitigationStrategy.ZERO_NOISE_EXTRAPOLATION: 0.05,
            MitigationStrategy.PROBABILISTIC_ERROR_CANCELLATION: 0.08,
            MitigationStrategy.TWIRLED_READOUT: 0.01,
        }
        adjusted = min(1.0, raw_fidelity + mitigation_boost.get(mitigation, 0.0))

        # Confidence level
        if adjusted >= self.THRESHOLDS["high"]:
            level = "high"
        elif adjusted >= self.THRESHOLDS["medium"]:
            level = "medium"
        elif adjusted >= self.THRESHOLDS["low"]:
            level = "low"
        else:
            level = "very_low"

        warnings = []
        if adjusted < 0.5:
            warnings.append("Result fidelity below 50% — results are unreliable")
        if decoherence > 0.1:
            warnings.append(f"High decoherence ({decoherence:.3f}) — consider reducing circuit depth")
        if self._caps.is_simulator:
            warnings.append("Running on simulator — fidelity estimate is ideal")

        return FidelityReport(
            estimated_fidelity=round(adjusted, 6),
            confidence_level=level,
            gate_error_contribution=round(gate_err, 6),
            readout_error_contribution=round(readout_err, 6),
            decoherence_contribution=round(decoherence, 6),
            mitigation_applied=mitigation.value,
            warnings=warnings,
        )


# ======================================================================
# Circuit retry manager
# ======================================================================

class CircuitRetryManager:
    """Automatic retry logic for hardware execution failures.

    Supports configurable retry policies: exponential backoff,
    recompilation on different qubits, and strategy escalation.
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_base_s: float = 1.0,
        backoff_factor: float = 2.0,
    ) -> None:
        self._max_retries = max_retries
        self._backoff_base = backoff_base_s
        self._backoff_factor = backoff_factor
        self._retry_history: List[Dict[str, Any]] = []

    def execute_with_retry(
        self,
        run_fn: Callable[[cirq.Circuit, int], cirq.Result],
        circuit: cirq.Circuit,
        repetitions: int = 1000,
        recompile_fn: Optional[Callable[[cirq.Circuit], cirq.Circuit]] = None,
    ) -> Dict[str, Any]:
        """Execute *circuit* via *run_fn* with automatic retries.

        On each retry:
          1. Wait with exponential backoff
          2. Optionally recompile (different qubit mapping)
          3. Retry execution
        """
        last_error: Optional[Exception] = None
        current_circuit = circuit

        for attempt in range(self._max_retries + 1):
            try:
                result = run_fn(current_circuit, repetitions)
                self._retry_history.append({
                    "attempt": attempt,
                    "success": True,
                    "timestamp": time.time(),
                })
                return {
                    "result": result,
                    "attempts": attempt + 1,
                    "success": True,
                }
            except Exception as exc:
                last_error = exc
                self._retry_history.append({
                    "attempt": attempt,
                    "success": False,
                    "error": str(exc),
                    "timestamp": time.time(),
                })
                logger.warning(
                    "Attempt %d/%d failed: %s",
                    attempt + 1, self._max_retries + 1, exc,
                )

                if attempt < self._max_retries:
                    wait = self._backoff_base * (self._backoff_factor ** attempt)
                    time.sleep(wait)

                    # recompile on retry to get a different qubit mapping
                    if recompile_fn and attempt >= 1:
                        current_circuit = recompile_fn(circuit)
                        logger.info("Recompiled circuit for retry %d", attempt + 1)

        return {
            "result": None,
            "attempts": self._max_retries + 1,
            "success": False,
            "last_error": str(last_error),
        }

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._retry_history)
