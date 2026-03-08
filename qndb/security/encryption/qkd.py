"""
Quantum Key Distribution (BB84)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Simulation of the BB84 QKD protocol.  When real quantum hardware is
available, the measurement and channel steps are delegated to the
device driver layer.
"""

import hashlib
import secrets
from collections import namedtuple
from typing import Any, Dict, List, Optional

import numpy as np


QKDResult = namedtuple("QKDResult", ["key", "security_parameters", "error_rate"])


class QuantumKeyDistribution:
    """BB84 quantum key distribution protocol."""

    def __init__(
        self, qubit_count: int = 1024, error_threshold: float = 0.1
    ) -> None:
        self.qubit_count = qubit_count
        self.error_threshold = error_threshold
        self._basis_choices: Dict[str, Dict[str, Any]] = {}

    def generate_bb84_key(
        self, session_id: str, remote_party: str
    ) -> QKDResult:
        """Simulate a full BB84 key-exchange session.

        Raises ``ValueError`` if the error rate exceeds the threshold
        (possible eavesdropping).
        """
        alice_bases = np.random.randint(0, 2, self.qubit_count)
        alice_bits = np.random.randint(0, 2, self.qubit_count)

        self._basis_choices[session_id] = {
            "bases": alice_bases.copy(),
            "bits": alice_bits.copy(),
        }

        bob_bases = np.random.randint(0, 2, self.qubit_count)
        matching_bases = alice_bases == bob_bases

        bob_bits = np.zeros(self.qubit_count, dtype=int)
        bob_bits[matching_bases] = alice_bits[matching_bases]

        non_matching = ~matching_bases
        random_matches = np.random.random(self.qubit_count) < 0.5
        bob_bits[non_matching] = np.logical_xor(
            alice_bits[non_matching], random_matches[non_matching]
        ).astype(int)

        shared_key_indices = np.where(matching_bases)[0]
        if len(shared_key_indices) == 0:
            raise ValueError("No matching bases found during QKD protocol.")

        split = len(shared_key_indices) // 4
        verification_indices = shared_key_indices[:split]
        key_indices = shared_key_indices[split:]

        va = alice_bits[verification_indices]
        vb = bob_bits[verification_indices]
        errors = int(np.sum(va != vb))
        error_rate = errors / len(verification_indices) if len(verification_indices) > 0 else 0.0

        if error_rate > self.error_threshold:
            raise ValueError(
                f"QKD error rate too high: {error_rate:.2f}. "
                "Possible eavesdropping detected."
            )

        final_key = self._bits_to_bytes(alice_bits[key_indices])
        security_params = {
            "total_bits": self.qubit_count,
            "matching_bases": int(np.sum(matching_bases)),
            "verification_bits": len(verification_indices),
            "key_bits": len(key_indices),
            "error_rate": error_rate,
        }

        return QKDResult(final_key, security_params, error_rate)

    @staticmethod
    def _bits_to_bytes(bits: np.ndarray) -> bytes:
        padded_length = ((len(bits) + 7) // 8) * 8
        padded = np.zeros(padded_length, dtype=int)
        padded[: len(bits)] = bits
        result = bytearray()
        for i in range(0, len(padded), 8):
            byte_val = 0
            for j in range(8):
                if i + j < len(padded):
                    byte_val |= padded[i + j] << (7 - j)
            result.append(byte_val)
        return bytes(result)
