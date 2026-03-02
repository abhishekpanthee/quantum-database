"""Quantum resource manager for the scheduler."""

import logging
import threading
from typing import Optional, Set

from qndb.middleware.scheduling.job import QuantumJob

logger = logging.getLogger(__name__)


class ResourceManager:
    """Manages quantum computing resources for the scheduler."""

    def __init__(
        self,
        total_qubits: int = 50,
        max_parallel_jobs: int = 5,
    ) -> None:
        self.total_qubits = total_qubits
        self.max_parallel_jobs = max_parallel_jobs
        self.available_qubits = total_qubits
        self.running_jobs = 0
        self.lock = threading.Lock()
        self._in_use: Set[int] = set()

    def allocate(self, job: QuantumJob) -> bool:
        with self.lock:
            if (
                self.available_qubits >= job.qubit_count
                and self.running_jobs < self.max_parallel_jobs
            ):
                start = self._next_free_block(job.qubit_count)
                if start is None:
                    return False
                assigned = set(range(start, start + job.qubit_count))
                self._in_use.update(assigned)
                job.assigned_qubits = assigned
                self.available_qubits -= job.qubit_count
                self.running_jobs += 1
                return True
            return False

    def release(self, job: QuantumJob) -> None:
        with self.lock:
            self._in_use -= job.assigned_qubits
            self.available_qubits += job.qubit_count
            self.running_jobs -= 1

    def can_allocate(self, job: QuantumJob) -> bool:
        with self.lock:
            return (
                self.available_qubits >= job.qubit_count
                and self.running_jobs < self.max_parallel_jobs
            )

    def _next_free_block(self, size: int) -> Optional[int]:
        run = 0
        start = 0
        for i in range(self.total_qubits):
            if i not in self._in_use:
                if run == 0:
                    start = i
                run += 1
                if run >= size:
                    return start
            else:
                run = 0
        return None

    def overlapping_qubits(self, job: QuantumJob, other_qubits: Set[int]) -> bool:
        return bool(job.assigned_qubits & other_qubits)
