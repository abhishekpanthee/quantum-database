"""Per-tenant resource quota."""


class ResourceQuota:
    """Per-tenant resource quota for multi-tenant scheduling."""

    def __init__(
        self,
        user_id: str,
        max_qubits: int = 20,
        max_concurrent_jobs: int = 3,
    ) -> None:
        self.user_id = user_id
        self.max_qubits = max_qubits
        self.max_concurrent_jobs = max_concurrent_jobs
        self.used_qubits = 0
        self.running_jobs = 0

    def can_allocate(self, qubits: int) -> bool:
        return (
            self.used_qubits + qubits <= self.max_qubits
            and self.running_jobs < self.max_concurrent_jobs
        )

    def allocate(self, qubits: int) -> None:
        self.used_qubits += qubits
        self.running_jobs += 1

    def release(self, qubits: int) -> None:
        self.used_qubits = max(0, self.used_qubits - qubits)
        self.running_jobs = max(0, self.running_jobs - 1)
