import unittest
import os
import shutil
import tempfile
import time
import logging
import sys
import numpy as np
import cirq

from qndb.enterprise.storage import (
    ColumnarStorage,
    QuantumDataType,
    QuantumColumnCompressor,
    MaterializedViewManager,
    PartitionManager,
    TieredStorageManager,
)
from qndb.enterprise.query import (
    WindowFunction,
    CTEResolver,
    UDQFRegistry,
    StoredProcedure,
    ViewManager,
    QuantumFullTextSearch,
    QuantumGeospatialIndex,
)
from qndb.enterprise.admin import (
    AdminConsole,
    QueryPerformanceMonitor,
    SlowQueryLog,
    StorageAnalytics,
    QuantumResourceDashboard,
    AlertManager,
)
from qndb.enterprise.integration import (
    JDBCODBCAdapter,
    SQLAlchemyDialect,
    ArrowFlightServer,
    KafkaConnector,
    GraphQLLayer,
    MetricsExporter,
    TracingProvider,
)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# =====================================================================
# 8.1  Advanced Storage
# =====================================================================

class TestColumnarStorage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cs = ColumnarStorage(storage_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_and_insert(self):
        self.cs.create_table("users", {
            "id": QuantumDataType.CLASSICAL_INT,
            "name": QuantumDataType.CLASSICAL_STRING,
        })
        n = self.cs.insert_rows("users", [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ])
        self.assertEqual(n, 2)

    def test_read_column(self):
        self.cs.create_table("t", {"a": QuantumDataType.CLASSICAL_INT})
        self.cs.insert_rows("t", [{"a": 10}, {"a": 20}])
        col = self.cs.read_column("t", "a")
        self.assertEqual(col, [10, 20])

    def test_scan_rows(self):
        self.cs.create_table("t", {"x": QuantumDataType.CLASSICAL_FLOAT})
        self.cs.insert_rows("t", [{"x": 1.5}, {"x": 2.5}, {"x": 3.5}])
        rows = self.cs.scan_rows("t", limit=2)
        self.assertEqual(len(rows), 2)

    def test_duplicate_table_raises(self):
        self.cs.create_table("t", {"a": QuantumDataType.CLASSICAL_INT})
        with self.assertRaises(ValueError):
            self.cs.create_table("t", {"a": QuantumDataType.CLASSICAL_INT})

    def test_drop_table(self):
        self.cs.create_table("t", {"a": QuantumDataType.CLASSICAL_INT})
        self.cs.drop_table("t")
        with self.assertRaises(KeyError):
            self.cs.read_column("t", "a")

    def test_table_info(self):
        self.cs.create_table("t", {"a": QuantumDataType.CLASSICAL_INT})
        self.cs.insert_rows("t", [{"a": 1}])
        info = self.cs.table_info("t")
        self.assertEqual(info["row_count"], 1)

    def test_store_superposition(self):
        self.cs.create_table("q", {"sv": QuantumDataType.SUPERPOSITION})
        amps = np.array([0.5, 0.5, 0.5, 0.5])
        self.cs.store_superposition("q", "sv", amps)

    def test_store_entangled_row(self):
        self.cs.create_table("e", {"ent": QuantumDataType.ENTANGLED})
        self.cs.store_entangled_row("e", np.array([1, 0, 0, 0]))


class TestQuantumColumnCompressor(unittest.TestCase):
    def setUp(self):
        self.comp = QuantumColumnCompressor()

    def test_compress_decompress(self):
        data = [1.0, 2.0, 3.0, 4.0]
        compressed = self.comp.compress(data)
        self.assertIn("compression_ratio", compressed)
        self.assertGreater(compressed["compression_ratio"], 1.0)
        restored = self.comp.decompress(compressed)
        np.testing.assert_allclose(restored, data, atol=1e-10)

    def test_single_value(self):
        compressed = self.comp.compress([42.0])
        self.assertEqual(compressed["original_length"], 1)


class TestMaterializedViewManager(unittest.TestCase):
    def setUp(self):
        self.mvm = MaterializedViewManager(cache_ttl=2)

    def test_create_and_get(self):
        self.mvm.create_view("v1", "SELECT * FROM t", ["t"], result=[1, 2, 3])
        self.assertEqual(self.mvm.get_result("v1"), [1, 2, 3])

    def test_stale_returns_none(self):
        self.mvm.create_view("v1", "q", ["t"], result="ok")
        time.sleep(2.1)
        self.assertIsNone(self.mvm.get_result("v1"))

    def test_refresh(self):
        self.mvm.create_view("v1", "q", ["t"], result="old")
        self.mvm.refresh("v1", "new")
        self.assertEqual(self.mvm.get_result("v1"), "new")

    def test_invalidate_by_table(self):
        self.mvm.create_view("v1", "q", ["t1", "t2"], result="data")
        invalidated = self.mvm.invalidate_by_table("t1")
        self.assertIn("v1", invalidated)
        self.assertIsNone(self.mvm.get_result("v1"))

    def test_list_views(self):
        self.mvm.create_view("v1", "q", ["t"])
        views = self.mvm.list_views()
        self.assertEqual(len(views), 1)


class TestPartitionManager(unittest.TestCase):
    def setUp(self):
        self.pm = PartitionManager()

    def test_hash_partition(self):
        self.pm.create_partition("t", PartitionManager.Strategy.HASH, "id", 4)
        bucket = self.pm.assign_partition("t", {"id": "abc"})
        self.assertIn(bucket, range(4))

    def test_partition_stats(self):
        self.pm.create_partition("t", PartitionManager.Strategy.HASH, "id", 2)
        self.pm.assign_partition("t", {"id": "x"})
        stats = self.pm.partition_stats("t")
        self.assertEqual(stats["num_partitions"], 2)

    def test_get_partition_data(self):
        self.pm.create_partition("t", PartitionManager.Strategy.HASH, "id", 4)
        bucket = self.pm.assign_partition("t", {"id": "test", "val": 42})
        data = self.pm.get_partition_data("t", bucket)
        self.assertEqual(len(data), 1)

    def test_prune_partitions(self):
        self.pm.create_partition("t", PartitionManager.Strategy.TIME, "ts", 4)
        pruned = self.pm.prune_partitions("t", lambda i: i < 2)
        self.assertEqual(pruned, [0, 1])


class TestTieredStorageManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tsm = TieredStorageManager(
            hot_capacity=2, warm_capacity=3, cold_dir=self.tmpdir,
            demote_seconds=0.5,
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_put_and_get(self):
        self.tsm.put("k1", "v1")
        self.assertEqual(self.tsm.get("k1"), "v1")

    def test_hot_eviction(self):
        self.tsm.put("a", 1, TieredStorageManager.Tier.HOT)
        self.tsm.put("b", 2, TieredStorageManager.Tier.HOT)
        self.tsm.put("c", 3, TieredStorageManager.Tier.HOT)  # evicts "a" to warm
        stats = self.tsm.tier_stats()
        self.assertEqual(stats["hot_count"], 2)

    def test_cold_storage(self):
        self.tsm.put("cold_key", "cold_val", TieredStorageManager.Tier.COLD)
        val = self.tsm.get("cold_key")
        self.assertEqual(val, "cold_val")

    def test_demote_stale(self):
        self.tsm.put("stale", "val", TieredStorageManager.Tier.HOT)
        time.sleep(0.6)
        demoted = self.tsm.demote_stale()
        self.assertGreaterEqual(demoted, 1)

    def test_tier_stats(self):
        stats = self.tsm.tier_stats()
        self.assertIn("hot_count", stats)
        self.assertIn("warm_count", stats)


# =====================================================================
# 8.2  Advanced Query Features
# =====================================================================

class TestWindowFunction(unittest.TestCase):
    def setUp(self):
        self.wf = WindowFunction()
        self.rows = [
            {"dept": "A", "salary": 100, "name": "x"},
            {"dept": "A", "salary": 200, "name": "y"},
            {"dept": "B", "salary": 150, "name": "z"},
            {"dept": "B", "salary": 150, "name": "w"},
        ]

    def test_row_number(self):
        result = self.wf.apply(self.rows, WindowFunction.Func.ROW_NUMBER,
                               partition_by=["dept"], order_by="salary")
        nums = [r["_window"] for r in result]
        self.assertEqual(nums, [1, 2, 1, 2])

    def test_sum(self):
        result = self.wf.apply(self.rows, WindowFunction.Func.SUM,
                               value_column="salary", partition_by=["dept"])
        sums = [r["_window"] for r in result]
        self.assertEqual(sums, [300, 300, 300, 300])

    def test_rank(self):
        result = self.wf.apply(self.rows, WindowFunction.Func.RANK,
                               partition_by=["dept"], order_by="salary")
        ranks = [r["_window"] for r in result]
        self.assertEqual(ranks[0], 1)

    def test_lag(self):
        result = self.wf.apply(self.rows[:2], WindowFunction.Func.LAG,
                               value_column="salary", order_by="salary")
        self.assertIsNone(result[0]["_window"])
        self.assertEqual(result[1]["_window"], 100)


class TestCTEResolver(unittest.TestCase):
    def setUp(self):
        self.cte = CTEResolver()

    def test_simple_resolve(self):
        self.cte.register("a", lambda ctx: [{"x": 1}])
        self.cte.register("b", lambda ctx: [{"y": r["x"] + 1} for r in ctx["a"]])
        result = self.cte.resolve(["a", "b"])
        self.assertEqual(result["b"], [{"y": 2}])

    def test_recursive(self):
        result = self.cte.resolve_recursive(
            "nums",
            seed=lambda: [{"n": 1}],
            step=lambda rows: [{"n": rows[-1]["n"] + 1}] if rows[-1]["n"] < 5 else [],
        )
        self.assertEqual(len(result), 5)

    def test_missing_cte_raises(self):
        with self.assertRaises(KeyError):
            self.cte.resolve(["nonexistent"])


class TestUDQFRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = UDQFRegistry()

    def test_register_and_invoke(self):
        def builder(n=2):
            q = [cirq.LineQubit(i) for i in range(n)]
            return cirq.Circuit(cirq.H.on_each(*q), cirq.measure(*q, key="m"))

        self.reg.register("hadamard_test", builder,
                          post_processor=lambda m: int(m["m"].sum()),
                          param_names=["n"])
        result = self.reg.invoke("hadamard_test", {"n": 2}, repetitions=100)
        self.assertIsInstance(result, (int, np.integer))

    def test_list_functions(self):
        self.reg.register("f1", lambda: cirq.Circuit(), lambda m: 0)
        fns = self.reg.list_functions()
        self.assertEqual(len(fns), 1)

    def test_unregister(self):
        self.reg.register("f1", lambda: cirq.Circuit(), lambda m: 0)
        self.reg.unregister("f1")
        with self.assertRaises(KeyError):
            self.reg.invoke("f1")


class TestStoredProcedure(unittest.TestCase):
    def setUp(self):
        self.sp = StoredProcedure()

    def test_create_and_call(self):
        self.sp.create("add", body=lambda a, b: a + b, param_names=["a", "b"])
        result = self.sp.call("add", a=3, b=4)
        self.assertEqual(result, 7)

    def test_drop(self):
        self.sp.create("f", body=lambda: 1)
        self.sp.drop("f")
        with self.assertRaises(KeyError):
            self.sp.call("f")

    def test_list_procedures(self):
        self.sp.create("p1", body=lambda: None)
        procs = self.sp.list_procedures()
        self.assertEqual(len(procs), 1)


class TestViewManager(unittest.TestCase):
    def setUp(self):
        self.vm = ViewManager()

    def test_create_and_resolve(self):
        self.vm.create_view("active_users", "SELECT * FROM users WHERE active = 1")
        q = self.vm.resolve("active_users")
        self.assertIn("SELECT", q)

    def test_rewrite_query(self):
        self.vm.create_view("v1", "SELECT id FROM t1")
        rewritten = self.vm.rewrite_query("SELECT * FROM v1 WHERE id > 5")
        self.assertIn("(SELECT id FROM t1) AS v1", rewritten)

    def test_drop_view(self):
        self.vm.create_view("v1", "SELECT 1")
        self.vm.drop_view("v1")
        with self.assertRaises(KeyError):
            self.vm.resolve("v1")


class TestQuantumFullTextSearch(unittest.TestCase):
    def setUp(self):
        self.fts = QuantumFullTextSearch(num_index_qubits=4)

    def test_add_and_search_classical(self):
        self.fts.add_document("hello world quantum")
        self.fts.add_document("quantum database engine")
        self.fts.add_document("classical sql database")
        results = self.fts.search_classical("quantum database")
        self.assertIn(1, results)

    def test_search_quantum(self):
        for i in range(8):
            self.fts.add_document(f"filler document {i}")
        self.fts.add_document("alpha beta gamma")
        self.fts.add_document("delta epsilon gamma")
        results = self.fts.search_quantum("gamma", repetitions=1000)
        self.assertGreater(len(results), 0)

    def test_get_document(self):
        did = self.fts.add_document("test doc")
        self.assertEqual(self.fts.get_document(did), "test doc")


class TestQuantumGeospatialIndex(unittest.TestCase):
    def setUp(self):
        self.geo = QuantumGeospatialIndex(num_qubits=3)

    def test_insert_and_bbox(self):
        self.geo.insert_point(40.0, -74.0)
        self.geo.insert_point(41.0, -73.0)
        self.geo.insert_point(35.0, -80.0)
        results = self.geo.bounding_box_search(39.0, 42.0, -75.0, -72.0)
        self.assertEqual(len(results), 2)

    def test_nearest_quantum(self):
        self.geo.insert_point(10.0, 20.0)
        self.geo.insert_point(10.1, 20.1)
        self.geo.insert_point(50.0, 50.0)
        results = self.geo.nearest_quantum(10.0, 20.0, k=1, repetitions=100)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0][0], 0)  # closest is point 0


