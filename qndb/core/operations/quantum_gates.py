"""
Custom quantum gates implementation for quantum database operations.

.. deprecated::
    This module is a backward-compatibility shim.  New code should import
    from :mod:`qndb.core.operations.gates` instead.
"""

# Re-export the facade so existing imports continue to work.
from qndb.core.operations.gates.database_gates import DatabaseGates  # noqa: F401

__all__ = ["DatabaseGates"]
