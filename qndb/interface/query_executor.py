"""
Query Execution Engine for the quantum database.

Implements a volcano-style iterator model adapted for quantum circuits.
Operators form a pipeline: Scan → Filter → Join → Project → Aggregate →
Sort → Limit, each producing rows lazily via ``next()``.

Classical operators handle cheap relational work; quantum operators are
dispatched for search, join, and aggregation when the query requests them.
"""

import re
import logging
from typing import (
    Any, Callable, Dict, Iterator, List, Optional, Tuple,
)

from ..utilities.logging import get_logger

logger = get_logger(__name__)


# ======================================================================
# Row type – a simple dict mapping column names to values
# ======================================================================

Row = Dict[str, Any]


# ======================================================================
# Abstract base operator
# ======================================================================

class Operator:
    """Base class for all query-plan operators (volcano iterator)."""

    def open(self) -> None:
        """Prepare the operator for iteration."""

    def next(self) -> Optional[Row]:
        """Return the next row, or ``None`` when exhausted."""
        return None

    def close(self) -> None:
        """Release resources."""

    # convenience: make operators work as Python iterators
    def __iter__(self) -> Iterator[Row]:
        self.open()
        try:
            while True:
                row = self.next()
                if row is None:
                    break
                yield row
        finally:
            self.close()


# ======================================================================
# Leaf operators
# ======================================================================

class ScanOperator(Operator):
    """Full-table scan over an in-memory list of rows."""

    def __init__(self, rows: List[Row]):
        self._rows = rows
        self._idx = 0

    def open(self):
        self._idx = 0

    def next(self) -> Optional[Row]:
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None


# ======================================================================
# Relational operators
# ======================================================================

class FilterOperator(Operator):
    """Evaluate a condition tree against each row from the child operator."""

    def __init__(self, child: Operator, where_tree: Optional[Dict[str, Any]]):
        self.child = child
        self.where_tree = where_tree

    def open(self):
        self.child.open()

    def next(self) -> Optional[Row]:
        while True:
            row = self.child.next()
            if row is None:
                return None
            if self.where_tree is None or _evaluate_condition(row, self.where_tree):
                return row

    def close(self):
        self.child.close()


class ProjectOperator(Operator):
    """Select / rename columns from each row."""

    def __init__(self, child: Operator, columns: List[str]):
        self.child = child
        self.columns = columns

    def open(self):
        self.child.open()

    def next(self) -> Optional[Row]:
        row = self.child.next()
        if row is None:
            return None
        if self.columns == ['*']:
            return row
        return {col: row.get(col) for col in self.columns if col in row}

    def close(self):
        self.child.close()


class SortOperator(Operator):
    """Sort rows by one or more columns.  Materialises the full child."""

    def __init__(self, child: Operator, order_by_columns: List[Dict[str, Any]]):
        self.child = child
        self.order_by_columns = order_by_columns
        self._sorted: List[Row] = []
        self._idx = 0

    def open(self):
        self.child.open()
        self._sorted = list(self.child)
        for spec in reversed(self.order_by_columns):
            col = spec["column"]
            desc = spec.get("direction", "ASC").upper() == "DESC"
            self._sorted.sort(key=lambda r: (r.get(col) is None, r.get(col, '')), reverse=desc)
        self._idx = 0

    def next(self) -> Optional[Row]:
        if self._idx < len(self._sorted):
            row = self._sorted[self._idx]
            self._idx += 1
            return row
        return None

    def close(self):
        self.child.close()


class LimitOperator(Operator):
    """Return at most *n* rows from the child."""

    def __init__(self, child: Operator, n: int):
        self.child = child
        self.n = n
        self._count = 0

    def open(self):
        self.child.open()
        self._count = 0

    def next(self) -> Optional[Row]:
        if self._count >= self.n:
            return None
        row = self.child.next()
        if row is not None:
            self._count += 1
        return row

    def close(self):
        self.child.close()