# =====================================================================
# 8.3  Administration
# =====================================================================

class TestQueryPerformanceMonitor(unittest.TestCase):
    def setUp(self):
        self.mon = QueryPerformanceMonitor(window_seconds=10)

    def test_record_and_stats(self):
        self.mon.record("q1", 50.0, circuit_depth=10, num_shots=100)
        self.mon.record("q2", 150.0, circuit_depth=20, num_shots=200, success=False)
        stats = self.mon.live_stats()
        self.assertEqual(stats["query_count"], 2)
        self.assertEqual(stats["success_rate"], 0.5)

    def test_recent_queries(self):
        self.mon.record("q1", 10.0)
        recent = self.mon.recent_queries(5)
        self.assertEqual(len(recent), 1)

    def test_reset(self):
        self.mon.record("q1", 10.0)
        self.mon.reset()
        stats = self.mon.live_stats()
        self.assertEqual(stats["query_count"], 0)


class TestSlowQueryLog(unittest.TestCase):
    def setUp(self):
        self.sql = SlowQueryLog(threshold_ms=100)

    def test_log_slow_query(self):
        logged = self.sql.check_and_log("SELECT *", 200, accessed_columns=["col_a"])
        self.assertTrue(logged)

    def test_fast_query_not_logged(self):
        logged = self.sql.check_and_log("SELECT 1", 10)
        self.assertFalse(logged)

    def test_suggest_indexes(self):
        self.sql.check_and_log("q1", 500, accessed_columns=["x", "y"])
        self.sql.check_and_log("q2", 600, accessed_columns=["x"])
        suggestions = self.sql.suggest_indexes()
        self.assertEqual(suggestions[0]["column"], "x")

    def test_clear(self):
        self.sql.check_and_log("q", 200)
        self.sql.clear()
        self.assertEqual(len(self.sql.entries()), 0)


