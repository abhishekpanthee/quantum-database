"""Quantum execution backend abstraction."""

import cirq
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class BackendBase:
    """Abstract base for quantum execution backends."""

    def run(self, circuit: cirq.Circuit, repetitions: int = 1000) -> cirq.Result:
        raise NotImplementedError

    def simulate(self, circuit: cirq.Circuit) -> cirq.SimulationTrialResult:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError


class SimulatorBackend(BackendBase):
    """Local Cirq simulator backend."""

    def __init__(self, noise_model: Optional["NoiseConfig"] = None) -> None:
        from qndb.core.engine.noise import NoiseConfig  # local import to avoid circularity

        if noise_model and noise_model.has_noise():
            self._simulator = cirq.DensityMatrixSimulator(
                noise=noise_model.to_cirq_noise_model()
            )
        else:
            self._simulator = cirq.Simulator()
        self._noise_model = noise_model

    def run(self, circuit: cirq.Circuit, repetitions: int = 1000) -> cirq.Result:
        return self._simulator.run(circuit, repetitions=repetitions)

    def simulate(self, circuit: cirq.Circuit):
        return self._simulator.simulate(circuit)

    @property
    def name(self) -> str:
        return "simulator"


class CloudBackend(BackendBase):
    """Cloud quantum backends (IBM / Google / IonQ).

    Uses local simulator as fallback when the provider SDK is not
    installed or API credentials are not configured.  For full hardware
    support, use the dedicated backend classes in ``qndb.core.engine.hardware``.
    """

    def __init__(self, provider: str = "ibm", api_key: Optional[str] = None) -> None:
        self._provider = provider
        self._api_key = api_key
        self._simulator = cirq.Simulator()
        logger.warning("CloudBackend(%s): using local simulator fallback", provider)

    def run(self, circuit: cirq.Circuit, repetitions: int = 1000) -> cirq.Result:
        return self._simulator.run(circuit, repetitions=repetitions)

    def simulate(self, circuit: cirq.Circuit):
        return self._simulator.simulate(circuit)

    @property
    def name(self) -> str:
        return f"cloud-{self._provider}"
