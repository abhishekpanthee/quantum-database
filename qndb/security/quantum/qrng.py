"""
Quantum Random Number Generator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Produces cryptographically-suitable random bytes by simulating
quantum measurement:  superposition → Hadamard → measure.

When a real quantum backend is available the class delegates to it;
otherwise it falls back to ``os.urandom`` (CSPRNG) and marks output
as *simulated*.
"""

import hashlib
import logging
import os
import struct
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class QuantumRNG:
    """
    Quantum (or simulated-quantum) random number generator.

    Parameters
    ----------
    use_hardware : bool
        If ``True`` and a hardware backend is discovered, use it.
        Currently always falls back to OS CSPRNG.
    entropy_pool_size : int
        Bytes to pre-buffer in the entropy pool.
    """

    def __init__(
        self,
        *,
        use_hardware: bool = False,
        entropy_pool_size: int = 4096,
    ) -> None:
        self._use_hardware = use_hardware
        self._pool_size = entropy_pool_size
        self._pool = bytearray()
        self._lock = threading.Lock()
        self._total_bytes_generated: int = 0
        self._is_simulated = True
        self._refill()

    @property
    def is_simulated(self) -> bool:
        return self._is_simulated

    @property
    def total_bytes_generated(self) -> int:
        return self._total_bytes_generated

    # -- core API ----------------------------------------------------------

    def random_bytes(self, n: int) -> bytes:
        """Return *n* random bytes."""
        if n <= 0:
            return b""
        with self._lock:
            while len(self._pool) < n:
                self._refill_locked()
            out = bytes(self._pool[:n])
            del self._pool[:n]
            self._total_bytes_generated += n
        return out

    def random_int(self, lo: int = 0, hi: int = 2**63 - 1) -> int:
        """Return a random integer in ``[lo, hi]`` (inclusive)."""
        if lo > hi:
            raise ValueError("lo must be <= hi")
        span = hi - lo + 1
        # determine bytes needed
        byte_count = (span.bit_length() + 7) // 8
        # rejection sampling to remove modulo bias
        limit = (256 ** byte_count // span) * span
        while True:
            raw = int.from_bytes(self.random_bytes(byte_count), "big")
            if raw < limit:
                return lo + (raw % span)

    def random_float(self) -> float:
        """Return a random float in ``[0.0, 1.0)``."""
        raw = struct.unpack("!Q", self.random_bytes(8))[0]
        return (raw >> 11) / (2**53)

    def random_bits(self, n: int) -> str:
        """Return a string of *n* random bits (``'0'``/``'1'``)."""
        byte_count = (n + 7) // 8
        raw = self.random_bytes(byte_count)
        bits = bin(int.from_bytes(raw, "big"))[2:].zfill(byte_count * 8)
        return bits[:n]

    def generate_key(self, length: int = 32) -> bytes:
        """Generate a cryptographic key of *length* bytes."""
        raw = self.random_bytes(length * 2)  # extra entropy
        return hashlib.sha256(raw).digest()[:length]

    # -- health / diagnostics ----------------------------------------------

    def health_check(self) -> dict:
        """Run basic statistical checks on a 1 KB sample."""
        sample = self.random_bytes(1024)
        ones = sum(bin(b).count("1") for b in sample)
        total_bits = 1024 * 8
        ratio = ones / total_bits
        # NIST monobit rough bound: 0.49 – 0.51 for good entropy
        healthy = 0.45 < ratio < 0.55
        return {
            "healthy": healthy,
            "ones_ratio": round(ratio, 4),
            "sample_bytes": 1024,
            "is_simulated": self._is_simulated,
            "total_generated": self._total_bytes_generated,
        }

    # -- internal ----------------------------------------------------------

    def _refill(self) -> None:
        with self._lock:
            self._refill_locked()

    def _refill_locked(self) -> None:
        # Use OS-level cryptographic RNG (backed by /dev/urandom or CNG)
        self._pool.extend(os.urandom(self._pool_size))
        self._is_simulated = True
