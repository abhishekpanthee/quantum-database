"""Main QueryOptimizer — cost-based optimizer with quantum-aware cost model."""

import logging
from typing import Dict, List, Any

from qndb.core.storage.circuit_compiler import CircuitCompiler
from qndb.utilities.benchmarking import cost_estimator

from qndb.middleware.optimization.statistics import StatisticsCollector, TableStatistics
from qndb.middleware.optimization.cost_model import QuantumCostModel
from qndb.middleware.optimization.plan_cache import PlanCache
from qndb.middleware.optimization.rewrite_engine import RewriteEngine

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """Cost-based query optimizer with quantum-aware cost model."""

    def __init__(self, max_depth: int = 100, optimization_level: int = 2,
                 available_qubits: int = 50, error_rate: float = 0.001):
        self.max_depth = max_depth
        self.optimization_level = optimization_level
        self.circuit_compiler = CircuitCompiler()
        self.cost_model = QuantumCostModel(error_rate, available_qubits)
        self.stats_collector = StatisticsCollector()
        self.plan_cache = PlanCache()
        self.rewriter = RewriteEngine()
        logger.info("Query optimizer initialized (level=%d, qubits=%d)",
                     optimization_level, available_qubits)

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def optimize(self, parsed_query) -> Any:
        """Optimize a parsed query for efficient execution."""
        if not hasattr(parsed_query, 'query_type'):
            return parsed_query

        # Check plan cache
        raw = getattr(parsed_query, 'raw_query', '')
        cached = self.plan_cache.get(raw) if raw else None
        if cached is not None:
            logger.debug("Plan cache hit for query")
            return cached

        # Dict-style query plan (legacy path)
        if isinstance(parsed_query, dict) and 'circuits' in parsed_query:
            return self.optimize_query_plan(parsed_query)

        # Rule-based rewrites
        pq = self.rewriter.predicate_pushdown(parsed_query)
        pq = self.rewriter.join_reorder(pq, self.stats_collector)

        # Attach cost estimate
        cost = self.estimate_query_cost(pq)
        if hasattr(pq, 'estimated_cost'):
            pq.estimated_cost = cost

        # Plan cache store
        if raw:
            self.plan_cache.put(raw, pq)

        return pq

    # ------------------------------------------------------------------
    # Cost estimation
    # ------------------------------------------------------------------

    def estimate_query_cost(self, parsed_query) -> Dict[str, Any]:
        table = getattr(parsed_query, 'target_table', '')
        stats = self.stats_collector.get(table)
        conditions = getattr(parsed_query, 'conditions', [])

        plan_info: Dict[str, Any] = {"conditions": conditions}
        if stats:
            plan_info["estimated_rows"] = stats.estimate_cardinality(conditions)
        else:
            plan_info["estimated_rows"] = 100  # fallback

        cost = self.cost_model.cost(plan_info, stats)

        # Penalty multipliers per query type
        qt = getattr(parsed_query, 'query_type', None)
        if qt is not None:
            qtv = qt.value if hasattr(qt, 'value') else str(qt)
            multipliers = {
                'SELECT': 1.0, 'INSERT': 0.6, 'UPDATE': 1.2,
                'DELETE': 0.8, 'QSEARCH': 2.0, 'QJOIN': 3.0,
                'QCOMPUTE': 2.5,
            }
            m = multipliers.get(qtv, 1.0)
            cost["gates"] = int(cost["gates"] * m)
            cost["depth"] = int(cost["depth"] * m)

        # JOIN cost bump
        jc = getattr(parsed_query, 'join_clauses', None)
        if jc:
            cost["gates"] += len(jc) * 50
            cost["depth"] += len(jc) * 10
            cost["qubits"] += len(jc) * 2

        return cost

    def collect_statistics(self, table_name: str, rows: List[Dict[str, Any]]) -> TableStatistics:
        return self.stats_collector.collect(table_name, rows)

    # ------------------------------------------------------------------
    # Legacy query-plan optimizer (dict-based)
    # ------------------------------------------------------------------

    def optimize_query_plan(self, query_plan: Dict[str, Any]) -> Dict[str, Any]:
        optimized = query_plan.copy()
        if 'circuits' in optimized:
            optimized['circuits'] = self._optimize_circuits(optimized['circuits'])
        if 'qubit_allocation' in optimized:
            optimized['qubit_allocation'] = self._optimize_qubit_allocation(
                optimized['qubit_allocation'], optimized.get('data_size', 0))
        if 'measurements' in optimized:
            optimized['measurements'] = self._optimize_measurements(optimized['measurements'])
        if 'operations' in optimized:
            optimized['operations'] = self._optimize_operation_order(optimized['operations'])
        try:
            if hasattr(cost_estimator, 'estimate_cost'):
                optimized['estimated_cost'] = cost_estimator.estimate_cost(optimized)
            else:
                optimized['estimated_cost'] = {
                    'qubits': optimized.get('qubit_allocation', {}).get('total_qubits', 10),
                    'gates': sum(c.get('gate_count', 100) for c in optimized.get('circuits', [])),
                    'depth': max((c.get('depth', 20) for c in optimized.get('circuits', [])), default=20),
                }
        except Exception as e:
            logger.warning("Cost estimation failed: %s", e)
            optimized['estimated_cost'] = {'qubits': 10, 'gates': 100, 'depth': 20}
        return optimized

    # -- internal helpers (kept from original) --

    def _optimize_circuits(self, circuits: List[Dict]) -> List[Dict]:
        out = []
        for circuit in circuits:
            opt = self.circuit_compiler.compile(circuit['definition'],
                                                optimization_level=self.optimization_level)
            if opt['depth'] > self.max_depth:
                opt = self._reduce_circuit_depth(opt)
            out.append({'id': circuit['id'], 'definition': opt['circuit'],
                        'depth': opt['depth'], 'gate_count': opt['gate_count']})
        return out

    def _reduce_circuit_depth(self, circuit: Dict) -> Dict:
        reduced = self.circuit_compiler.compile(circuit['circuit'],
                                                optimization_level=3,
                                                target_depth=self.max_depth)
        if reduced['depth'] > self.max_depth:
            reduced = self.circuit_compiler.cut_circuit(reduced['circuit'],
                                                        max_depth=self.max_depth)
        return reduced

    def _optimize_qubit_allocation(self, alloc: Dict, data_size: int) -> Dict:
        opt = alloc.copy()
        min_q = self._calculate_min_qubits(data_size)
        opt['total_qubits'] = max(min_q, alloc.get('total_qubits', 0))
        if 'index_qubits' in opt and 'data_qubits' in opt:
            total = opt['total_qubits']
            log_sz = (data_size.bit_length() - 1) if data_size > 0 else 0
            opt['index_qubits'] = max(log_sz, 1)
            opt['data_qubits'] = total - opt['index_qubits']
        return opt

    @staticmethod
    def _calculate_min_qubits(data_size: int) -> int:
        if data_size <= 0:
            return 2
        return max((data_size.bit_length() - 1) + 2, 2)

    def _optimize_measurements(self, meas: Dict) -> Dict:
        opt = meas.copy()
        if 'count' in opt:
            conf = opt.get('required_confidence', 0.95)
            opt['count'] = self._calculate_optimal_measurement_count(conf)
        if 'target_qubits' in opt:
            opt['target_qubits'] = self._identify_relevant_qubits(opt['target_qubits'])
        return opt

    @staticmethod
    def _calculate_optimal_measurement_count(confidence: float) -> int:
        if confidence >= 0.99:
            return 10000
        if confidence >= 0.95:
            return 5000
        if confidence >= 0.90:
            return 2000
        if confidence >= 0.80:
            return 1000
        return 500

    @staticmethod
    def _identify_relevant_qubits(target_qubits: List[int]) -> List[int]:
        return target_qubits

    def _optimize_operation_order(self, operations: List[Dict]) -> List[Dict]:
        independent = [op for op in operations if not op.get('dependencies')]
        dependent = [op for op in operations if op.get('dependencies')]
        dependent.sort(key=lambda x: len(x.get('dependencies', [])))
        parallelized = self._parallelize_operations(independent)
        return parallelized + dependent

    @staticmethod
    def _parallelize_operations(operations: List[Dict]) -> List[Dict]:
        parallelized: List[Dict] = []
        current_batch: List[Dict] = []
        current_qubits: set = set()
        for op in operations:
            op_q = set(op.get('qubits', []))
            if not op_q.intersection(current_qubits):
                current_batch.append(op)
                current_qubits.update(op_q)
            else:
                if current_batch:
                    parallelized.append({'type': 'parallel_batch',
                                         'operations': current_batch,
                                         'qubits': list(current_qubits)})
                current_batch = [op]
                current_qubits = op_q
        if current_batch:
            parallelized.append({'type': 'parallel_batch',
                                 'operations': current_batch,
                                 'qubits': list(current_qubits)})
        return parallelized