class TestStorageAnalytics(unittest.TestCase):
    def setUp(self):
        self.sa = StorageAnalytics()

    def test_record_and_summary(self):
        self.sa.record_snapshot("t1", 100, 1024)
        summary = self.sa.summary()
        self.assertIn("t1", summary["tables"])

    def test_growth_rate(self):
        self.sa.record_snapshot("t1", 100, 1000)
        time.sleep(0.1)
        self.sa.record_snapshot("t1", 200, 2000)
        rate = self.sa.growth_rate("t1")
        self.assertIsNotNone(rate)
        self.assertGreater(rate, 0)

    def test_capacity_projection(self):
        self.sa.record_snapshot("t1", 100, 1000)
        time.sleep(0.1)
        self.sa.record_snapshot("t1", 200, 2000)
        remaining = self.sa.capacity_projection("t1", 10000)
        self.assertIsNotNone(remaining)
        self.assertGreater(remaining, 0)


class TestQuantumResourceDashboard(unittest.TestCase):
    def setUp(self):
        self.qrd = QuantumResourceDashboard(max_qubits=10, shot_budget=5000)

    def test_allocate_and_release(self):
        self.assertTrue(self.qrd.allocate_qubits(5))
        self.assertTrue(self.qrd.allocate_qubits(5))
        self.assertFalse(self.qrd.allocate_qubits(1))
        self.qrd.release_qubits(3)
        self.assertTrue(self.qrd.allocate_qubits(3))

    def test_consume_shots(self):
        self.qrd.consume_shots(100)
        d = self.qrd.dashboard()
        self.assertEqual(d["shots_consumed"], 100)
        self.assertEqual(d["shots_remaining"], 4900)

    def test_record_error(self):
        self.qrd.record_error("GATE_ERROR", "T1 timeout on qubit 3")
        d = self.qrd.dashboard()
        self.assertEqual(d["error_count"], 1)

    def test_reset_budget(self):
        self.qrd.consume_shots(100)
        self.qrd.reset_budget(10000)
        d = self.qrd.dashboard()
        self.assertEqual(d["shots_consumed"], 0)
        self.assertEqual(d["shot_budget"], 10000)


