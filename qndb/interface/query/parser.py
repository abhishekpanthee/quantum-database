"""Main query parser for the quantum SQL dialect.

Features:
 - Full WHERE clause: AND, OR, NOT, parenthesised expressions, IN, BETWEEN, LIKE
 - GROUP BY + HAVING with quantum aggregation hooks
 - ORDER BY with multi-column ASC/DESC
 - JOIN syntax: INNER, LEFT, RIGHT, FULL OUTER, CROSS
 - Subquery support (scalar values in WHERE)
 - Parameterised query escaping (injection-safe)
 - Query validation / semantic analysis
"""

import re
from typing import Dict, List, Any, Optional, Tuple

from qndb.core.quantum_engine import QuantumEngine
from qndb.core.operations.quantum_gates import DatabaseGates
from qndb.core.operations.search import QuantumSearch
from qndb.core.operations.join import QuantumJoin
from qndb.middleware.optimizer import QueryOptimizer
from qndb.utilities.logging import get_logger

from qndb.interface.query.enums import QueryType
from qndb.interface.query.models import QuantumClause, ParsedQuery
from qndb.interface.query.tokenizer import WhereTokenizer
from qndb.interface.query.where_parser import WhereParser
from qndb.interface.query.helpers import flatten_conditions, find_top_level, extract_between

logger = get_logger(__name__)


