"""Transaction and isolation level enumerations."""

from enum import Enum


class TransactionStatus(Enum):
    """Possible states of a database transaction."""
    ACTIVE = "active"
    COMMITTED = "committed"
    ABORTED = "aborted"
    PENDING = "pending"


class IsolationLevel(Enum):
    """Transaction isolation levels."""
    READ_UNCOMMITTED = "read_uncommitted"
    READ_COMMITTED = "read_committed"
    REPEATABLE_READ = "repeatable_read"
    SERIALIZABLE = "serializable"
    QUANTUM_CONSISTENT = "quantum_consistent"