class TestAlertManager(unittest.TestCase):
    def setUp(self):
        self.am = AlertManager()

    def test_add_rule_and_evaluate(self):
        self.am.add_rule(
            "high_latency",
            condition=lambda m: m.get("avg_latency_ms", 0) > 100,
            severity=AlertManager.Severity.WARNING,
            message_template="Latency exceeded threshold: {name}",
        )
        fired = self.am.evaluate({"avg_latency_ms": 200})
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0]["severity"], "WARNING")

    def test_cooldown(self):
        self.am.add_rule("r1", condition=lambda m: True, cooldown_seconds=10)
        self.am.evaluate({})
        fired = self.am.evaluate({})
        self.assertEqual(len(fired), 0)  # cooldown active

    def test_callback(self):
        alerts_received = []
        self.am.add_callback(lambda a: alerts_received.append(a))
        self.am.add_rule("r1", condition=lambda m: True, cooldown_seconds=0)
        self.am.evaluate({})
        self.assertEqual(len(alerts_received), 1)


class TestAdminConsole(unittest.TestCase):
    def test_health_check(self):
        console = AdminConsole()
        health = console.health_check()
        self.assertIn("status", health)
        self.assertIn("performance", health)
        self.assertIn("resources", health)

    def test_run_diagnostics(self):
        console = AdminConsole()
        diag = console.run_diagnostics()
        self.assertIn("alerts_fired", diag)
        self.assertIn("index_suggestions", diag)


