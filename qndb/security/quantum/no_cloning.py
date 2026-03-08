"""
No-Cloning Theorem Enforcement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Tracks quantum state handles and prevents unauthorized duplication.

The no-cloning theorem (Wootters & Zurek, 1982) states that it is
impossible to create an independent and identical copy of an arbitrary
unknown quantum state.  This module enforces that constraint at the
software layer by maintaining a registry of live state handles and
refusing copy operations.
"""

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class QuantumStateHandle:
    """An opaque reference to a quantum state in the system."""

    __slots__ = (
        "handle_id", "owner_id", "created_at", "circuit_id",
        "qubit_indices", "is_measured", "_cloned_from",
    )

    def __init__(
        self,
        owner_id: str,
        circuit_id: str,
        qubit_indices: List[int],
        *,
        cloned_from: Optional[str] = None,
    ) -> None:
        self.handle_id = uuid.uuid4().hex
        self.owner_id = owner_id
        self.created_at = time.time()
        self.circuit_id = circuit_id
        self.qubit_indices = qubit_indices
        self.is_measured = False
        self._cloned_from = cloned_from

    def to_dict(self) -> Dict[str, Any]:
        return {
            "handle_id": self.handle_id,
            "owner_id": self.owner_id,
            "circuit_id": self.circuit_id,
            "qubit_indices": self.qubit_indices,
            "is_measured": self.is_measured,
            "created_at": self.created_at,
        }


class NoCloningViolation(Exception):
    """Raised when an operation would violate the no-cloning theorem."""
    pass


class NoCloningEnforcer:
    """Enforces the no-cloning constraint across the database.

    Every quantum state is registered with a unique handle.  Clone
    attempts are detected and blocked.
    """

    def __init__(self) -> None:
        self._registry: Dict[str, QuantumStateHandle] = {}
        self._circuit_handles: Dict[str, Set[str]] = {}  # circuit_id → handle IDs
        self._lock = threading.Lock()
        self._violation_count = 0

    def register_state(
        self,
        owner_id: str,
        circuit_id: str,
        qubit_indices: List[int],
    ) -> QuantumStateHandle:
        """Register a new quantum state and return its handle."""
        handle = QuantumStateHandle(owner_id, circuit_id, qubit_indices)
        with self._lock:
            self._registry[handle.handle_id] = handle
            self._circuit_handles.setdefault(circuit_id, set()).add(
                handle.handle_id
            )
        logger.debug(
            "Registered state %s for circuit %s (qubits %s)",
            handle.handle_id, circuit_id, qubit_indices,
        )
        return handle

    def attempt_clone(self, handle_id: str, requester_id: str) -> None:
        """Attempt to clone a state — always raises ``NoCloningViolation``."""
        with self._lock:
            self._violation_count += 1
            handle = self._registry.get(handle_id)
        state_info = handle.to_dict() if handle else {"handle_id": handle_id}
        logger.warning(
            "No-cloning violation #%d by %s on state %s",
            self._violation_count, requester_id, handle_id,
        )
        raise NoCloningViolation(
            f"Cannot clone quantum state {handle_id}: "
            "no-cloning theorem prohibits copying of arbitrary quantum states. "
            f"Requester: {requester_id}"
        )

    def mark_measured(self, handle_id: str) -> None:
        """Mark a state as measured (collapsed).  Classical data can be copied."""
        with self._lock:
            handle = self._registry.get(handle_id)
            if handle:
                handle.is_measured = True
                logger.debug("State %s marked as measured", handle_id)

    def release_state(self, handle_id: str) -> None:
        """Release a state handle (circuit completed / state discarded)."""
        with self._lock:
            handle = self._registry.pop(handle_id, None)
            if handle:
                cset = self._circuit_handles.get(handle.circuit_id)
                if cset:
                    cset.discard(handle_id)

    def is_clonable(self, handle_id: str) -> bool:
        """Quantum states are never clonable.  Returns ``True`` only for
        measured (classical) states."""
        with self._lock:
            handle = self._registry.get(handle_id)
            return handle is not None and handle.is_measured

    def get_handle(self, handle_id: str) -> Optional[QuantumStateHandle]:
        with self._lock:
            return self._registry.get(handle_id)

    def list_handles(
        self, *, circuit_id: Optional[str] = None
    ) -> List[QuantumStateHandle]:
        with self._lock:
            if circuit_id:
                ids = self._circuit_handles.get(circuit_id, set())
                return [self._registry[h] for h in ids if h in self._registry]
            return list(self._registry.values())

    @property
    def violation_count(self) -> int:
        return self._violation_count
