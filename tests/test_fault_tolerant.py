import unittest
import os
import shutil
import tempfile
import time
import logging
import sys
import numpy as np
import cirq

from qndb.fault_tolerant.operations import (
    SurfaceCodeStorageLayer,
    LogicalQubit,
    MagicStateDistillery,
    LatticeSurgeryEngine,
    ErrorBudgetTracker,
)
from qndb.fault_tolerant.scalable import (
    LogicalQubitManager,
    MultiZoneProcessor,
    QuantumMemoryBank,
    ModularQPUConnector,
    PetabyteQuantumIndex,
)
from qndb.fault_tolerant.networking import (
    QuantumInternetGateway,
    EntanglementDistributor,
    QuantumRepeaterChain,
    BellPairLocker,
    QuantumSecureLink,
)
from qndb.fault_tolerant.performance import (
    BatchQueryEngine,
    CircuitCacheLayer,
    HorizontalScaler,
    QuantumAdvantageBenchmark,
)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# =====================================================================
# 9.1  Fault-Tolerant Operations
# =====================================================================

class TestSurfaceCodeStorageLayer(unittest.TestCase):
    def setUp(self):
        self.sc = SurfaceCodeStorageLayer(code_distance=3)

    def test_create_patch(self):
        patch = self.sc.create_patch("q0")
        self.assertEqual(patch["code_distance"], 3)
        self.assertEqual(len(patch["data_qubits"]), 9)
        self.assertIsInstance(patch["syndrome_circuit"], cirq.Circuit)

    def test_duplicate_patch_raises(self):
        self.sc.create_patch("q0")
        with self.assertRaises(ValueError):
            self.sc.create_patch("q0")

    def test_delete_patch(self):
        self.sc.create_patch("q0")
        self.sc.delete_patch("q0")
        with self.assertRaises(KeyError):
            self.sc.get_patch("q0")

    def test_list_patches(self):
        self.sc.create_patch("a")
        self.sc.create_patch("b")
        self.assertEqual(sorted(self.sc.list_patches()), ["a", "b"])

    def test_encode_logical_zero(self):
        self.sc.create_patch("q0")
        circuit = self.sc.encode_logical_zero("q0")
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_encode_logical_plus(self):
        self.sc.create_patch("q0")
        circuit = self.sc.encode_logical_plus("q0")
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_decode_syndrome(self):
        corrections = self.sc.decode_syndrome([1, 0, 1, 0], stabiliser_type="X")
        self.assertIsInstance(corrections, list)

    def test_invalid_distance(self):
        with self.assertRaises(ValueError):
            SurfaceCodeStorageLayer(code_distance=2)


class TestLogicalQubit(unittest.TestCase):
    def setUp(self):
        self.sc = SurfaceCodeStorageLayer(code_distance=3)
        self.lq = LogicalQubit("lq0", self.sc)

    def test_logical_x(self):
        circuit = self.lq.logical_x()
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_logical_z(self):
        circuit = self.lq.logical_z()
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_logical_h(self):
        circuit = self.lq.logical_h()
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_logical_s(self):
        circuit = self.lq.logical_s()
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_logical_t_with_distillery(self):
        distillery = MagicStateDistillery()
        circuit = self.lq.logical_t(distillery)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_logical_measure(self):
        circuit = self.lq.logical_measure()
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_gate_history(self):
        self.lq.logical_x()
        self.lq.logical_z()
        self.assertEqual(len(self.lq.gate_history()), 2)

    def test_syndrome_round(self):
        circuit = self.lq.syndrome_round()
        self.assertIsInstance(circuit, cirq.Circuit)