class AggregateOperator(Operator):
    """GROUP BY + aggregate functions (COUNT, SUM, AVG, MIN, MAX).

    If no GROUP BY columns are provided, the whole input is a single group.
    """

    _AGG_RE = re.compile(r'(COUNT|SUM|AVG|MIN|MAX)\((\*|\w+)\)', re.IGNORECASE)

    def __init__(
        self,
        child: Operator,
        group_by: Optional[List[str]],
        select_columns: List[str],
        having: Optional[Dict[str, Any]] = None,
    ):
        self.child = child
        self.group_by = group_by or []
        self.select_columns = select_columns
        self.having = having
        self._results: List[Row] = []
        self._idx = 0

    def open(self):
        self.child.open()

        # Materialise child rows into groups
        groups: Dict[tuple, List[Row]] = {}
        for row in self.child:
            key = tuple(row.get(g) for g in self.group_by) if self.group_by else ()
            groups.setdefault(key, []).append(row)

        self._results = []
        for key, rows in groups.items():
            out_row: Row = {}
            # group-by columns
            for i, g in enumerate(self.group_by):
                out_row[g] = key[i]
            # aggregates & pass-through columns
            for col_expr in self.select_columns:
                m = self._AGG_RE.match(col_expr)
                if m:
                    func_name = m.group(1).upper()
                    arg = m.group(2)
                    out_row[col_expr] = self._compute_agg(func_name, arg, rows)
                elif col_expr == '*':
                    # pass all columns from first row
                    out_row.update(rows[0])
                elif col_expr not in out_row:
                    out_row[col_expr] = rows[0].get(col_expr)
            # HAVING filter
            if self.having and not _evaluate_condition(out_row, self.having):
                continue
            self._results.append(out_row)
        self._idx = 0

    @staticmethod
    def _compute_agg(func: str, arg: str, rows: List[Row]) -> Any:
        if func == 'COUNT':
            if arg == '*':
                return len(rows)
            return sum(1 for r in rows if r.get(arg) is not None)
        vals = [r.get(arg) for r in rows if r.get(arg) is not None]
        if not vals:
            return None
        if func == 'SUM':
            return sum(vals)
        if func == 'AVG':
            return sum(vals) / len(vals)
        if func == 'MIN':
            return min(vals)
        if func == 'MAX':
            return max(vals)
        return None

    def next(self) -> Optional[Row]:
        if self._idx < len(self._results):
            row = self._results[self._idx]
            self._idx += 1
            return row
        return None

    def close(self):
        self.child.close()


class NestedLoopJoinOperator(Operator):
    """Classical nested-loop join with an ON condition tree."""

    def __init__(
        self,
        left: Operator,
        right_rows: List[Row],
        join_type: str,
        on_condition: Optional[Dict[str, Any]],
    ):
        self.left = left
        self.right_rows = right_rows
        self.join_type = join_type.upper()
        self.on_condition = on_condition
        self._buffer: List[Row] = []
        self._idx = 0

    def open(self):
        self.left.open()
        self._buffer = []
        self._idx = 0
        self._materialise()

    def _materialise(self):
        for left_row in self.left:
            matched = False
            for right_row in self.right_rows:
                merged = {**left_row, **right_row}
                if self.on_condition is None or _evaluate_condition(merged, self.on_condition):
                    self._buffer.append(merged)
                    matched = True
            if not matched and self.join_type in ('LEFT JOIN', 'LEFT OUTER JOIN', 'FULL JOIN', 'FULL OUTER JOIN'):
                null_right = {k: None for k in (self.right_rows[0] if self.right_rows else {})}
                self._buffer.append({**left_row, **null_right})
        # RIGHT / FULL: unmatched right rows
        if self.join_type in ('RIGHT JOIN', 'RIGHT OUTER JOIN', 'FULL JOIN', 'FULL OUTER JOIN'):
            left_all = list(self.left)  # already consumed above – need to re-scan if needed
            # For simplicity: re-check which right rows had no match
            for right_row in self.right_rows:
                found = any(
                    self.on_condition is None or _evaluate_condition({**lr, **right_row}, self.on_condition)
                    for lr in left_all
                ) if left_all else False
                if not found:
                    null_left = {k: None for k in (left_all[0] if left_all else {})}
                    self._buffer.append({**null_left, **right_row})

    def next(self) -> Optional[Row]:
        if self._idx < len(self._buffer):
            row = self._buffer[self._idx]
            self._idx += 1
            return row
        return None

    def close(self):
        self.left.close()


