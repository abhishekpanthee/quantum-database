"""Query type enumeration."""

from enum import Enum


class QueryType(Enum):
    """Types of supported quantum database queries."""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CREATE = "CREATE"
    DROP = "DROP"
    QUANTUM_SEARCH = "QSEARCH"
    QUANTUM_JOIN = "QJOIN"
    QUANTUM_COMPUTE = "QCOMPUTE"
    EXECUTE = "EXECUTE"