class TestMagicStateDistillery(unittest.TestCase):
    def setUp(self):
        self.dis = MagicStateDistillery()

    def test_distill(self):
        circuit = self.dis.distill()
        self.assertIsInstance(circuit, cirq.Circuit)
        self.assertGreater(len(circuit.all_qubits()), 0)

    def test_distill_batch(self):
        circuits = self.dis.distill_batch(3)
        self.assertEqual(len(circuits), 3)

    def test_estimate_overhead(self):
        overhead = self.dis.estimate_overhead()
        self.assertEqual(overhead["protocol"], "FIFTEEN_TO_ONE")
        self.assertGreater(overhead["success_probability"], 0.9)

    def test_twenty_to_four_protocol(self):
        dis = MagicStateDistillery(protocol=MagicStateDistillery.Protocol.TWENTY_TO_FOUR)
        circuit = dis.distill()
        self.assertIsInstance(circuit, cirq.Circuit)


class TestLatticeSurgeryEngine(unittest.TestCase):
    def setUp(self):
        self.sc = SurfaceCodeStorageLayer(code_distance=3)
        self.sc.create_patch("ctrl")
        self.sc.create_patch("tgt")
        self.engine = LatticeSurgeryEngine(self.sc)

    def test_logical_cnot(self):
        circuit = self.engine.logical_cnot("ctrl", "tgt")
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_merge_xx(self):
        circuit = self.engine.merge("ctrl", "tgt",
                                    LatticeSurgeryEngine.OperationType.MERGE_XX)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_merge_zz(self):
        circuit = self.engine.merge("ctrl", "tgt",
                                    LatticeSurgeryEngine.OperationType.MERGE_ZZ)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_split(self):
        circuit = self.engine.split("ctrl")
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_operation_log(self):
        self.engine.logical_cnot("ctrl", "tgt")
        log = self.engine.operation_log()
        self.assertGreater(len(log), 0)


class TestErrorBudgetTracker(unittest.TestCase):
    def setUp(self):
        self.ebt = ErrorBudgetTracker(default_budget=1e-4)

    def test_register_and_status(self):
        qid = self.ebt.register_query()
        status = self.ebt.query_status(qid)
        self.assertEqual(status["total_budget"], 1e-4)
        self.assertFalse(status["over_budget"])

    def test_record_gate(self):
        qid = self.ebt.register_query()
        res = self.ebt.record_gate(qid, "H", 1e-5)
        self.assertGreater(res["remaining"], 0)

    def test_over_budget(self):
        qid = self.ebt.register_query(total_budget=1e-6)
        res = self.ebt.record_gate(qid, "CNOT", 1e-3)
        self.assertTrue(res["over_budget"])
        self.assertGreater(res["recommended_syndrome_rounds"], 0)

    def test_allocate_correction(self):
        qid = self.ebt.register_query()
        self.ebt.record_gate(qid, "T", 5e-5)
        res = self.ebt.allocate_correction(qid, 2)
        self.assertGreater(res["remaining"], 0)

    def test_summary(self):
        self.ebt.register_query()
        summary = self.ebt.summary()
        self.assertEqual(summary["tracked_queries"], 1)

    def test_invalid_budget(self):
        with self.assertRaises(ValueError):
            ErrorBudgetTracker(default_budget=2.0)


# =====================================================================
# 9.2  Scalable Architecture
# =====================================================================

class TestLogicalQubitManager(unittest.TestCase):
    def setUp(self):
        self.mgr = LogicalQubitManager(capacity=100)

    def test_allocate(self):
        ids = self.mgr.allocate(5, zone="zone_a")
        self.assertEqual(len(ids), 5)

    def test_release(self):
        ids = self.mgr.allocate(3)
        released = self.mgr.release(ids)
        self.assertEqual(released, 3)

    def test_capacity_exceeded(self):
        self.mgr.allocate(100)
        with self.assertRaises(RuntimeError):
            self.mgr.allocate(1)

    def test_mark_error(self):
        ids = self.mgr.allocate(1)
        self.mgr.mark_error(ids[0], "decoherence")
        stats = self.mgr.stats()
        self.assertEqual(stats["by_state"].get("ERROR", 0), 1)

    def test_reclaim_expired(self):
        mgr = LogicalQubitManager(capacity=10)
        ids = mgr.allocate(2)
        # Force coherence deadline into the past
        for qid in ids:
            mgr._qubits[qid]["coherence_deadline"] = time.time() - 1
        reclaimed = mgr.reclaim_expired()
        self.assertEqual(reclaimed, 2)

    def test_stats(self):
        self.mgr.allocate(5)
        stats = self.mgr.stats()
        self.assertEqual(stats["capacity"], 100)
        self.assertEqual(stats["total_tracked"], 5)


