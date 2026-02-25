"""Rule-based query rewrite engine."""

from typing import Dict, List, Optional

from qndb.middleware.optimization.statistics import StatisticsCollector


class RewriteEngine:
    """Applies rule-based rewrites to a ParsedQuery."""

    @staticmethod
    def predicate_pushdown(parsed_query):
        """Push WHERE conditions below JOINs when they reference only one table."""
        if not getattr(parsed_query, 'join_clauses', None):
            return parsed_query
        if not getattr(parsed_query, 'where_tree', None):
            return parsed_query
        # For now, mark conditions that reference only the left table
        # so the executor can apply them before the join.
        pq = parsed_query.copy()
        pq_conditions = getattr(pq, 'conditions', [])
        pushed: List[Dict] = []
        remaining: List[Dict] = []
        join_tables = {jc["table"] for jc in (pq.join_clauses or [])}
        for cond in pq_conditions:
            field = cond.get("field", "")
            if '.' in field:
                tbl = field.split('.')[0]
                if tbl not in join_tables:
                    pushed.append(cond)
                    continue
            remaining.append(cond)
        if pushed:
            pq.conditions = remaining
            # Attach pushed predicates for the executor to pick up early
            if not hasattr(pq, '_pushed_predicates'):
                object.__setattr__(pq, '_pushed_predicates', pushed)
        return pq

    @staticmethod
    def join_reorder(parsed_query, stats_collector: Optional[StatisticsCollector] = None):
        """Reorder JOINs so smallest tables are joined first."""
        jc = getattr(parsed_query, 'join_clauses', None)
        if not jc or len(jc) < 2:
            return parsed_query
        if stats_collector is None:
            return parsed_query

        def table_size(name):
            s = stats_collector.get(name)
            return s.row_count if s else 1_000_000

        pq = parsed_query.copy()
        pq.join_clauses = sorted(jc, key=lambda j: table_size(j["table"]))
        return pq
