"""
qndb.core.operations.gates — Quantum Gate Library
===================================================

Modular gate implementations for database operations.
"""

from qndb.core.operations.gates.oracle import OracleBuilder          # noqa: F401
from qndb.core.operations.gates.comparison import ComparisonGates     # noqa: F401
from qndb.core.operations.gates.arithmetic import ArithmeticGates     # noqa: F401
from qndb.core.operations.gates.transforms import TransformGates      # noqa: F401
from qndb.core.operations.gates.aggregation import AggregationGates   # noqa: F401
from qndb.core.operations.gates.sorting import SortingGates           # noqa: F401
from qndb.core.operations.gates.database_gates import DatabaseGates   # noqa: F401

__all__ = [
    "OracleBuilder", "ComparisonGates", "ArithmeticGates",
    "TransformGates", "AggregationGates", "SortingGates",
    "DatabaseGates",
]