class TestMultiZoneProcessor(unittest.TestCase):
    def setUp(self):
        self.proc = MultiZoneProcessor()
        self.proc.add_zone("z1", qubit_capacity=50)
        self.proc.add_zone("z2", qubit_capacity=100)

    def test_add_zone(self):
        self.assertEqual(len(self.proc.zone_stats()), 2)

    def test_duplicate_zone_raises(self):
        with self.assertRaises(ValueError):
            self.proc.add_zone("z1")

    def test_remove_zone(self):
        self.proc.remove_zone("z1")
        self.assertEqual(len(self.proc.zone_stats()), 1)

    def test_route_circuit(self):
        q = cirq.LineQubit.range(5)
        circuit = cirq.Circuit(cirq.H.on_each(*q))
        result = self.proc.route_circuit(circuit, preferred_zone="z1")
        self.assertEqual(result["zone"], "z1")

    def test_route_best_fit(self):
        q = cirq.LineQubit.range(60)
        circuit = cirq.Circuit(cirq.H.on_each(*q))
        result = self.proc.route_circuit(circuit)
        self.assertEqual(result["zone"], "z2")  # z1 only has 50

    def test_add_link_and_inter_zone(self):
        self.proc.add_link("z1", "z2", fidelity=0.99)
        circuit = self.proc.inter_zone_circuit("z1", "z2", num_pairs=2)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_release_zone_qubits(self):
        q = cirq.LineQubit.range(5)
        circuit = cirq.Circuit(cirq.H.on_each(*q))
        self.proc.route_circuit(circuit, preferred_zone="z1")
        self.proc.release_zone_qubits("z1", 5)
        stats = [s for s in self.proc.zone_stats() if s["zone_id"] == "z1"][0]
        self.assertEqual(stats["allocated"], 0)


class TestQuantumMemoryBank(unittest.TestCase):
    def setUp(self):
        self.mem = QuantumMemoryBank(num_slots=16, t1_microseconds=1e6, t2_microseconds=1e6)

    def test_store_and_load(self):
        amps = np.array([1, 0, 0, 0], dtype=complex) / 1
        self.mem.store(0, amps)
        loaded = self.mem.load(0)
        np.testing.assert_allclose(loaded, amps)

    def test_load_empty_slot(self):
        self.assertIsNone(self.mem.load(5))

    def test_out_of_range_slot(self):
        with self.assertRaises(ValueError):
            self.mem.store(100, np.array([1]))

    def test_fidelity(self):
        self.mem.store(0, np.array([1, 0], dtype=complex))
        f = self.mem.fidelity(0)
        self.assertGreater(f, 0.99)

    def test_refresh(self):
        self.mem.store(0, np.array([1, 0], dtype=complex))
        f = self.mem.refresh(0)
        self.assertEqual(f, 1.0)

    def test_evict(self):
        self.mem.store(0, np.array([1]))
        self.mem.evict(0)
        self.assertIsNone(self.mem.load(0))

    def test_stats(self):
        self.mem.store(0, np.array([1, 0], dtype=complex))
        stats = self.mem.stats()
        self.assertEqual(stats["occupied"], 1)


