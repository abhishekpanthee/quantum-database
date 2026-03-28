"""
Enterprise Features — Columnar Storage, Window Functions, Admin
================================================================

Demonstrates the Phase 8 enterprise modules: columnar storage,
window functions, CTEs, admin monitoring, and integrations.
"""

from qndb.enterprise import (
    ColumnarStorage,
    QuantumDataType,
    PartitionManager,
    TieredStorageManager,
    WindowFunction,
    CTEResolver,
    UDQFRegistry,
    StoredProcedure,
    QuantumFullTextSearch,
    AdminConsole,
    QueryPerformanceMonitor,
    SlowQueryLog,
    AlertManager,
    MetricsExporter,
)


def columnar_storage_demo():
    """Columnar storage with partitioning and tiered storage."""
    print("=== Columnar Storage ===\n")

    store = ColumnarStorage()
    store.create_table("events", {
        "ts": "timestamp",
        "value": "float",
        "tag": "text",
        "sensor_id": "int",
    })

    # Insert data
    for i in range(10):
        store.insert("events", {
            "ts": 1700000000 + i * 60,
            "value": 20.0 + i * 0.5,
            "tag": f"sensor-{i % 3}",
            "sensor_id": i % 3,
        })
    print(f"Inserted 10 rows into 'events'")

    # Columnar scan
    results = store.scan("events", columns=["ts", "value"], limit=5)
    print(f"Scan (first 5 rows): {results}")

    # Partitioning
    pm = PartitionManager()
    pm.create_partition("events", key="sensor_id", strategy="hash", num_partitions=3)
    info = pm.partition_info("events")
    print(f"Partitions: {info}")

    # Tiered storage
    tsm = TieredStorageManager()
    tsm.configure_tiers({
        "hot": {"max_age_hours": 24, "storage": "memory"},
        "warm": {"max_age_hours": 168, "storage": "ssd"},
        "cold": {"max_age_hours": None, "storage": "object_store"},
    })
    tier = tsm.classify_age(hours=100)
    print(f"100-hour-old data -> tier: {tier}")


def query_features_demo():
    """Window functions, CTEs, stored procedures, FTS."""
    print("\n=== Query Features ===\n")

    # Window functions
    wf = WindowFunction()
    data = [10, 20, 30, 40, 50, 60, 70]
    avg = wf.evaluate(data, function="moving_avg", window_size=3)
    print(f"Moving average (window=3): {avg}")

    rank = wf.evaluate(data, function="rank")
    print(f"Rank: {rank}")

    # CTE (Common Table Expressions)
    cte = CTEResolver()
    cte.define("high_values", "SELECT * FROM events WHERE value > 22.0")
    cte.define("tagged", "SELECT * FROM high_values WHERE tag = 'sensor-1'")
    plan = cte.resolve("tagged")
    print(f"CTE resolution plan: {plan}")

    # UDQFs (User-Defined Quantum Functions)
    registry = UDQFRegistry()
    registry.register(
        name="quantum_avg",
        num_qubits=4,
        circuit_template="amplitude_estimation",
        description="Quantum amplitude estimation for average",
    )
    print(f"Registered UDQFs: {registry.list_functions()}")

    # Stored procedures
    proc = StoredProcedure(
        name="cleanup_old_events",
        body="DELETE FROM events WHERE ts < :cutoff",
        params={"cutoff": "timestamp"},
    )
    print(f"Stored procedure: {proc.name} (params: {list(proc.params.keys())})")

    # Full-text search
    fts = QuantumFullTextSearch()
    fts.index_document("doc1", "Quantum database with Grover search")
    fts.index_document("doc2", "Classical relational database system")
    hits = fts.search("quantum Grover")
    print(f"FTS results: {hits}")


def admin_demo():
    """Admin console, monitoring, alerts."""
    print("\n=== Administration ===\n")

    console = AdminConsole()
    console.register_node("node-1", {"host": "10.0.0.1", "qubits": 72, "status": "online"})
    console.register_node("node-2", {"host": "10.0.0.2", "qubits": 54, "status": "online"})
    health = console.cluster_health()
    print(f"Cluster health: {health}")

    # Query performance monitor
    monitor = QueryPerformanceMonitor()
    monitor.record_query("SELECT * FROM events", duration_ms=45.2, qubits_used=8)
    monitor.record_query("INSERT INTO events ...", duration_ms=12.1, qubits_used=4)
    stats = monitor.summary()
    print(f"Query stats: {stats}")

    # Slow query log
    slow_log = SlowQueryLog(threshold_ms=30.0)
    slow_log.record("SELECT * FROM events", duration_ms=45.2)
    slow_log.record("INSERT INTO events ...", duration_ms=12.1)
    slow = slow_log.get_slow_queries()
    print(f"Slow queries: {len(slow)} found")

    # Alerts
    alerts = AlertManager()
    alerts.add_rule("high_latency", condition="avg_query_ms > 100", action="email")
    alerts.add_rule("low_qubits", condition="available_qubits < 10", action="slack")
    print(f"Alert rules: {alerts.list_rules()}")

    # Metrics export
    exporter = MetricsExporter(format="prometheus")
    metrics = exporter.collect()
    print(f"Exported {len(metrics)} metrics")


def main():
    columnar_storage_demo()
    query_features_demo()
    admin_demo()


if __name__ == "__main__":
    main()