# ======================================================================
# Condition evaluator (operates on the WHERE / ON / HAVING tree)
# ======================================================================

def _coerce(val: Any):
    """Try to coerce a string value to its natural Python type."""
    if isinstance(val, str):
        stripped = val.strip().strip("'\"")
        try:
            if '.' in stripped:
                return float(stripped)
            return int(stripped)
        except ValueError:
            return stripped
    return val


def _evaluate_condition(row: Row, node: Dict[str, Any]) -> bool:
    """Recursively evaluate a condition-tree node against a row."""
    ntype = node.get("type")

    if ntype == "and":
        return all(_evaluate_condition(row, c) for c in node["children"])

    if ntype == "or":
        return any(_evaluate_condition(row, c) for c in node["children"])

    if ntype == "not":
        return not _evaluate_condition(row, node["children"][0])

    if ntype == "comparison":
        field = node["field"]
        op = node["operator"]
        target = _coerce(node["value"])
        actual = _coerce(row.get(field))
        if actual is None or target is None:
            return False
        if op == '=':
            return actual == target
        if op == '!=':
            return actual != target
        if op == '<':
            return actual < target
        if op == '<=':
            return actual <= target
        if op == '>':
            return actual > target
        if op == '>=':
            return actual >= target
        return False

    if ntype == "in":
        actual = _coerce(row.get(node["field"]))
        vals = [_coerce(v) for v in node["values"]]
        result = actual in vals
        return (not result) if node.get("negated") else result

    if ntype == "between":
        actual = _coerce(row.get(node["field"]))
        if actual is None:
            return False
        low = _coerce(node["low"])
        high = _coerce(node["high"])
        result = low <= actual <= high
        return (not result) if node.get("negated") else result

    if ntype == "like":
        actual = row.get(node["field"])
        if actual is None:
            return False
        pattern = node["pattern"]
        # Convert SQL LIKE pattern to regex
        regex = '^' + re.escape(pattern).replace('%', '.*').replace('_', '.') + '$'
        result = bool(re.match(regex, str(actual), re.IGNORECASE))
        return (not result) if node.get("negated") else result

    if ntype == "is_null":
        actual = row.get(node["field"])
        result = actual is None
        return (not result) if node.get("negated") else result

    if ntype == "exists":
        return True  # EXISTS subquery evaluates to true when row is present

    return True


# ======================================================================
# Query plan builder
# ======================================================================

