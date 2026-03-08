"""
Side-Channel Mitigation
~~~~~~~~~~~~~~~~~~~~~~~~~
Defences against timing attacks, power-analysis, and cache probing
on quantum circuit execution and classical cryptographic operations.
"""

import logging
import os
import time
import threading
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def constant_time_compare(a: bytes, b: bytes) -> bool:
    """Compare two byte strings in constant time (prevents timing leaks)."""
    if len(a) != len(b):
        # Still do a full XOR walk to maintain constant-ish timing,
        # but result is always False.
        dummy = 0
        for x, y in zip(a, b[:len(a)]):
            dummy |= x ^ y
        return False  # length mismatch
    result = 0
    for x, y in zip(a, b):
        result |= x ^ y
    return result == 0


class SideChannelMitigator:
    """
    Applies side-channel countermeasures around callable operations.

    Features
    --------
    * **Constant-time padding**: normalises execution time so all calls
      take at least ``min_duration`` seconds.
    * **Dummy operations**: inserts random no-op work to obscure power
      and EM profiles.
    * **Jitter injection**: adds small random delays to frustrate
      statistical timing analysis.
    * **Operation counting**: tracks how many protected calls have been
      made (useful for audit).
    """

    def __init__(
        self,
        *,
        min_duration: float = 0.005,
        jitter_range: float = 0.002,
        dummy_ops: int = 8,
    ) -> None:
        self._min_duration = max(0.0, min_duration)
        self._jitter_range = max(0.0, jitter_range)
        self._dummy_ops = max(0, dummy_ops)
        self._call_count = 0
        self._lock = threading.Lock()

    @property
    def call_count(self) -> int:
        with self._lock:
            return self._call_count

    def protect(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute *fn* with side-channel countermeasures.

        1. Run dummy operations before the real call.
        2. Execute the real function and capture the result.
        3. Pad remaining time so total ≥ ``min_duration``.
        4. Add random jitter.
        """
        start = time.monotonic()

        # 1. dummy work (randomised to vary power profile)
        self._run_dummy_ops()

        # 2. real call
        result = fn(*args, **kwargs)

        # 3. constant-time padding
        elapsed = time.monotonic() - start
        remaining = self._min_duration - elapsed
        if remaining > 0:
            self._busy_wait(remaining)

        # 4. jitter
        if self._jitter_range > 0:
            jitter = (int.from_bytes(os.urandom(2), "big") / 65535) * self._jitter_range
            self._busy_wait(jitter)

        with self._lock:
            self._call_count += 1

        return result

    def constant_compare(self, a: bytes, b: bytes) -> bool:
        """Convenience wrapper around module-level constant_time_compare."""
        return self.protect(constant_time_compare, a, b)

    # -- internals ---------------------------------------------------------

    def _run_dummy_ops(self) -> None:
        """Execute random dummy computations."""
        n = self._dummy_ops
        if n <= 0:
            return
        # Vary the count slightly so power trace is non-deterministic
        extra = int.from_bytes(os.urandom(1), "big") % max(n, 1)
        total = n + extra
        acc = 0
        for _ in range(total):
            acc ^= int.from_bytes(os.urandom(4), "big")
        # discard acc — the work is the point

    @staticmethod
    def _busy_wait(duration: float) -> None:
        """Spin-wait for *duration* seconds (avoids sleep granularity issues)."""
        end = time.monotonic() + duration
        while time.monotonic() < end:
            pass
