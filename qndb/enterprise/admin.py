"""
Administration — Enterprise Admin & Monitoring
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **AdminConsole** — Web-based admin console (programmatic API)
* **QueryPerformanceMonitor** — Real-time query performance monitoring
* **SlowQueryLog** — Slow-query log with automatic indexing suggestions
* **StorageAnalytics** — Storage analytics and capacity planning
* **QuantumResourceDashboard** — Quantum resource usage dashboards
* **AlertManager** — Alert system for hardware errors, latency, exhaustion
"""

import logging
import statistics
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ======================================================================
# Query Performance Monitor
# ======================================================================

class QueryPerformanceMonitor:
    """Real-time query performance monitoring.

    Records per-query metrics (latency, circuit depth, shots, success)
    and exposes aggregate statistics for dashboards.

    Args:
        window_seconds: Rolling-window size for live stats.
        max_history: Maximum metric entries retained.
    """

    def __init__(self, window_seconds: float = 300, max_history: int = 50_000) -> None:
        self._history: Deque[Dict[str, Any]] = deque(maxlen=max_history)
        self._lock = threading.RLock()
        self._window = window_seconds

    def record(
        self,
        query_id: str,
        execution_time_ms: float,
        circuit_depth: int = 0,
        num_shots: int = 0,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "query_id": query_id,
            "execution_time_ms": execution_time_ms,
            "circuit_depth": circuit_depth,
            "num_shots": num_shots,
            "success": success,
            "timestamp": time.time(),
            **(metadata or {}),
        }
        with self._lock:
            self._history.append(entry)

    def live_stats(self) -> Dict[str, Any]:
        """Aggregate stats over the rolling window."""
        now = time.time()
        with self._lock:
            window = [e for e in self._history if now - e["timestamp"] <= self._window]
        if not window:
            return {"window_seconds": self._window, "query_count": 0}

        latencies = [e["execution_time_ms"] for e in window]
        successes = [e for e in window if e["success"]]
        return {
            "window_seconds": self._window,
            "query_count": len(window),
            "success_rate": len(successes) / len(window),
            "avg_latency_ms": statistics.mean(latencies),
            "p50_latency_ms": statistics.median(latencies),
            "p95_latency_ms": sorted(latencies)[int(0.95 * len(latencies))] if len(latencies) >= 2 else latencies[0],
            "p99_latency_ms": sorted(latencies)[int(0.99 * len(latencies))] if len(latencies) >= 2 else latencies[0],
            "max_latency_ms": max(latencies),
            "avg_circuit_depth": statistics.mean([e["circuit_depth"] for e in window]),
            "total_shots": sum(e["num_shots"] for e in window),
        }

    def recent_queries(self, n: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history)[-n:]

    def reset(self) -> None:
        with self._lock:
            self._history.clear()


# ======================================================================
# Slow Query Log
# ======================================================================

class SlowQueryLog:
    """Slow-query log with automatic indexing suggestions.

    Any query whose execution time exceeds *threshold_ms* is logged.
    The log also analyses access patterns and suggests which columns
    would benefit from quantum indexing.

    Args:
        threshold_ms: Queries slower than this are recorded.
        max_entries: Maximum log size.
    """

    def __init__(self, threshold_ms: float = 1000, max_entries: int = 10_000) -> None:
        self._log: Deque[Dict[str, Any]] = deque(maxlen=max_entries)
        self._threshold = threshold_ms
        self._column_access: Dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()

    def check_and_log(
        self,
        query_text: str,
        execution_time_ms: float,
        accessed_columns: Optional[List[str]] = None,
        plan_info: Optional[Dict] = None,
    ) -> bool:
        """Log the query if it exceeds the threshold.

        Returns:
            ``True`` if logged (slow), ``False`` otherwise.
        """
        if execution_time_ms < self._threshold:
            return False

        with self._lock:
            self._log.append({
                "query": query_text,
                "execution_time_ms": execution_time_ms,
                "accessed_columns": accessed_columns or [],
                "plan_info": plan_info,
                "timestamp": datetime.now().isoformat(),
            })
            for col in (accessed_columns or []):
                self._column_access[col] += 1

        logger.warning("Slow query (%.1fms): %s", execution_time_ms, query_text[:200])
        return True

    def suggest_indexes(self, top_n: int = 5) -> List[Dict[str, Any]]:
        """Suggest columns for indexing based on slow-query patterns.

        Returns:
            List of ``{column, frequency, suggestion}`` dicts.
        """
        with self._lock:
            sorted_cols = sorted(self._column_access.items(), key=lambda x: -x[1])
        suggestions = []
        for col, freq in sorted_cols[:top_n]:
            suggestions.append({
                "column": col,
                "slow_query_frequency": freq,
                "suggestion": f"Create quantum index on '{col}' (referenced in {freq} slow queries)",
            })
        return suggestions

    def entries(self, n: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._log)
        return items[-n:] if n else items

    def clear(self) -> None:
        with self._lock:
            self._log.clear()
            self._column_access.clear()


