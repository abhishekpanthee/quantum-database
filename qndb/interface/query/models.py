"""Data models for the quantum SQL dialect."""

from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass
from copy import deepcopy

from qndb.interface.query.enums import QueryType


@dataclass
class QuantumClause:
    """Represents a quantum-specific clause in a query."""
    type: str
    parameters: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert the quantum clause to a dictionary representation."""
        return {"type": self.type, "parameters": self.parameters}


@dataclass
class ParsedQuery:
    """Represents a parsed quantum SQL query."""
    query_type: QueryType
    target_table: str
    columns: List[Any]
    conditions: List[Dict[str, Any]]
    quantum_clauses: List[QuantumClause]
    limit: Optional[int] = None
    order_by: Optional[str] = None
    raw_query: str = ""
    where_tree: Optional[Dict[str, Any]] = None
    group_by: Optional[List[str]] = None
    having: Optional[Dict[str, Any]] = None
    join_clauses: Optional[List[Dict[str, Any]]] = None
    subqueries: Optional[Dict[str, Any]] = None
    values: Optional[List[Any]] = None
    set_clauses: Optional[List[Dict[str, Any]]] = None
    table_alias: Optional[str] = None
    order_by_columns: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert ParsedQuery to a dictionary for serialization."""
        result = {
            "query_type": self.query_type.value if isinstance(self.query_type, Enum) else self.query_type,
            "target_table": self.target_table,
            "columns": self.columns,
            "conditions": self.conditions,
            "quantum_clauses": [qc.to_dict() for qc in self.quantum_clauses] if self.quantum_clauses else [],
            "limit": self.limit,
            "order_by": self.order_by,
            "raw_query": self.raw_query,
        }
        if self.where_tree is not None:
            result["where_tree"] = self.where_tree
        if self.group_by is not None:
            result["group_by"] = self.group_by
        if self.having is not None:
            result["having"] = self.having
        if self.join_clauses is not None:
            result["join_clauses"] = self.join_clauses
        if self.subqueries is not None:
            result["subqueries"] = self.subqueries
        if self.values is not None:
            result["values"] = self.values
        if self.set_clauses is not None:
            result["set_clauses"] = self.set_clauses
        if self.table_alias is not None:
            result["table_alias"] = self.table_alias
        if self.order_by_columns is not None:
            result["order_by_columns"] = self.order_by_columns
        return result

    def __iter__(self):
        """Make ParsedQuery iterable like a dictionary."""
        yield from self.to_dict().items()

    def get(self, key, default=None):
        """Dictionary-like get method."""
        return getattr(self, key, default)

    def __getitem__(self, key):
        """Support dictionary-like access with []."""
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def __contains__(self, key):
        """Support 'in' operator."""
        return hasattr(self, key)

    def keys(self):
        """Return the keys like a dictionary."""
        return self.to_dict().keys()

    def values_dict(self):
        """Return the values like a dictionary."""
        return self.to_dict().values()

    def to_circuit(self) -> Any:
        """Convert the parsed query to a quantum circuit.

        Returns ``None`` when no quantum acceleration is applicable.
        """
        return None

    def copy(self):
        """Create a deep copy of the ParsedQuery object."""
        return ParsedQuery(
            query_type=self.query_type,
            target_table=self.target_table,
            columns=deepcopy(self.columns),
            conditions=deepcopy(self.conditions),
            quantum_clauses=deepcopy(self.quantum_clauses),
            limit=self.limit,
            order_by=self.order_by,
            raw_query=self.raw_query,
            where_tree=deepcopy(self.where_tree),
            group_by=deepcopy(self.group_by),
            having=deepcopy(self.having),
            join_clauses=deepcopy(self.join_clauses),
            subqueries=deepcopy(self.subqueries),
            values=deepcopy(self.values),
            set_clauses=deepcopy(self.set_clauses),
            table_alias=self.table_alias,
            order_by_columns=deepcopy(self.order_by_columns),
        )
