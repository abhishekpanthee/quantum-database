"""Transaction and Savepoint models."""

import time
from typing import Dict, List, Any, Optional, Set, Tuple

from qndb.interface.transactions.enums import TransactionStatus, IsolationLevel


class Savepoint:
    """Represents a named savepoint within a transaction."""

    __slots__ = ('name', 'lsn', 'operations_count')

    def __init__(self, name: str, lsn: int, operations_count: int):
        self.name = name
        self.lsn = lsn
        self.operations_count = operations_count


class Transaction:
    """Represents a database transaction with ACID properties."""

    def __init__(self, transaction_id: str,
                 isolation_level: IsolationLevel = IsolationLevel.SERIALIZABLE,
                 snapshot_ts: Optional[float] = None):
        self.transaction_id = transaction_id
        self.status = TransactionStatus.ACTIVE
        self.isolation_level = isolation_level
        self.start_time = time.time()
        self.snapshot_ts = snapshot_ts or self.start_time
        self.commit_time: Optional[float] = None
        self.operations: List[Dict[str, Any]] = []
        self.locks: Set[Tuple[str, str]] = set()  # (resource_id, lock_type)
        self.accessed_resources: Set[str] = set()
        self.modified_resources: Set[str] = set()
        self.savepoints: List[Savepoint] = []

    def add_operation(self, operation: Dict[str, Any]) -> None:
        self.operations.append(operation)
        resource = operation.get("resource")
        if resource:
            self.accessed_resources.add(resource)
            if operation.get("type") in ("write", "update", "delete"):
                self.modified_resources.add(resource)

    def create_savepoint(self, name: str, lsn: int) -> Savepoint:
        sp = Savepoint(name, lsn, len(self.operations))
        self.savepoints.append(sp)
        return sp

    def rollback_to_savepoint(self, name: str) -> bool:
        for i, sp in enumerate(self.savepoints):
            if sp.name == name:
                self.operations = self.operations[:sp.operations_count]
                self.savepoints = self.savepoints[:i + 1]
                return True
        return False

    def has_conflicts(self, other_transaction: 'Transaction') -> bool:
        if (self.status != TransactionStatus.ACTIVE or
                other_transaction.status != TransactionStatus.ACTIVE):
            return False

        if self.isolation_level == IsolationLevel.SERIALIZABLE:
            return bool(
                self.accessed_resources.intersection(other_transaction.modified_resources) or
                self.modified_resources.intersection(other_transaction.accessed_resources))

        if self.isolation_level == IsolationLevel.REPEATABLE_READ:
            return bool(self.accessed_resources.intersection(other_transaction.modified_resources))

        if self.isolation_level == IsolationLevel.READ_COMMITTED:
            return False

        if self.isolation_level == IsolationLevel.QUANTUM_CONSISTENT:
            # Probabilistic reads: only conflict on write-write overlap
            return bool(self.modified_resources.intersection(other_transaction.modified_resources))

        return False