class TestModularQPUConnector(unittest.TestCase):
    def setUp(self):
        self.conn = ModularQPUConnector()
        self.conn.register_module("m1", num_qubits=50)
        self.conn.register_module("m2", num_qubits=100)

    def test_duplicate_module_raises(self):
        with self.assertRaises(ValueError):
            self.conn.register_module("m1", num_qubits=50)

    def test_connect_and_bell(self):
        self.conn.connect_modules("m1", "m2", fidelity=0.99)
        circuit = self.conn.build_cross_module_bell("m1", "m2")
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_unconnected_bell_raises(self):
        with self.assertRaises(ValueError):
            self.conn.build_cross_module_bell("m1", "m2")

    def test_aggregate_capacity(self):
        cap = self.conn.aggregate_capacity()
        self.assertEqual(cap["total_qubits"], 150)
        self.assertEqual(cap["module_count"], 2)

    def test_route_to_module(self):
        mid = self.conn.route_to_module(60)
        self.assertEqual(mid, "m2")

    def test_deregister(self):
        self.conn.deregister_module("m1")
        self.assertEqual(self.conn.aggregate_capacity()["module_count"], 1)


class TestPetabyteQuantumIndex(unittest.TestCase):
    def setUp(self):
        self.idx = PetabyteQuantumIndex(num_index_qubits=8)

    def test_insert_and_lookup(self):
        self.idx.insert("key1", "value1")
        self.assertEqual(self.idx.lookup("key1"), "value1")

    def test_lookup_missing(self):
        self.assertIsNone(self.idx.lookup("nonexistent"))

    def test_delete(self):
        self.idx.insert("k", "v")
        self.assertTrue(self.idx.delete("k"))
        self.assertIsNone(self.idx.lookup("k"))

    def test_range_scan(self):
        self.idx.insert("user:1", "Alice")
        self.idx.insert("user:2", "Bob")
        self.idx.insert("order:1", "Widget")
        results = self.idx.range_scan("user:")
        self.assertEqual(len(results), 2)

    def test_quantum_search_circuit(self):
        self.idx.insert("target", "data")
        circuit = self.idx.quantum_search_circuit("target")
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_stats(self):
        self.idx.insert("a", 1)
        stats = self.idx.stats()
        self.assertEqual(stats["total_keys"], 1)
        self.assertEqual(stats["index_qubits"], 8)


# =====================================================================
# 9.3  Quantum Networking
# =====================================================================

class TestQuantumInternetGateway(unittest.TestCase):
    def setUp(self):
        self.gw = QuantumInternetGateway(local_node_id="node_A")

    def test_register_peer(self):
        self.gw.register_peer("node_B", fidelity=0.99)
        status = self.gw.link_status()
        self.assertIn("node_B", status)
        self.assertEqual(status["node_B"]["state"], "UP")

    def test_send_and_receive(self):
        self.gw.register_peer("node_B")
        amps = np.array([1, 0], dtype=complex)
        tx_id = self.gw.send_state("node_B", amps)
        self.assertIsInstance(tx_id, str)
        received = self.gw.receive_states()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["tx_id"], tx_id)

    def test_send_to_down_link_raises(self):
        self.gw.register_peer("node_B")
        self.gw.set_link_state("node_B", QuantumInternetGateway.LinkState.DOWN)
        with self.assertRaises(ConnectionError):
            self.gw.send_state("node_B", np.array([1, 0]))

    def test_deregister_peer(self):
        self.gw.register_peer("node_B")
        self.gw.deregister_peer("node_B")
        self.assertNotIn("node_B", self.gw.link_status())


class TestEntanglementDistributor(unittest.TestCase):
    def setUp(self):
        self.dist = EntanglementDistributor(pool_size=50)

    def test_generate_pair(self):
        pair = self.dist.generate_pair("A", "B")
        self.assertIn("pair_id", pair)
        self.assertIsInstance(pair["circuit"], cirq.Circuit)

    def test_consume_pair(self):
        self.dist.generate_pair("A", "B")
        pair = self.dist.consume_pair("A", "B")
        self.assertIsNotNone(pair)
        # Pool should be empty now
        self.assertIsNone(self.dist.consume_pair("A", "B"))

    def test_generate_pool(self):
        n = self.dist.generate_pool("A", "B", 10)
        self.assertEqual(n, 10)
        stats = self.dist.pool_stats()
        self.assertEqual(stats["available"], 10)

    def test_build_ghz(self):
        circuit = self.dist.build_ghz_circuit(["A", "B", "C"])
        self.assertIsInstance(circuit, cirq.Circuit)
        self.assertEqual(len(circuit.all_qubits()), 3)

    def test_ghz_too_few_raises(self):
        with self.assertRaises(ValueError):
            self.dist.build_ghz_circuit(["A"])


