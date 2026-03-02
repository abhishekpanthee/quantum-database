"""Quantum job model."""

from datetime import datetime
from typing import Any, Dict, Optional, Set

from qndb.middleware.scheduling.enums import JobStatus, JobPriority


class QuantumJob:
    """Represents a quantum database job to be scheduled."""

    def __init__(
        self,
        job_id: str,
        query: Dict[str, Any],
        priority: JobPriority = JobPriority.NORMAL,
        deadline: Optional[datetime] = None,
        user_id: Optional[str] = None,
        estimated_runtime: float = 60.0,
    ) -> None:
        self.job_id = job_id
        self.query = query
        self.priority = priority
        self.deadline = deadline
        self.user_id = user_id
        self.estimated_runtime = estimated_runtime

        self.status = JobStatus.QUEUED
        self.queued_time = datetime.now()
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.result: Any = None
        self.error: Optional[Exception] = None

        self.qubit_count = self._estimate_qubit_count()
        self.circuit_depth = self._estimate_circuit_depth()
        self.assigned_qubits: Set[int] = set()

    def _estimate_qubit_count(self) -> int:
        if "qubit_allocation" in self.query and "total_qubits" in self.query["qubit_allocation"]:
            return self.query["qubit_allocation"]["total_qubits"]
        return 10

    def _estimate_circuit_depth(self) -> int:
        if "circuits" in self.query and self.query["circuits"]:
            return max(c.get("depth", 100) for c in self.query["circuits"])
        return 100

    def start(self) -> None:
        self.status = JobStatus.RUNNING
        self.start_time = datetime.now()

    def complete(self, result: Any) -> None:
        self.status = JobStatus.COMPLETED
        self.end_time = datetime.now()
        self.result = result

    def fail(self, error: Exception) -> None:
        self.status = JobStatus.FAILED
        self.end_time = datetime.now()
        self.error = error

    def cancel(self) -> None:
        self.status = JobStatus.CANCELLED
        self.end_time = datetime.now()

    def preempt(self) -> None:
        self.status = JobStatus.PREEMPTED
        self.end_time = datetime.now()

    def get_runtime(self) -> float:
        if self.start_time is None:
            return 0
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    def get_wait_time(self) -> float:
        start = self.start_time or datetime.now()
        return (start - self.queued_time).total_seconds()

    def is_deadline_approaching(self, threshold_seconds: int = 60) -> bool:
        if self.deadline is None:
            return False
        time_left = (self.deadline - datetime.now()).total_seconds()
        return 0 < time_left < threshold_seconds

    def get_priority_score(self) -> float:
        base_score = self.priority.value * 1000
        if self.deadline:
            time_left = max(0, (self.deadline - datetime.now()).total_seconds())
            base_score += 1000 / (time_left + 1)
        wait_time = self.get_wait_time()
        base_score += min(wait_time / 10, 100)
        return base_score

    def __lt__(self, other: "QuantumJob") -> bool:
        return self.get_priority_score() > other.get_priority_score()