class QueryParser:
    """Parser for the quantum SQL dialect."""

    def __init__(self):
        """Initialize the quantum SQL parser."""
        self.quantum_engine = QuantumEngine()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def parse(self, query_string: str, params: Optional[Dict[str, Any]] = None) -> ParsedQuery:
        """Parse a quantum SQL query string into a structured format.

        Args:
            query_string: The quantum SQL query to parse
            params: Optional parameter dictionary for parameterized queries

        Returns:
            ParsedQuery object representing the structured query
        """
        logger.debug("Parsing query: %s", query_string)

        if params:
            query_string = self._substitute_params(query_string, params)

        normalized = self._normalize_query(query_string)
        query_type = self._determine_query_type(normalized)

        _parsers = {
            QueryType.SELECT: self._parse_select_query,
            QueryType.CREATE: self._parse_create_query,
            QueryType.INSERT: self._parse_insert_query,
            QueryType.UPDATE: self._parse_update_query,
            QueryType.DELETE: self._parse_delete_query,
            QueryType.QUANTUM_SEARCH: self._parse_quantum_search,
            QueryType.QUANTUM_JOIN: self._parse_quantum_join,
            QueryType.QUANTUM_COMPUTE: self._parse_quantum_compute,
        }

        if query_type == QueryType.EXECUTE:
            return ParsedQuery(
                query_type=QueryType.EXECUTE,
                target_table="system",
                columns=[],
                conditions=[],
                quantum_clauses=[],
                raw_query=normalized,
            )

        parser_fn = _parsers.get(query_type)
        if parser_fn is None:
            raise ValueError(f"Unsupported query type: {query_type}")
        return parser_fn(normalized)

    # ------------------------------------------------------------------
    # Parameter substitution (injection-safe)
    # ------------------------------------------------------------------

    def _substitute_params(self, query: str, params: Dict[str, Any]) -> str:
        """Replace ``:name`` placeholders with properly escaped literal values."""
        result = query
        for key, value in params.items():
            placeholder = f":{key}"
            if isinstance(value, str):
                escaped = value.replace("'", "''")
                result = result.replace(placeholder, f"'{escaped}'")
            elif value is None:
                result = result.replace(placeholder, "NULL")
            elif isinstance(value, bool):
                result = result.replace(placeholder, "TRUE" if value else "FALSE")
            elif isinstance(value, (int, float)):
                result = result.replace(placeholder, str(value))
            else:
                # Treat unknown types as strings for safety
                escaped = str(value).replace("'", "''")
                result = result.replace(placeholder, f"'{escaped}'")
        return result

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalize_query(self, query: str) -> str:
        """Normalize whitespace and keyword casing while preserving string literals."""
        placeholders: Dict[str, str] = {}

        def _stash(match):
            ph = f"__STR_{len(placeholders)}__"
            placeholders[ph] = match.group(0)
            return ph

        # Strip comments
        query = re.sub(r'--.*?$', '', query, flags=re.MULTILINE)
        query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)

        # Stash string literals
        safe = re.sub(r"'[^']*'", _stash, query)

        # Collapse whitespace first so multi-word keywords match reliably
        safe = re.sub(r'\s+', ' ', safe).strip()

        # Uppercase SQL keywords
        keywords = [
            # multi-word (longest first)
            "LEFT OUTER JOIN", "RIGHT OUTER JOIN", "FULL OUTER JOIN",
            "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL JOIN", "CROSS JOIN",
            "GROUP BY", "ORDER BY",
            "IF NOT EXISTS",
            # single-word
            "SELECT", "FROM", "WHERE", "INSERT", "INTO", "VALUES",
            "UPDATE", "SET", "DELETE", "CREATE", "DROP", "TABLE",
            "QSEARCH", "QJOIN", "QCOMPUTE", "USING",
            "HAVING", "LIMIT", "ASC", "DESC",
            "AND", "OR", "NOT", "IN", "BETWEEN", "LIKE",
            "IS", "NULL", "EXISTS",
            "ON", "AS", "JOIN",
            "WITH", "ENCODING", "PRIMARY", "KEY",
        ]
        for kw in keywords:
            safe = re.sub(r'\b' + kw + r'\b', kw, safe, flags=re.IGNORECASE)

        # Restore literals
        for ph, lit in placeholders.items():
            safe = safe.replace(ph, lit)

        return safe

    # ------------------------------------------------------------------
    # Query-type detection
    # ------------------------------------------------------------------

    def _determine_query_type(self, query: str) -> QueryType:
        """Determine the type of quantum SQL query."""
        upper = query.strip().upper()
        _prefixes = [
            ("SELECT ", QueryType.SELECT),
            ("INSERT ", QueryType.INSERT),
            ("CREATE ", QueryType.CREATE),
            ("UPDATE ", QueryType.UPDATE),
            ("DELETE ", QueryType.DELETE),
            ("DROP ",   QueryType.DROP),
            ("QSEARCH ", QueryType.QUANTUM_SEARCH),
            ("QJOIN ",  QueryType.QUANTUM_JOIN),
            ("QCOMPUTE ", QueryType.QUANTUM_COMPUTE),
        ]
        for prefix, qt in _prefixes:
            if upper.startswith(prefix):
                return qt
        if upper in ("COMMIT", "ROLLBACK") or upper.startswith("BEGIN"):
            return QueryType.EXECUTE
        raise ValueError(f"Unable to determine query type: {query}")

    # ------------------------------------------------------------------
    # WHERE clause helper
    # ------------------------------------------------------------------

    def _parse_where_clause(
        self, query: str, terminators: Optional[List[str]] = None
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extract and parse a WHERE clause.

        Returns:
            (where_tree, flat_conditions) – the tree representation and
            a backward-compatible flat list of simple comparisons.
        """
        if terminators is None:
            terminators = []
        where_text, _ = extract_between(query, 'WHERE', terminators)
        if not where_text:
            return None, []
        tree = WhereParser(WhereTokenizer(where_text).tokens).parse()
        return tree, flatten_conditions(tree)

    # ==================================================================
    # SELECT
    # ==================================================================

    def _parse_select_query(self, query: str) -> ParsedQuery:
        """Parse a full SELECT query with JOINs, GROUP BY, HAVING, ORDER BY."""

        # ---- columns (SELECT ... FROM) ----
        columns_text, _ = extract_between(query, 'SELECT', ['FROM'])
        if columns_text is None:
            raise ValueError("Invalid SELECT clause")
        if columns_text.strip() == '*':
            columns = ['*']
        else:
            columns = [c.strip() for c in columns_text.split(',')]

        # ---- FROM table [AS alias] ----
        from_terminators = [
            'WHERE', 'GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT',
            'INNER JOIN', 'LEFT JOIN', 'LEFT OUTER JOIN',
            'RIGHT JOIN', 'RIGHT OUTER JOIN',
            'FULL JOIN', 'FULL OUTER JOIN', 'CROSS JOIN', 'JOIN',
        ]
        from_text, _ = extract_between(query, 'FROM', from_terminators)
        if from_text is None:
            raise ValueError("FROM clause missing or invalid in SELECT query")
        # Handle comma-separated implicit cross-joins by taking first table
        first_table_raw = from_text.split(',')[0].strip()
        table_parts = first_table_raw.split()
        table_name = table_parts[0] if table_parts else ''
        table_alias = None
        _non_table_words = {
            'WHERE', 'GROUP', 'ORDER', 'LIMIT', 'HAVING',
            'INNER', 'LEFT', 'RIGHT', 'FULL', 'CROSS', 'JOIN',
        }
        if len(table_parts) >= 3 and table_parts[1].upper() == 'AS':
            table_alias = table_parts[2]
        elif len(table_parts) == 2 and table_parts[1].upper() not in _non_table_words:
            table_alias = table_parts[1]

        # ---- JOINs ----
        join_clauses = self._parse_join_clauses(query)

        # ---- WHERE ----
        where_tree, conditions = self._parse_where_clause(
            query, ['GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT'])

        # ---- GROUP BY ----
        group_by = None
        gb_text, _ = extract_between(query, 'GROUP BY', ['HAVING', 'ORDER BY', 'LIMIT'])
        if gb_text:
            group_by = [g.strip() for g in gb_text.split(',')]

        # ---- HAVING ----
        having = None
        hv_text, _ = extract_between(query, 'HAVING', ['ORDER BY', 'LIMIT'])
        if hv_text:
            having = WhereParser(WhereTokenizer(hv_text).tokens).parse()

        # ---- ORDER BY ----
        order_by = None
        order_by_columns = None
        ob_text, _ = extract_between(query, 'ORDER BY', ['LIMIT'])
        if ob_text:
            order_by = ob_text
            order_by_columns = []
            for part in ob_text.split(','):
                tokens = part.strip().split()
                col = tokens[0] if tokens else ''
                direction = 'ASC'
                if len(tokens) > 1 and tokens[-1].upper() in ('ASC', 'DESC'):
                    direction = tokens[-1].upper()
                order_by_columns.append({"column": col, "direction": direction})

        # ---- LIMIT ----
        limit = None
        limit_match = re.search(r'\bLIMIT\s+(\d+)', query, re.IGNORECASE)
        if limit_match:
            limit = int(limit_match.group(1))

        # ---- quantum clauses ----
        quantum_clauses = self._extract_quantum_clauses(query)

        return ParsedQuery(
            query_type=QueryType.SELECT,
            target_table=table_name,
            columns=columns,
            conditions=conditions,
            quantum_clauses=quantum_clauses,
            limit=limit,
            order_by=order_by,
            raw_query=query,
            where_tree=where_tree,
            group_by=group_by,
            having=having,
            join_clauses=join_clauses if join_clauses else None,
            table_alias=table_alias,
            order_by_columns=order_by_columns,
        )

    # ==================================================================
    # JOIN clause extraction
    # ==================================================================

    _JOIN_PATTERN = re.compile(
        r'\b(INNER\s+JOIN|LEFT\s+OUTER\s+JOIN|LEFT\s+JOIN|'
        r'RIGHT\s+OUTER\s+JOIN|RIGHT\s+JOIN|'
        r'FULL\s+OUTER\s+JOIN|FULL\s+JOIN|CROSS\s+JOIN|JOIN)\b',
        re.IGNORECASE,
    )

    def _parse_join_clauses(self, query: str) -> List[Dict[str, Any]]:
        """Extract all JOIN clauses from a query."""
        joins: List[Dict[str, Any]] = []
        for m in self._JOIN_PATTERN.finditer(query):
            join_type = re.sub(r'\s+', ' ', m.group(1)).upper()
            rest = query[m.end():].strip()

            # table name [AS alias]
            tbl_match = re.match(r'(\w+)(?:\s+AS\s+(\w+))?', rest, re.IGNORECASE)
            if not tbl_match:
                continue
            tbl_name = tbl_match.group(1)
            tbl_alias = tbl_match.group(2)
            after_table = rest[tbl_match.end():].strip()

            # ON condition – up to next JOIN/WHERE/GROUP BY/…
            on_tree = None
            if after_table.upper().startswith('ON '):
                on_text = after_table[3:]
                for term in [
                    'INNER JOIN', 'LEFT OUTER JOIN', 'LEFT JOIN',
                    'RIGHT OUTER JOIN', 'RIGHT JOIN',
                    'FULL OUTER JOIN', 'FULL JOIN', 'CROSS JOIN', 'JOIN',
                    'WHERE', 'GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT',
                ]:
                    tp = find_top_level(on_text, term)
                    if tp != -1:
                        on_text = on_text[:tp]
                on_text = on_text.strip()
                if on_text:
                    on_tree = WhereParser(WhereTokenizer(on_text).tokens).parse()

            joins.append({
                "join_type": join_type,
                "table": tbl_name,
                "alias": tbl_alias,
                "on": on_tree,
            })
        return joins

    # ==================================================================
    # CREATE
    # ==================================================================

    def _parse_create_query(self, query: str) -> ParsedQuery:
        """Parse a CREATE QUANTUM TABLE query."""
        table_match = re.search(
            r'CREATE\s+(?:QUANTUM\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)',
            query, re.IGNORECASE)
        if not table_match:
            raise ValueError("Invalid CREATE TABLE format")
        table_name = table_match.group(1)

        columns: List[Any] = []
        cols_match = re.search(r'\((.*?)\)', query)
        if cols_match:
            for col_def in cols_match.group(1).split(','):
                parts = [p.strip() for p in col_def.strip().split()]
                if parts:
                    col_info: Dict[str, Any] = {
                        'name': parts[0],
                        'type': parts[1] if len(parts) > 1 else 'TEXT',
                    }
                    if len(parts) > 2:
                        col_info['constraints'] = parts[2:]
                    columns.append(col_info)

        quantum_clauses: List[QuantumClause] = []
        enc_match = re.search(r'WITH ENCODING=(\w+)', query, re.IGNORECASE)
        if enc_match:
            quantum_clauses.append(QuantumClause(
                type="encoding", parameters={"type": enc_match.group(1)}))

        return ParsedQuery(
            query_type=QueryType.CREATE,
            target_table=table_name,
            columns=columns,
            conditions=[],
            quantum_clauses=quantum_clauses,
            raw_query=query,
        )

    # ==================================================================
    # INSERT
    # ==================================================================

    def _parse_insert_query(self, query: str) -> ParsedQuery:
        """Parse an INSERT query."""
        table_match = re.search(r'INTO\s+(\w+)', query, re.IGNORECASE)
        if not table_match:
            raise ValueError("INTO clause missing or invalid in INSERT query")
        table_name = table_match.group(1)

        columns_match = re.search(r'INTO\s+\w+\s*\((.*?)\)', query, re.IGNORECASE)
        columns = [c.strip() for c in columns_match.group(1).split(',')] if columns_match else []

        # Extract VALUES
        values = None
        val_match = re.search(r'VALUES\s*\((.*?)\)', query, re.IGNORECASE)
        if val_match:
            raw_vals = val_match.group(1)
            values = []
            for v in raw_vals.split(','):
                v = v.strip().strip("'\"")
                try:
                    if '.' in v:
                        values.append(float(v))
                    else:
                        values.append(int(v))
                except ValueError:
                    values.append(v)

        quantum_clauses = self._extract_quantum_clauses(query)
        return ParsedQuery(
            query_type=QueryType.INSERT,
            target_table=table_name,
            columns=columns,
            conditions=[],
            quantum_clauses=quantum_clauses,
            raw_query=query,
            values=values,
        )

    # ==================================================================
    # UPDATE
    # ==================================================================

    def _parse_update_query(self, query: str) -> ParsedQuery:
        """Parse an UPDATE query with full WHERE support."""
        table_match = re.search(r'UPDATE\s+(\w+)', query, re.IGNORECASE)
        if not table_match:
            raise ValueError("Invalid UPDATE query format")
        table_name = table_match.group(1)

        set_text, _ = extract_between(query, 'SET', ['WHERE'])
        if set_text is None:
            raise ValueError("SET clause missing in UPDATE query")
        set_clauses: List[Dict[str, Any]] = []
        for assignment in set_text.split(','):
            if '=' in assignment:
                col, val = assignment.split('=', 1)
                set_clauses.append({"column": col.strip(), "value": val.strip()})
        # backward-compat: columns as raw assignment strings
        columns = [a.strip() for a in set_text.split(',')]

        where_tree, conditions = self._parse_where_clause(query, [])
        quantum_clauses = self._extract_quantum_clauses(query)

        return ParsedQuery(
            query_type=QueryType.UPDATE,
            target_table=table_name,
            columns=columns,
            conditions=conditions,
            quantum_clauses=quantum_clauses,
            raw_query=query,
            where_tree=where_tree,
            set_clauses=set_clauses,
        )

    # ==================================================================
    # DELETE
    # ==================================================================

    def _parse_delete_query(self, query: str) -> ParsedQuery:
        """Parse a DELETE query with full WHERE support."""
        table_match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
        if not table_match:
            raise ValueError("FROM clause missing or invalid in DELETE query")
        table_name = table_match.group(1)

        where_tree, conditions = self._parse_where_clause(query, [])
        quantum_clauses = self._extract_quantum_clauses(query)

        return ParsedQuery(
            query_type=QueryType.DELETE,
            target_table=table_name,
            columns=[],
            conditions=conditions,
            quantum_clauses=quantum_clauses,
            raw_query=query,
            where_tree=where_tree,
        )

    # ==================================================================
    # QSEARCH
    # ==================================================================

    def _parse_quantum_search(self, query: str) -> ParsedQuery:
        """Parse a QSEARCH quantum-specific query."""
        table_match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
        if not table_match:
            raise ValueError("FROM clause missing or invalid in QSEARCH query")
        table_name = table_match.group(1)

        params_match = re.search(r'USING\s+(.*?)(?:\s+FROM)', query, re.IGNORECASE)
        columns = [p.strip() for p in params_match.group(1).split(',')] if params_match else []

        where_tree, conditions = self._parse_where_clause(query, [])
        quantum_clauses = self._extract_quantum_clauses(query)

        return ParsedQuery(
            query_type=QueryType.QUANTUM_SEARCH,
            target_table=table_name,
            columns=columns,
            conditions=conditions,
            quantum_clauses=quantum_clauses,
            raw_query=query,
            where_tree=where_tree,
        )

    # ==================================================================
    # QJOIN
    # ==================================================================

    def _parse_quantum_join(self, query: str) -> ParsedQuery:
        """Parse a QJOIN quantum-specific query."""
        tables_match = re.search(r'TABLES\s+(.*?)(?:\s+ON)', query, re.IGNORECASE)
        if not tables_match:
            raise ValueError("TABLES clause missing or invalid in QJOIN query")
        tables = [t.strip() for t in tables_match.group(1).split(',')]
        if len(tables) < 2:
            raise ValueError("QJOIN requires at least two tables")
        target_table = tables[0]

        join_match = re.search(r'ON\s+(.*?)(?:\s+USING|\s+$)', query, re.IGNORECASE)
        conditions: List[Dict[str, Any]] = []
        if join_match:
            jtext = join_match.group(1).strip()
            for part in jtext.split('AND'):
                if '=' in part:
                    left, right = part.split('=', 1)
                    conditions.append({
                        'left': left.strip(),
                        'operator': '=',
                        'right': right.strip(),
                    })

        quantum_clauses = self._extract_quantum_clauses(query)
        quantum_clauses.append(QuantumClause(
            type="join_tables", parameters={"tables": tables[1:]}))

        return ParsedQuery(
            query_type=QueryType.QUANTUM_JOIN,
            target_table=target_table,
            columns=[],
            conditions=conditions,
            quantum_clauses=quantum_clauses,
            raw_query=query,
        )

    # ==================================================================
    # QCOMPUTE
    # ==================================================================

    def _parse_quantum_compute(self, query: str) -> ParsedQuery:
        """Parse a QCOMPUTE custom quantum computation query."""
        target_match = re.search(r'ON\s+(\w+)', query, re.IGNORECASE)
        target_table = target_match.group(1) if target_match else ""

        circuit_match = re.search(r'CIRCUIT\s+\((.*?)\)', query, re.IGNORECASE)
        columns = [circuit_match.group(1).strip()] if circuit_match else []

        quantum_clauses = self._extract_quantum_clauses(query)
        return ParsedQuery(
            query_type=QueryType.QUANTUM_COMPUTE,
            target_table=target_table,
            columns=columns,
            conditions=[],
            quantum_clauses=quantum_clauses,
            raw_query=query,
        )

    # ==================================================================
    # Quantum clause extraction
    # ==================================================================

    def _extract_quantum_clauses(self, query: str) -> List[QuantumClause]:
        """Extract quantum-specific clauses from the query."""
        qc: List[QuantumClause] = []
        if m := re.search(r'ALGORITHM\s+(\w+)', query, re.IGNORECASE):
            qc.append(QuantumClause(type="algorithm", parameters={"name": m.group(1)}))
        if m := re.search(r'ITERATIONS\s+(\d+)', query, re.IGNORECASE):
            qc.append(QuantumClause(type="iterations", parameters={"count": int(m.group(1))}))
        if m := re.search(r'OPTIMIZATION\s+(\w+)', query, re.IGNORECASE):
            qc.append(QuantumClause(type="optimization", parameters={"level": m.group(1).upper()}))
        if m := re.search(r'ERROR_CORRECTION\s+(\w+)', query, re.IGNORECASE):
            qc.append(QuantumClause(type="error_correction", parameters={"level": m.group(1)}))
        return qc

    # ==================================================================
    # Query validation / semantic analysis
    # ==================================================================

    def validate_query(self, parsed: ParsedQuery) -> List[str]:
        """Perform semantic validation on a parsed query.

        Returns:
            A list of error strings.  Empty means valid.
        """
        errors: List[str] = []

        if not parsed.target_table and parsed.query_type not in (QueryType.EXECUTE,):
            errors.append("Missing target table")

        if parsed.query_type == QueryType.SELECT:
            if not parsed.columns:
                errors.append("SELECT requires at least one column or '*'")
            if parsed.having and not parsed.group_by:
                errors.append("HAVING clause requires GROUP BY")
            if parsed.group_by and parsed.columns != ['*']:
                agg_prefixes = ('COUNT(', 'SUM(', 'AVG(', 'MIN(', 'MAX(')
                non_agg = [
                    col for col in parsed.columns
                    if not any(col.upper().startswith(f) for f in agg_prefixes)
                    and col not in parsed.group_by
                ]
                if non_agg:
                    errors.append(
                        f"Columns {non_agg} must appear in GROUP BY "
                        f"or be aggregate functions")

        if parsed.query_type == QueryType.INSERT:
            if parsed.columns and parsed.values is not None:
                if len(parsed.columns) != len(parsed.values):
                    errors.append(
                        f"Column count ({len(parsed.columns)}) does not match "
                        f"value count ({len(parsed.values)})")

        if parsed.query_type == QueryType.UPDATE:
            if not parsed.set_clauses:
                errors.append("UPDATE requires SET clause")

        return errors

    # ==================================================================
    # Circuit generation
    # ==================================================================

    def generate_quantum_circuit(self, parsed_query: ParsedQuery) -> Any:
        """Generate a quantum circuit from a parsed query.

        Returns ``None`` when the query does not benefit from quantum
        acceleration.  Subclasses or extensions may override this to
        provide Grover-based search circuits, amplitude estimation, etc.
        """
        return None