class TestQuantumRepeaterChain(unittest.TestCase):
    def setUp(self):
        self.chain = QuantumRepeaterChain(segment_fidelity=0.95)
        self.chain.add_segment("A", "R1", distance_km=50)
        self.chain.add_segment("R1", "B", distance_km=50)

    def test_end_to_end_fidelity(self):
        f = self.chain.end_to_end_fidelity()
        self.assertAlmostEqual(f, 0.95 ** 2, places=5)

    def test_build_swap_circuit(self):
        circuit = self.chain.build_swap_circuit(0)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_build_full_chain(self):
        circuit = self.chain.build_full_chain_circuit()
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_purify(self):
        f_before = self.chain.end_to_end_fidelity()
        f_after = self.chain.purify(num_rounds=3)
        self.assertGreater(f_after, f_before)

    def test_chain_stats(self):
        stats = self.chain.chain_stats()
        self.assertEqual(stats["num_segments"], 2)
        self.assertEqual(stats["total_distance_km"], 100)

    def test_invalid_segment_raises(self):
        with self.assertRaises(IndexError):
            self.chain.build_swap_circuit(10)


class TestBellPairLocker(unittest.TestCase):
    def setUp(self):
        self.dist = EntanglementDistributor(pool_size=50)
        self.dist.generate_pool("A", "B", 10)
        self.locker = BellPairLocker(self.dist)

    def test_acquire_and_release(self):
        acquired = self.locker.acquire("resource_1", "A", "B")
        self.assertTrue(acquired)
        self.assertTrue(self.locker.is_locked("resource_1"))
        self.assertTrue(self.locker.release("resource_1"))
        self.assertFalse(self.locker.is_locked("resource_1"))

    def test_double_acquire_fails(self):
        self.locker.acquire("r1", "A", "B", timeout=10)
        self.assertFalse(self.locker.acquire("r1", "A", "B", timeout=10))

    def test_lock_info(self):
        self.locker.acquire("r1", "A", "B")
        info = self.locker.lock_info("r1")
        self.assertEqual(info["holder_a"], "A")

    def test_active_locks(self):
        self.locker.acquire("r1", "A", "B")
        self.locker.acquire("r2", "A", "B")
        self.assertEqual(len(self.locker.active_locks()), 2)

    def test_verification_circuit(self):
        self.locker.acquire("r1", "A", "B")
        circuit = self.locker.build_lock_verification_circuit("r1")
        self.assertIsInstance(circuit, cirq.Circuit)


class TestQuantumSecureLink(unittest.TestCase):
    def setUp(self):
        self.qsl = QuantumSecureLink(key_length=256)

    def test_generate_bb84_circuit(self):
        circuit = self.qsl.generate_bb84_circuit(16)
        self.assertIsInstance(circuit, cirq.Circuit)

    def test_establish_key(self):
        result = self.qsl.establish_key("link_AB", "A", "B")
        self.assertEqual(result["link_id"], "link_AB")
        self.assertGreater(result["sifted_bits"], 0)
        self.assertEqual(result["key_bytes"], 32)

    def test_get_key(self):
        self.qsl.establish_key("link_AB", "A", "B")
        key = self.qsl.get_key("link_AB")
        self.assertIsInstance(key, bytes)
        self.assertEqual(len(key), 32)

    def test_encrypt_decrypt(self):
        self.qsl.establish_key("link_AB", "A", "B")
        plaintext = b"Hello quantum world!"
        ciphertext = self.qsl.encrypt_classical("link_AB", plaintext)
        self.assertNotEqual(ciphertext, plaintext)
        decrypted = self.qsl.decrypt_classical("link_AB", ciphertext)
        self.assertEqual(decrypted, plaintext)

    def test_rotate_key(self):
        self.qsl.establish_key("link_AB", "A", "B")
        old_key = self.qsl.get_key("link_AB")
        self.qsl.rotate_key("link_AB", "A", "B")
        new_key = self.qsl.get_key("link_AB")
        # Keys should differ (extremely high probability)
        self.assertNotEqual(old_key, new_key)

    def test_list_links(self):
        self.qsl.establish_key("link_1", "A", "B")
        self.assertIn("link_1", self.qsl.list_links())