# =====================================================================
# 8.4  Integration & Ecosystem
# =====================================================================

class TestJDBCODBCAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = JDBCODBCAdapter(
            executor=lambda q: [{"id": 1, "name": "test"}]
        )

    def test_connect_execute_fetch_close(self):
        conn_id = self.adapter.connect("qndb://localhost", "admin")
        n = self.adapter.execute(conn_id, "SELECT * FROM t")
        self.assertEqual(n, 1)
        rows = self.adapter.fetch(conn_id)
        self.assertEqual(len(rows), 1)
        self.adapter.close(conn_id)

    def test_bad_connection_raises(self):
        with self.assertRaises(ConnectionError):
            self.adapter.execute("bad_id", "SELECT 1")

    def test_list_connections(self):
        self.adapter.connect("dsn1")
        conns = self.adapter.list_connections()
        self.assertEqual(len(conns), 1)


class TestSQLAlchemyDialect(unittest.TestCase):
    def setUp(self):
        self.dialect = SQLAlchemyDialect(
            schema_provider=lambda: {"users": ["id", "name"], "orders": ["id", "amount"]}
        )

    def test_get_table_names(self):
        tables = self.dialect.get_table_names()
        self.assertIn("users", tables)
        self.assertIn("orders", tables)

    def test_get_columns(self):
        cols = self.dialect.get_columns("users")
        names = [c["name"] for c in cols]
        self.assertIn("id", names)

    def test_has_table(self):
        self.assertTrue(self.dialect.has_table("users"))
        self.assertFalse(self.dialect.has_table("nonexistent"))