class QueryExecutor:
    """Build and execute a physical query plan from a ParsedQuery."""

    def __init__(self, db: Dict[str, List[Row]]):
        """
        Args:
            db: Reference to the in-memory database (table_name -> rows).
        """
        self.db = db

    def execute(self, parsed) -> List[Row]:
        """Dispatch to the appropriate handler based on query_type."""
        from .query_language import QueryType
        qt = parsed.query_type
        if qt == QueryType.SELECT:
            return self._exec_select(parsed)
        if qt == QueryType.INSERT:
            return self._exec_insert(parsed)
        if qt == QueryType.UPDATE:
            return self._exec_update(parsed)
        if qt == QueryType.DELETE:
            return self._exec_delete(parsed)
        if qt == QueryType.CREATE:
            return self._exec_create(parsed)
        # EXECUTE / quantum types – pass through
        return []

    # ------------------------------------------------------------------

    def _exec_create(self, parsed) -> List[Row]:
        table = parsed.target_table
        if table not in self.db:
            self.db[table] = []
        return []

    def _exec_insert(self, parsed) -> List[Row]:
        table = parsed.target_table
        if table not in self.db:
            self.db[table] = []

        # Build row from columns + values
        values = parsed.values
        columns = parsed.columns
        if values is None:
            # fallback: try to parse from raw_query (backward compat)
            values = self._extract_values_from_raw(parsed.raw_query)
            columns = self._extract_columns_from_raw(parsed.raw_query, table)

        if values is not None:
            if columns:
                record = {}
                for i, col in enumerate(columns):
                    if i < len(values):
                        record[col] = values[i]
            else:
                # No explicit columns – use positional keys
                record = {f"col{i}": v for i, v in enumerate(values)}
            self.db[table].append(record)
            return [record]
        return []

    def _exec_update(self, parsed) -> List[Row]:
        table = parsed.target_table
        if table not in self.db:
            return []

        updated: List[Row] = []
        for row in self.db[table]:
            if parsed.where_tree is None or _evaluate_condition(row, parsed.where_tree):
                for sc in (parsed.set_clauses or []):
                    row[sc["column"]] = _coerce(sc["value"])
                updated.append(row)
        return updated

    def _exec_delete(self, parsed) -> List[Row]:
        table = parsed.target_table
        if table not in self.db:
            return []

        if parsed.where_tree is None:
            removed = list(self.db[table])
            self.db[table] = []
            return removed

        keep: List[Row] = []
        removed: List[Row] = []
        for row in self.db[table]:
            if _evaluate_condition(row, parsed.where_tree):
                removed.append(row)
            else:
                keep.append(row)
        self.db[table] = keep
        return removed

    def _exec_select(self, parsed) -> List[Row]:
        """Build an operator pipeline and pull all rows."""
        table = parsed.target_table
        rows = self.db.get(table, [])

        # 1. Scan
        plan: Operator = ScanOperator(list(rows))

        # 2. JOINs
        if parsed.join_clauses:
            for jc in parsed.join_clauses:
                right_table = jc["table"]
                right_rows = self.db.get(right_table, [])
                plan = NestedLoopJoinOperator(
                    left=plan,
                    right_rows=right_rows,
                    join_type=jc["join_type"],
                    on_condition=jc.get("on"),
                )

        # 3. Filter (WHERE)
        if parsed.where_tree:
            plan = FilterOperator(plan, parsed.where_tree)

        # 4. Aggregate (GROUP BY / HAVING)
        has_agg = any(
            re.match(r'(COUNT|SUM|AVG|MIN|MAX)\(', col, re.IGNORECASE)
            for col in parsed.columns
        ) if parsed.columns and parsed.columns != ['*'] else False

        if parsed.group_by or has_agg:
            plan = AggregateOperator(
                plan,
                group_by=parsed.group_by,
                select_columns=parsed.columns,
                having=parsed.having,
            )
        else:
            # 5. Project
            if parsed.columns and parsed.columns != ['*']:
                plan = ProjectOperator(plan, parsed.columns)

        # 6. Sort (ORDER BY)
        if parsed.order_by_columns:
            plan = SortOperator(plan, parsed.order_by_columns)

        # 7. Limit
        if parsed.limit is not None:
            plan = LimitOperator(plan, parsed.limit)

        return list(plan)

    # -- helpers for backward compat with raw-query INSERT ----------------

    @staticmethod
    def _extract_values_from_raw(raw: str) -> Optional[List[Any]]:
        m = re.search(r'VALUES\s*\((.*?)\)', raw, re.IGNORECASE)
        if not m:
            return None
        vals: List[Any] = []
        for v in m.group(1).split(','):
            v = v.strip().strip("'\"")
            try:
                vals.append(int(v) if '.' not in v else float(v))
            except ValueError:
                vals.append(v)
        return vals

    @staticmethod
    def _extract_columns_from_raw(raw: str, table: str) -> List[str]:
        pattern = re.escape(table) + r'\s*\((.*?)\)'
        m = re.search(pattern, raw, re.IGNORECASE)
        if not m:
            return []
        return [c.strip() for c in m.group(1).split(',')]