# =====================================================================
# 9.4  Performance at Scale
# =====================================================================

class TestBatchQueryEngine(unittest.TestCase):
    def setUp(self):
        self.engine = BatchQueryEngine(max_batch_size=10)

    def test_submit_batch_sequential(self):
        engine = BatchQueryEngine(strategy=BatchQueryEngine.Strategy.SEQUENTIAL)
        q = cirq.LineQubit(0)
        queries = [
            {"circuit": cirq.Circuit(cirq.H(q), cirq.measure(q, key="m")), "key": f"q{i}", "repetitions": 1}
            for i in range(3)
        ]
        result = engine.submit_batch(queries)
        self.assertEqual(result["total"], 3)
        self.assertEqual(len(result["results"]), 3)

    def test_submit_batch_parallel(self):
        q = cirq.LineQubit(0)
        queries = [
            {"circuit": cirq.Circuit(cirq.H(q), cirq.measure(q, key=f"m{i}")), "key": f"q{i}"}
            for i in range(3)
        ]
        result = self.engine.submit_batch(queries)
        self.assertEqual(result["total"], 3)

    def test_throughput_stats(self):
        q = cirq.LineQubit(0)
        self.engine.submit_batch([
            {"circuit": cirq.Circuit(cirq.H(q), cirq.measure(q, key="m")), "key": "q0"}
        ])
        stats = self.engine.throughput_stats()
        self.assertEqual(stats["batches"], 1)
        self.assertGreater(stats["avg_queries_per_sec"], 0)

    def test_custom_executor(self):
        calls = []
        def mock_exec(circuit, reps):
            calls.append(1)
            return None
        engine = BatchQueryEngine(strategy=BatchQueryEngine.Strategy.SEQUENTIAL)
        q = cirq.LineQubit(0)
        engine.submit_batch(
            [{"circuit": cirq.Circuit(cirq.H(q)), "key": "q0"}],
            executor=mock_exec,
        )
        self.assertEqual(len(calls), 1)


class TestCircuitCacheLayer(unittest.TestCase):
    def setUp(self):
        self.cache = CircuitCacheLayer(capacity=10, ttl_seconds=2)

    def test_put_and_get(self):
        circuit = cirq.Circuit(cirq.H(cirq.LineQubit(0)))
        self.cache.put("hash1", circuit)
        cached = self.cache.get("hash1")
        self.assertEqual(cached, circuit)

    def test_miss(self):
        self.assertIsNone(self.cache.get("nonexistent"))

    def test_ttl_expiry(self):
        circuit = cirq.Circuit()
        self.cache.put("h1", circuit)
        time.sleep(2.1)
        self.assertIsNone(self.cache.get("h1"))

    def test_lru_eviction(self):
        for i in range(12):
            self.cache.put(f"h{i}", cirq.Circuit())
        # First two should be evicted
        self.assertIsNone(self.cache.get("h0"))
        self.assertIsNone(self.cache.get("h1"))
        self.assertIsNotNone(self.cache.get("h2"))

    def test_invalidate(self):
        self.cache.put("h1", cirq.Circuit())
        self.assertTrue(self.cache.invalidate("h1"))
        self.assertIsNone(self.cache.get("h1"))

    def test_clear(self):
        self.cache.put("h1", cirq.Circuit())
        self.cache.put("h2", cirq.Circuit())
        self.assertEqual(self.cache.clear(), 2)

    def test_hash_query(self):
        h = self.cache.hash_query("SELECT * FROM t")
        self.assertEqual(len(h), 64)  # SHA-256 hex

    def test_stats(self):
        self.cache.put("h1", cirq.Circuit())
        self.cache.get("h1")  # hit
        self.cache.get("h2")  # miss
        stats = self.cache.stats()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertAlmostEqual(stats["hit_rate"], 0.5)