class TestArrowFlightServer(unittest.TestCase):
    def setUp(self):
        self.server = ArrowFlightServer(
            executor=lambda q: [{"x": 1}, {"x": 2}]
        )

    def test_get_flight_info_and_do_get(self):
        info = self.server.get_flight_info("SELECT * FROM t")
        self.assertEqual(info["num_rows"], 2)
        data = self.server.do_get(info["ticket"])
        self.assertEqual(len(data), 2)

    def test_do_get_consumed_raises(self):
        info = self.server.get_flight_info("SELECT 1")
        self.server.do_get(info["ticket"])
        with self.assertRaises(KeyError):
            self.server.do_get(info["ticket"])

    def test_do_put_and_flush(self):
        n = self.server.do_put("t1", [{"a": 1}, {"a": 2}])
        self.assertEqual(n, 2)
        rows = self.server.flush_put_buffer("t1")
        self.assertEqual(len(rows), 2)


class TestKafkaConnector(unittest.TestCase):
    def setUp(self):
        self.kafka = KafkaConnector()

    def test_produce_and_consume(self):
        self.kafka.produce("events", "k1", {"action": "click"})
        self.kafka.produce("events", "k2", {"action": "view"})
        msgs = self.kafka.consume("events", 10)
        self.assertEqual(len(msgs), 2)

    def test_seek(self):
        self.kafka.produce("t", None, "a")
        self.kafka.produce("t", None, "b")
        self.kafka.seek("t", 1)
        msgs = self.kafka.consume("t", 10)
        self.assertEqual(len(msgs), 1)

    def test_topic_stats(self):
        self.kafka.produce("t1", None, "x")
        stats = self.kafka.topic_stats("t1")
        self.assertEqual(stats["message_count"], 1)
        self.assertEqual(stats["lag"], 1)

    def test_list_topics(self):
        self.kafka.produce("a", None, 1)
        self.kafka.produce("b", None, 2)
        topics = self.kafka.list_topics()
        self.assertIn("a", topics)
        self.assertIn("b", topics)


class TestGraphQLLayer(unittest.TestCase):
    def setUp(self):
        self.gql = GraphQLLayer()

    def test_register_and_execute_query(self):
        self.gql.register_query("users", lambda: [{"name": "Alice"}])
        result = self.gql.execute("query", "users")
        self.assertEqual(result, [{"name": "Alice"}])

    def test_mutation(self):
        store = {"count": 0}
        self.gql.register_mutation("increment", lambda: store.update(count=store["count"] + 1))
        self.gql.execute("mutation", "increment")
        self.assertEqual(store["count"], 1)

    def test_introspect(self):
        self.gql.register_query("q1", lambda: [])
        self.gql.register_mutation("m1", lambda: None)
        schema = self.gql.introspect()
        self.assertIn("q1", schema["queries"])
        self.assertIn("m1", schema["mutations"])

    def test_missing_resolver_raises(self):
        with self.assertRaises(KeyError):
            self.gql.execute("query", "nonexistent")


