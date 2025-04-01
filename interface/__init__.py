"""
Interface module for the quantum database system.
Provides client interfaces, query language, and connection management.
"""

from .db_client import DatabaseClient
from .query_language import QueryParser, QueryType
from .transaction_manager import TransactionManager, IsolationLevel
from .connection_pool import ConnectionPool

__all__ = [
    'DatabaseClient',
    'QueryParser',
    'QueryType',
    'TransactionManager',
    'IsolationLevel',
    'ConnectionPool'
]

# Version information
__version__ = '0.1.0'