class TestHorizontalScaler(unittest.TestCase):
    def setUp(self):
        self.scaler = HorizontalScaler(min_workers=2, max_workers=8)

    def test_initial_workers(self):
        self.assertEqual(self.scaler.worker_count(), 2)

    def test_submit_and_process(self):
        self.scaler.submit({"type": "circuit_exec"})
        self.scaler.submit({"type": "circuit_exec"})
        processed = self.scaler.process_pending()
        self.assertEqual(processed, 2)

    def test_add_worker(self):
        wid = self.scaler.add_worker()
        self.assertEqual(self.scaler.worker_count(), 3)

    def test_remove_worker_respects_min(self):
        self.assertFalse(self.scaler.remove_worker())  # already at min

    def test_stats(self):
        stats = self.scaler.stats()
        self.assertEqual(stats["workers"], 2)
        self.assertEqual(stats["min_workers"], 2)
        self.assertEqual(stats["max_workers"], 8)


class TestQuantumAdvantageBenchmark(unittest.TestCase):
    def setUp(self):
        self.bench = QuantumAdvantageBenchmark()

    def test_register_benchmark(self):
        result = self.bench.register_benchmark(
            "test_bench",
            quantum_fn=lambda: sum(range(100)),
            classical_fn=lambda: sum(range(100)),
        )
        self.assertEqual(result["name"], "test_bench")
        self.assertIn("avg_speedup", result)
        self.assertEqual(len(result["sizes"]), 1)

    def test_multiple_sizes(self):
        result = self.bench.register_benchmark(
            "multi_size",
            quantum_fn=lambda: 42,
            classical_fn=lambda: 42,
            sizes=[10, 100, 1000],
        )
        self.assertEqual(len(result["sizes"]), 3)

    def test_summary(self):
        self.bench.register_benchmark("b1", lambda: 1, lambda: 1)
        summary = self.bench.summary()
        self.assertEqual(summary["benchmarks"], 1)

    def test_clear(self):
        self.bench.register_benchmark("b1", lambda: 1, lambda: 1)
        self.bench.clear()
        self.assertEqual(len(self.bench.results()), 0)


# =====================================================================
# Package-level import
# =====================================================================

class TestFaultTolerantPackageImport(unittest.TestCase):
    def test_import_all(self):
        from qndb.fault_tolerant import __all__ as all_names
        self.assertEqual(len(all_names), 19)

    def test_import_classes(self):
        from qndb.fault_tolerant import (
            SurfaceCodeStorageLayer, LogicalQubit, MagicStateDistillery,
            LatticeSurgeryEngine, ErrorBudgetTracker,
            LogicalQubitManager, MultiZoneProcessor, QuantumMemoryBank,
            ModularQPUConnector, PetabyteQuantumIndex,
            QuantumInternetGateway, EntanglementDistributor,
            QuantumRepeaterChain, BellPairLocker, QuantumSecureLink,
            BatchQueryEngine, CircuitCacheLayer, HorizontalScaler,
            QuantumAdvantageBenchmark,
        )
        self.assertTrue(all([
            SurfaceCodeStorageLayer, LogicalQubit, MagicStateDistillery,
            LatticeSurgeryEngine, ErrorBudgetTracker,
            LogicalQubitManager, MultiZoneProcessor, QuantumMemoryBank,
            ModularQPUConnector, PetabyteQuantumIndex,
            QuantumInternetGateway, EntanglementDistributor,
            QuantumRepeaterChain, BellPairLocker, QuantumSecureLink,
            BatchQueryEngine, CircuitCacheLayer, HorizontalScaler,
            QuantumAdvantageBenchmark,
        ]))


if __name__ == '__main__':
    unittest.main()