# ======================================================================
# Storage Analytics
# ======================================================================

class StorageAnalytics:
    """Storage analytics and capacity planning.

    Tracks table sizes, growth rates, and projects when capacity
    thresholds will be reached.
    """

    def __init__(self) -> None:
        self._snapshots: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._lock = threading.RLock()

    def record_snapshot(
        self,
        table_name: str,
        row_count: int,
        size_bytes: int,
        num_qubits_used: int = 0,
    ) -> None:
        with self._lock:
            self._snapshots[table_name].append({
                "row_count": row_count,
                "size_bytes": size_bytes,
                "num_qubits_used": num_qubits_used,
                "timestamp": time.time(),
            })

    def growth_rate(self, table_name: str) -> Optional[float]:
        """Return bytes-per-second growth rate (linear regression)."""
        with self._lock:
            snaps = self._snapshots.get(table_name, [])
        if len(snaps) < 2:
            return None
        t0, s0 = snaps[0]["timestamp"], snaps[0]["size_bytes"]
        t1, s1 = snaps[-1]["timestamp"], snaps[-1]["size_bytes"]
        dt = t1 - t0
        return (s1 - s0) / dt if dt > 0 else 0.0

    def capacity_projection(
        self, table_name: str, capacity_bytes: int,
    ) -> Optional[float]:
        """Estimate seconds until *capacity_bytes* is reached.

        Returns:
            Seconds remaining, or *None* if not enough data.
        """
        rate = self.growth_rate(table_name)
        if rate is None or rate <= 0:
            return None
        with self._lock:
            current = self._snapshots[table_name][-1]["size_bytes"]
        remaining = capacity_bytes - current
        return remaining / rate if remaining > 0 else 0.0

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            tables = {}
            for tname, snaps in self._snapshots.items():
                latest = snaps[-1] if snaps else {}
                tables[tname] = {
                    "row_count": latest.get("row_count", 0),
                    "size_bytes": latest.get("size_bytes", 0),
                    "num_qubits_used": latest.get("num_qubits_used", 0),
                    "snapshots": len(snaps),
                    "growth_rate_bps": self.growth_rate(tname),
                }
            return {"tables": tables, "total_tables": len(tables)}


# ======================================================================
# Quantum Resource Dashboard
# ======================================================================

class QuantumResourceDashboard:
    """Quantum resource usage dashboard.

    Collects and exposes qubit utilisation, circuit depth budgets,
    shot budgets, and hardware error rates for operational monitoring.
    """

    def __init__(self, max_qubits: int = 127, shot_budget: int = 1_000_000) -> None:
        self._max_qubits = max_qubits
        self._shot_budget = shot_budget
        self._qubits_in_use = 0
        self._shots_consumed = 0
        self._circuit_executions = 0
        self._errors: Deque[Dict[str, Any]] = deque(maxlen=1000)
        self._lock = threading.RLock()

    def allocate_qubits(self, n: int) -> bool:
        """Try to allocate *n* qubits. Returns ``False`` if over budget."""
        with self._lock:
            if self._qubits_in_use + n > self._max_qubits:
                return False
            self._qubits_in_use += n
            return True

    def release_qubits(self, n: int) -> None:
        with self._lock:
            self._qubits_in_use = max(0, self._qubits_in_use - n)

    def consume_shots(self, n: int) -> None:
        with self._lock:
            self._shots_consumed += n
            self._circuit_executions += 1

    def record_error(self, error_type: str, details: str = "") -> None:
        with self._lock:
            self._errors.append({
                "type": error_type,
                "details": details,
                "timestamp": datetime.now().isoformat(),
            })

    def dashboard(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "qubits_in_use": self._qubits_in_use,
                "max_qubits": self._max_qubits,
                "qubit_utilisation": self._qubits_in_use / self._max_qubits if self._max_qubits else 0,
                "shots_consumed": self._shots_consumed,
                "shot_budget": self._shot_budget,
                "shots_remaining": max(0, self._shot_budget - self._shots_consumed),
                "circuit_executions": self._circuit_executions,
                "recent_errors": list(self._errors)[-10:],
                "error_count": len(self._errors),
            }

    def reset_budget(self, shot_budget: Optional[int] = None) -> None:
        with self._lock:
            self._shots_consumed = 0
            if shot_budget is not None:
                self._shot_budget = shot_budget


# ======================================================================
# Alert Manager
# ======================================================================