class TestMetricsExporter(unittest.TestCase):
    def setUp(self):
        self.exp = MetricsExporter(prefix="test")

    def test_counter(self):
        self.exp.inc_counter("requests")
        self.exp.inc_counter("requests")
        snap = self.exp.snapshot()
        self.assertEqual(snap["counters"]["test_requests"], 2.0)

    def test_gauge(self):
        self.exp.set_gauge("active_conns", 5)
        snap = self.exp.snapshot()
        self.assertEqual(snap["gauges"]["test_active_conns"], 5)

    def test_histogram(self):
        self.exp.observe_histogram("latency", 10.0)
        self.exp.observe_histogram("latency", 20.0)
        snap = self.exp.snapshot()
        self.assertEqual(len(snap["histograms"]["test_latency"]), 2)

    def test_exposition_format(self):
        self.exp.inc_counter("x")
        text = self.exp.exposition()
        self.assertIn("# TYPE test_x counter", text)

    def test_labels(self):
        self.exp.inc_counter("req", labels={"method": "GET"})
        snap = self.exp.snapshot()
        self.assertIn('test_req{method="GET"}', snap["counters"])


class TestTracingProvider(unittest.TestCase):
    def setUp(self):
        self.tp = TracingProvider(service_name="test-svc")

    def test_start_and_end_span(self):
        sid = self.tp.start_span("query_execute")
        self.tp.end_span(sid, status="OK")
        spans = self.tp.recent_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["status"], "OK")
        self.assertIn("duration_ms", spans[0])

    def test_parent_child_spans(self):
        parent = self.tp.start_span("parent", trace_id="trace123")
        child = self.tp.start_span("child", trace_id="trace123", parent_span_id=parent)
        self.tp.end_span(child)
        self.tp.end_span(parent)
        trace = self.tp.get_trace("trace123")
        self.assertEqual(len(trace), 2)

    def test_export_otlp(self):
        sid = self.tp.start_span("op")
        self.tp.end_span(sid)
        exported = self.tp.export_otlp()
        self.assertEqual(len(exported), 1)
        self.assertIn("traceId", exported[0])
        self.assertIn("spanId", exported[0])


# =====================================================================
# Package-level import
# =====================================================================

class TestEnterprisePackageImport(unittest.TestCase):
    def test_import_all(self):
        from qndb.enterprise import __all__ as all_names
        self.assertEqual(len(all_names), 26)

    def test_import_classes(self):
        from qndb.enterprise import (
            ColumnarStorage, QuantumDataType, QuantumColumnCompressor,
            MaterializedViewManager, PartitionManager, TieredStorageManager,
            WindowFunction, CTEResolver, UDQFRegistry, StoredProcedure,
            ViewManager, QuantumFullTextSearch, QuantumGeospatialIndex,
            AdminConsole, QueryPerformanceMonitor, SlowQueryLog,
            StorageAnalytics, QuantumResourceDashboard, AlertManager,
            JDBCODBCAdapter, SQLAlchemyDialect, ArrowFlightServer,
            KafkaConnector, GraphQLLayer, MetricsExporter, TracingProvider,
        )
        self.assertTrue(all([
            ColumnarStorage, QuantumDataType, QuantumColumnCompressor,
            MaterializedViewManager, PartitionManager, TieredStorageManager,
            WindowFunction, CTEResolver, UDQFRegistry, StoredProcedure,
            ViewManager, QuantumFullTextSearch, QuantumGeospatialIndex,
            AdminConsole, QueryPerformanceMonitor, SlowQueryLog,
            StorageAnalytics, QuantumResourceDashboard, AlertManager,
            JDBCODBCAdapter, SQLAlchemyDialect, ArrowFlightServer,
            KafkaConnector, GraphQLLayer, MetricsExporter, TracingProvider,
        ]))


if __name__ == '__main__':
    unittest.main()
