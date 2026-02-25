"""Statistics and cardinality estimation."""

from typing import Dict, List, Any, Optional


class ColumnHistogram:
    """Equi-width histogram for a single column."""

    def __init__(self, num_buckets: int = 64):
        self.num_buckets = num_buckets
        self.buckets: List[int] = []
        self.min_val: Optional[float] = None
        self.max_val: Optional[float] = None
        self.ndv: int = 0  # number of distinct values
        self.null_count: int = 0
        self.total: int = 0

    def build(self, values: List[Any]) -> None:
        nums = []
        distinct = set()
        for v in values:
            self.total += 1
            if v is None:
                self.null_count += 1
                continue
            distinct.add(v)
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
                nums.append(hash(v) % 1_000_000)
        self.ndv = len(distinct)
        if not nums:
            self.buckets = [0] * self.num_buckets
            return
        self.min_val = min(nums)
        self.max_val = max(nums)
        width = (self.max_val - self.min_val) / self.num_buckets if self.max_val != self.min_val else 1.0
        self.buckets = [0] * self.num_buckets
        for n in nums:
            idx = min(int((n - self.min_val) / width), self.num_buckets - 1)
            self.buckets[idx] += 1

    def selectivity(self, op: str, value: Any) -> float:
        """Estimate fraction of rows satisfying ``column <op> value``."""
        if self.total == 0:
            return 0.5
        try:
            v = float(value)
        except (TypeError, ValueError):
            v = hash(value) % 1_000_000
        if self.min_val is None or self.max_val is None:
            return 0.5
        if op == '=':
            return 1.0 / max(self.ndv, 1)
        rng = self.max_val - self.min_val if self.max_val != self.min_val else 1.0
        frac = (v - self.min_val) / rng
        frac = max(0.0, min(1.0, frac))
        if op in ('<', '<='):
            return frac
        if op in ('>', '>='):
            return 1.0 - frac
        if op == '!=':
            return 1.0 - 1.0 / max(self.ndv, 1)
        return 0.5


class TableStatistics:
    """Statistics for a single table (row count + per-column histograms)."""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self.row_count: int = 0
        self.columns: Dict[str, ColumnHistogram] = {}

    def collect(self, rows: List[Dict[str, Any]]) -> None:
        self.row_count = len(rows)
        if not rows:
            return
        col_names = set()
        for r in rows:
            col_names.update(r.keys())
        for col in col_names:
            h = ColumnHistogram()
            h.build([r.get(col) for r in rows])
            self.columns[col] = h

    def estimate_cardinality(self, conditions: Optional[List[Dict[str, Any]]]) -> float:
        """Estimate output cardinality given flat conditions list."""
        if not conditions:
            return float(self.row_count)
        sel = 1.0
        for cond in conditions:
            ctype = cond.get("type", "comparison")
            field = cond.get("field", "")
            hist = self.columns.get(field)
            if hist is None:
                sel *= 0.5
                continue
            if ctype == "comparison":
                sel *= hist.selectivity(cond.get("operator", "="), cond.get("value"))
            elif ctype == "in":
                sel *= min(len(cond.get("values", [])) / max(hist.ndv, 1), 1.0)
            elif ctype == "between":
                low_sel = hist.selectivity(">=", cond.get("low"))
                high_sel = hist.selectivity("<=", cond.get("high"))
                sel *= max(low_sel + high_sel - 1.0, 0.01)
            elif ctype == "like":
                sel *= 0.1  # rough default
            else:
                sel *= 0.5
        return max(self.row_count * sel, 1.0)


class StatisticsCollector:
    """Manages per-table statistics across the database."""

    def __init__(self):
        self._stats: Dict[str, TableStatistics] = {}

    def collect(self, table_name: str, rows: List[Dict[str, Any]]) -> TableStatistics:
        ts = TableStatistics(table_name)
        ts.collect(rows)
        self._stats[table_name] = ts
        return ts

    def get(self, table_name: str) -> Optional[TableStatistics]:
        return self._stats.get(table_name)
