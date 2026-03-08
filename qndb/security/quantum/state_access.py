"""
Quantum State Access Logger
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Records every operation (create, read, measure, entangle, discard)
performed on quantum states. Provides circuit-level audit granularity.
"""

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StateAccessRecord:
    """A single access record for a quantum state."""

    __slots__ = (
        "record_id", "timestamp", "user_id", "circuit_id",
        "operation", "qubit_indices", "details", "success",
    )

    def __init__(
        self,
        user_id: str,
        circuit_id: str,
        operation: str,
        qubit_indices: List[int],
        *,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
    ) -> None:
        self.record_id = uuid.uuid4().hex
        self.timestamp = time.time()
        self.user_id = user_id
        self.circuit_id = circuit_id
        self.operation = operation  # create, read, measure, entangle, discard, gate
        self.qubit_indices = qubit_indices
        self.details = details or {}
        self.success = success

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "circuit_id": self.circuit_id,
            "operation": self.operation,
            "qubit_indices": self.qubit_indices,
            "details": self.details,
            "success": self.success,
        }


class QuantumStateAccessLogger:
    """Thread-safe logger for quantum state access events."""

    def __init__(self, max_records: int = 100_000) -> None:
        self._records: List[StateAccessRecord] = []
        self._lock = threading.Lock()
        self._max_records = max_records

    def log_access(
        self,
        user_id: str,
        circuit_id: str,
        operation: str,
        qubit_indices: List[int],
        *,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
    ) -> str:
        """Log a state access and return the record ID."""
        record = StateAccessRecord(
            user_id, circuit_id, operation, qubit_indices,
            details=details, success=success,
        )
        with self._lock:
            self._records.append(record)
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]
        logger.debug(
            "State access: user=%s circuit=%s op=%s qubits=%s",
            user_id, circuit_id, operation, qubit_indices,
        )
        return record.record_id

    def log_gate(
        self,
        user_id: str,
        circuit_id: str,
        gate_name: str,
        qubit_indices: List[int],
    ) -> str:
        return self.log_access(
            user_id, circuit_id, "gate", qubit_indices,
            details={"gate": gate_name},
        )

    def log_measurement(
        self,
        user_id: str,
        circuit_id: str,
        qubit_indices: List[int],
        *,
        result: Optional[Any] = None,
    ) -> str:
        return self.log_access(
            user_id, circuit_id, "measure", qubit_indices,
            details={"result": result},
        )

    def log_entanglement(
        self,
        user_id: str,
        circuit_id: str,
        qubit_a: int,
        qubit_b: int,
    ) -> str:
        return self.log_access(
            user_id, circuit_id, "entangle", [qubit_a, qubit_b],
        )

    # -- query interface ---------------------------------------------------

    def get_records(
        self,
        *,
        user_id: Optional[str] = None,
        circuit_id: Optional[str] = None,
        operation: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 1000,
    ) -> List[StateAccessRecord]:
        with self._lock:
            result = list(self._records)
        if user_id:
            result = [r for r in result if r.user_id == user_id]
        if circuit_id:
            result = [r for r in result if r.circuit_id == circuit_id]
        if operation:
            result = [r for r in result if r.operation == operation]
        if since:
            result = [r for r in result if r.timestamp >= since]
        return result[-limit:]

    def get_circuit_timeline(
        self, circuit_id: str
    ) -> List[Dict[str, Any]]:
        """Return all access records for a circuit in chronological order."""
        records = self.get_records(circuit_id=circuit_id, limit=100_000)
        return [r.to_dict() for r in sorted(records, key=lambda r: r.timestamp)]

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
