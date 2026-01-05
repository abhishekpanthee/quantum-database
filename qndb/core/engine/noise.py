"""Noise model configuration for quantum circuits."""

import cirq
from typing import List, Optional


class NoiseConfig:
    """Configurable noise model for quantum circuits."""

    def __init__(
        self,
        depolarizing: float = 0.0,
        amplitude_damping: float = 0.0,
        readout_error: float = 0.0,
    ) -> None:
        self.depolarizing = depolarizing
        self.amplitude_damping = amplitude_damping
        self.readout_error = readout_error

    def has_noise(self) -> bool:
        return (
            self.depolarizing > 0
            or self.amplitude_damping > 0
            or self.readout_error > 0
        )

    def to_cirq_noise_model(self) -> cirq.NoiseModel:
        """Build a composite Cirq noise model from the configuration."""
        noise_ops: List[cirq.Gate] = []
        if self.depolarizing > 0:
            noise_ops.append(cirq.depolarize(p=self.depolarizing))
        if self.amplitude_damping > 0:
            noise_ops.append(cirq.amplitude_damp(gamma=self.amplitude_damping))
        if not noise_ops:
            return cirq.UNCONSTRAINED_DEVICE
        return cirq.ConstantQubitNoiseModel(qubit_noise_gate=noise_ops[0])