class AlertManager:
    """Alert system for hardware errors, high latency, and resource exhaustion.

    Supports configurable rules with thresholds, cooldown periods,
    and pluggable notification callbacks.
    """

    class Severity(Enum):
        INFO = auto()
        WARNING = auto()
        CRITICAL = auto()

    def __init__(self) -> None:
        self._rules: Dict[str, Dict[str, Any]] = {}
        self._fired: Deque[Dict[str, Any]] = deque(maxlen=10_000)
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._cooldowns: Dict[str, float] = {}
        self._lock = threading.RLock()

    def add_rule(
        self,
        name: str,
        condition: Callable[[Dict[str, Any]], bool],
        severity: "AlertManager.Severity" = None,
        cooldown_seconds: float = 60,
        message_template: str = "Alert: {name}",
    ) -> None:
        """Register an alert rule.

        Args:
            name: Unique rule name.
            condition: Callable accepting a metrics dict; returns
                ``True`` to fire the alert.
            severity: Alert severity.
            cooldown_seconds: Minimum seconds between firings.
            message_template: f-string template with ``{name}`` placeholder.
        """
        severity = severity or self.Severity.WARNING
        with self._lock:
            self._rules[name] = {
                "condition": condition,
                "severity": severity,
                "cooldown": cooldown_seconds,
                "message": message_template,
            }

    def add_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a notification callback (email, Slack, PagerDuty, …)."""
        with self._lock:
            self._callbacks.append(callback)

    def evaluate(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate all rules against *metrics*.

        Returns:
            List of fired alert dicts.
        """
        fired = []
        now = time.time()
        with self._lock:
            for name, rule in self._rules.items():
                if now - self._cooldowns.get(name, 0) < rule["cooldown"]:
                    continue
                try:
                    if rule["condition"](metrics):
                        alert = {
                            "rule": name,
                            "severity": rule["severity"].name,
                            "message": rule["message"].format(name=name),
                            "timestamp": datetime.now().isoformat(),
                            "metrics_snapshot": dict(metrics),
                        }
                        self._fired.append(alert)
                        self._cooldowns[name] = now
                        fired.append(alert)
                        for cb in self._callbacks:
                            try:
                                cb(alert)
                            except Exception as exc:
                                logger.error("Alert callback failed: %s", exc)
                except Exception as exc:
                    logger.error("Alert rule '%s' evaluation failed: %s", name, exc)
        return fired

    def recent_alerts(self, n: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._fired)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._fired.clear()
            self._cooldowns.clear()


# ======================================================================
# Admin Console
# ======================================================================

class AdminConsole:
    """Programmatic admin console aggregating all monitoring components.

    Provides a single entry-point for dashboards, slow-query analysis,
    storage health, and alerting.

    Args:
        performance_monitor: Optional shared monitor instance.
        slow_query_log: Optional shared slow-query log.
        storage_analytics: Optional shared analytics instance.
        resource_dashboard: Optional shared resource dashboard.
        alert_manager: Optional shared alert manager.
    """

    def __init__(
        self,
        performance_monitor: Optional[QueryPerformanceMonitor] = None,
        slow_query_log: Optional[SlowQueryLog] = None,
        storage_analytics: Optional[StorageAnalytics] = None,
        resource_dashboard: Optional[QuantumResourceDashboard] = None,
        alert_manager: Optional[AlertManager] = None,
    ) -> None:
        self.monitor = performance_monitor or QueryPerformanceMonitor()
        self.slow_log = slow_query_log or SlowQueryLog()
        self.storage = storage_analytics or StorageAnalytics()
        self.resources = resource_dashboard or QuantumResourceDashboard()
        self.alerts = alert_manager or AlertManager()

    def health_check(self) -> Dict[str, Any]:
        """Return a full system health snapshot."""
        perf = self.monitor.live_stats()
        res = self.resources.dashboard()
        return {
            "status": "healthy" if perf.get("success_rate", 1.0) >= 0.95 else "degraded",
            "performance": perf,
            "resources": res,
            "storage": self.storage.summary(),
            "slow_queries": len(self.slow_log.entries()),
            "recent_alerts": self.alerts.recent_alerts(5),
            "timestamp": datetime.now().isoformat(),
        }

    def run_diagnostics(self) -> Dict[str, Any]:
        """Run a diagnostic sweep and fire any pending alerts."""
        metrics = {
            **self.monitor.live_stats(),
            **self.resources.dashboard(),
        }
        fired = self.alerts.evaluate(metrics)
        suggestions = self.slow_log.suggest_indexes()
        return {
            "alerts_fired": fired,
            "index_suggestions": suggestions,
            "diagnostics_time": datetime.now().isoformat(),
        }
