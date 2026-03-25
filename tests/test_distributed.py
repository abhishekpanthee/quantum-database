"""
Comprehensive tests for the distributed subsystem.

Covers: networking, node_manager, consensus, synchronization,
        query_processor, and cluster_manager.
"""
import json
import os
import tempfile
import time
import unittest

from qndb.distributed.networking import (
    NodeHealth, PartitionState,
    PhiAccrualFailureDetector, ServiceDiscovery, ServiceRecord,
    PartitionDetector, TLSConfig,
    TransportChannel, TransportLayer,
    RPCRequest, RPCResponse,
    encode_message, decode_header, HEADER_SIZE, PROTO_VERSION,
    MSG_HEARTBEAT, MSG_VOTE_REQUEST,
)
from qndb.distributed.node_manager import Node, NodeManager
from qndb.distributed.consensus import (
    LogEntry, PersistentLog, ConsensusMetrics,
    QuantumConsensusProtocol, QuantumRaft, QuantumPBFT,
)
from qndb.distributed.synchronization import (
    ConsistencyLevel, VectorClock, GCounter, LWWRegister,
    ConflictResolutionPolicy, ReplicatedValue, ConflictResolver,
    GeoRouter, QuantumStateSynchronizer,
)
from qndb.distributed.query_processor import (
    PartitionStrategy, PartitionConfig, DataPartitioner,
    QueryFragment, DistributedQueryPlanner,
    DistributedJoinStrategy, DistributedJoinPlanner,
    DistributedAggregator,
    TwoPhaseCommitState, TwoPhaseCommitCoordinator,
    DistributedDeadlockDetector,
)
from qndb.distributed.cluster_manager import (
    NodeRole, ClusterNode, ClusterTopology, HelmValues,
    ScalingMetrics, AutoScaler, UpgradePhase, UpgradeState,
    RollingUpgradeManager, BackupManifest, BackupManager, ClusterManager,
)
from qndb.core.quantum_engine import QuantumEngine
from qndb.middleware.classical_bridge import ClassicalBridge


# ======================================================================
# Networking
# ======================================================================
class TestWireProtocol(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        payload = b'{"hello": "world"}'
        frame = encode_message(MSG_HEARTBEAT, payload)
        ver, mtype, length = decode_header(frame[:HEADER_SIZE])
        self.assertEqual(ver, PROTO_VERSION)
        self.assertEqual(mtype, MSG_HEARTBEAT)
        self.assertEqual(length, len(payload))
        self.assertEqual(frame[HEADER_SIZE:], payload)

    def test_decode_header_incomplete(self):
        with self.assertRaises(ValueError):
            decode_header(b"\x00")


class TestPhiAccrualFailureDetector(unittest.TestCase):
    def setUp(self):
        self.fd = PhiAccrualFailureDetector(threshold=8.0)

    def test_initial_phi_zero(self):
        self.assertEqual(self.fd.phi(), 0.0)

    def test_available_after_heartbeats(self):
        for _ in range(5):
            self.fd.heartbeat()
        self.assertTrue(self.fd.is_available)

    def test_phi_increases_without_heartbeat(self):
        for _ in range(5):
            self.fd.heartbeat()
        phi_now = self.fd.phi()
        self.assertLess(phi_now, 5.0)


class TestServiceDiscovery(unittest.TestCase):
    def setUp(self):
        self.sd = ServiceDiscovery()

    def test_register_and_discover(self):
        self.sd.register("n1", "host1", 5000, ttl=300)
        records = self.sd.discover()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].node_id, "n1")

    def test_deregister(self):
        self.sd.register("n1", "host1", 5000, ttl=300)
        self.assertTrue(self.sd.deregister("n1"))
        self.assertEqual(len(self.sd.discover(healthy_only=False)), 0)

    def test_get(self):
        self.sd.register("n1", "host1", 5000, ttl=300)
        self.assertIsNotNone(self.sd.get("n1"))
        self.assertIsNone(self.sd.get("n999"))

    def test_watcher_callback(self):
        events = []
        self.sd.add_watcher(lambda svc, rec, evt: events.append(evt))
        self.sd.register("n1", "host1", 5000, ttl=300)
        self.sd.deregister("n1")
        self.assertEqual(events, ["register", "deregister"])


class TestPartitionDetector(unittest.TestCase):
    def setUp(self):
        self.pd = PartitionDetector()

    def test_no_peers_connected(self):
        self.assertEqual(self.pd.partition_state, PartitionState.CONNECTED)

    def test_register_peer_and_health(self):
        self.pd.register_peer("p1")
        health = self.pd.peer_health("p1")
        self.assertIn(health, (NodeHealth.HEALTHY, NodeHealth.SUSPECT))

    def test_remove_peer(self):
        self.pd.register_peer("p1")
        self.pd.remove_peer("p1")
        self.assertEqual(self.pd.peer_health("p1"), NodeHealth.DEAD)

    def test_has_quorum_no_peers(self):
        self.assertTrue(self.pd.has_quorum)


class TestTransportChannel(unittest.TestCase):
    def test_send_receive(self):
        ch = TransportChannel("a", "b")
        req = RPCRequest(method="ping", payload={"x": 1}, sender_id="a")
        self.assertTrue(ch.send(req))
        ch.deliver(RPCRequest(method="pong", payload={"y": 2}, sender_id="b"))
        msgs = ch.receive()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].method, "pong")

    def test_close_prevents_send(self):
        ch = TransportChannel("a", "b")
        ch.close()
        self.assertFalse(ch.send(RPCRequest(method="x")))

    def test_stats(self):
        ch = TransportChannel("a", "b")
        ch.send(RPCRequest(method="x", payload={"k": 1}))
        s = ch.stats()
        self.assertGreater(s["bytes_sent"], 0)
        self.assertEqual(s["messages_sent"], 1)


class TestTransportLayer(unittest.TestCase):
    def test_connect_send_poll(self):
        tl = TransportLayer("n1")
        tl.connect("n2")
        tl.send("n2", "greetings", {"msg": "hi"})
        ch = tl._channels["n2"]
        ch.deliver(RPCRequest(method="reply", payload={"r": 1}, sender_id="n2"))
        items = tl.poll()
        self.assertEqual(len(items), 1)

    def test_broadcast(self):
        tl = TransportLayer("n1")
        tl.connect("n2")
        tl.connect("n3")
        sent = tl.broadcast("hb", {"t": 1}, exclude={"n3"})
        self.assertEqual(sent, 1)

    def test_disconnect(self):
        tl = TransportLayer("n1")
        tl.connect("n2")
        tl.disconnect("n2")
        self.assertNotIn("n2", tl._channels)


# ======================================================================
# Node manager
# ======================================================================
class TestNode(unittest.TestCase):
    def setUp(self):
        self.node = Node("test_node", "localhost", 8000, is_active=True)

    def test_node_initialization(self):
        self.assertEqual(self.node.id, "test_node")
        self.assertEqual(self.node.host, "localhost")
        self.assertEqual(self.node.port, 8000)
        self.assertTrue(self.node.is_active)
        self.assertEqual(len(self.node.message_queue), 0)

    def test_send_message(self):
        resp = self.node.send_message("test_message", {"key": "value"})
        self.assertEqual(len(self.node.message_queue), 1)
        self.assertEqual(self.node.message_queue[0]["type"], "test_message")
        self.assertEqual(resp["status"], "success")

    def test_receive_messages(self):
        self.node.send_message("m1", {"a": 1})
        self.node.send_message("m2", {"b": 2})
        msgs = self.node.receive_messages()
        self.assertEqual(len(msgs), 2)
        self.assertEqual(len(self.node.message_queue), 0)


class TestNodeManager(unittest.TestCase):
    def setUp(self):
        self.manager = NodeManager(node_id="node1")

    def test_register_node(self):
        self.manager.register_node("node2", "localhost", 8000, is_active=True)
        self.assertIn("node2", self.manager.nodes)
        self.assertEqual(self.manager.nodes["node2"].host, "localhost")

    def test_deregister_node(self):
        self.manager.register_node("node2", "localhost", 8000)
        self.assertTrue(self.manager.deregister_node("node2"))
        self.assertNotIn("node2", self.manager.nodes)

    def test_get_active_nodes(self):
        self.manager.register_node("n2", "h", 1, is_active=True)
        self.manager.register_node("n3", "h", 2, is_active=False)
        active = self.manager.get_active_nodes()
        ids = [n.id for n in active]
        self.assertIn("n2", ids)
        self.assertNotIn("n3", ids)

    def test_mark_node_inactive_and_active(self):
        self.manager.register_node("n2", "h", 1, is_active=True)
        self.manager.mark_node_inactive("n2")
        self.assertFalse(self.manager.nodes["n2"].is_active)
        self.manager.mark_node_active("n2")
        self.assertTrue(self.manager.nodes["n2"].is_active)

    def test_send_and_get_messages(self):
        self.manager.register_node("n2", "h", 1)
        self.manager.transport.connect("n2")
        ch = self.manager.transport._channels.get("n2")
        ch.deliver(RPCRequest(method="test", payload={"foo": "bar"}, sender_id="n2"))
        msgs = self.manager.get_messages()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["foo"], "bar")

    def test_broadcast_message(self):
        self.manager.register_node("n2", "h", 1)
        self.manager.register_node("n3", "h", 2)
        sent = self.manager.broadcast_message({"type": "hb"})
        self.assertGreaterEqual(sent, 1)


# ======================================================================
# Consensus — Persistent log
# ======================================================================
class TestPersistentLog(unittest.TestCase):
    def test_in_memory_log(self):
        log = PersistentLog()
        e = LogEntry(term=1, index=1, command={"set": "x"})
        log.append(e)
        self.assertEqual(log.last_index(), 1)
        self.assertEqual(log.last_term(), 1)
        self.assertEqual(log.get(1).command, {"set": "x"})

    def test_entries_from(self):
        log = PersistentLog()
        for i in range(1, 4):
            log.append(LogEntry(term=1, index=i))
        entries = log.entries_from(2)
        self.assertEqual(len(entries), 2)

    def test_truncate_from(self):
        log = PersistentLog()
        for i in range(1, 6):
            log.append(LogEntry(term=1, index=i))
        log.truncate_from(3)
        self.assertEqual(log.last_index(), 2)

    def test_snapshot_and_restore(self):
        log = PersistentLog()
        log.append(LogEntry(term=1, index=1, command={"a": 1}))
        log.term = 2
        log.voted_for = "n1"
        snap = log.snapshot_data()
        log2 = PersistentLog()
        log2.restore_snapshot(snap)
        self.assertEqual(log2.last_index(), 1)
        self.assertEqual(log2.term, 2)
        self.assertEqual(log2.voted_for, "n1")

    def test_file_backed_log(self):
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            path = f.name
        try:
            log = PersistentLog(path=path)
            log.append(LogEntry(term=1, index=1, command={"x": 1}))
            log.term = 3
            log.voted_for = "n5"
            log2 = PersistentLog(path=path)
            self.assertEqual(log2.last_index(), 1)
            self.assertEqual(log2.term, 3)
            self.assertEqual(log2.voted_for, "n5")
        finally:
            os.unlink(path)
            meta = path + ".meta"
            if os.path.exists(meta):
                os.unlink(meta)


# ======================================================================
# Consensus — Raft
# ======================================================================
class TestQuantumRaft(unittest.TestCase):
    def _make_raft(self, node_id="n1"):
        nm = NodeManager(node_id=node_id)
        nm.register_node(node_id, "localhost", 5000)
        nm.register_node("n2", "localhost", 5001)
        nm.register_node("n3", "localhost", 5002)
        engine = QuantumEngine(num_qubits=2, simulator_type="simulator")
        raft = QuantumRaft(nm, engine)
        raft.start()
        return raft

    def test_initial_state(self):
        raft = self._make_raft()
        self.assertEqual(raft.state, "FOLLOWER")
        self.assertFalse(raft.is_leader)
        self.assertTrue(raft.running)

    def test_start_election(self):
        raft = self._make_raft()
        raft.start_election()
        self.assertEqual(raft.state, "CANDIDATE")
        self.assertEqual(raft.term, 1)
        self.assertEqual(raft.voted_for, "n1")
        self.assertEqual(raft.vote_count, 1)

    def test_become_leader(self):
        raft = self._make_raft()
        raft.start_election()
        raft.become_leader()
        self.assertEqual(raft.state, "LEADER")
        self.assertTrue(raft.is_leader)

    def test_become_follower(self):
        raft = self._make_raft()
        raft.start_election()
        raft.become_leader()
        raft.become_follower(5, "n2")
        self.assertEqual(raft.state, "FOLLOWER")
        self.assertFalse(raft.is_leader)
        self.assertEqual(raft.term, 5)

    def test_propose_entry(self):
        raft = self._make_raft()
        raft.start_election()
        raft.become_leader()
        entry = raft.propose({"key": "val"})
        self.assertIsNotNone(entry)
        self.assertEqual(entry.command, {"key": "val"})
        raft.become_follower(raft.term)
        self.assertIsNone(raft.propose({"x": 1}))

    def test_handle_vote_request_grants(self):
        raft = self._make_raft()
        resp = raft.handle_vote_request({
            "term": 1, "candidate_id": "n2",
            "last_log_term": 0, "last_log_index": 0,
        })
        self.assertTrue(resp["vote_granted"])

    def test_handle_vote_request_rejects_old_term(self):
        raft = self._make_raft()
        raft.start_election()
        resp = raft.handle_vote_request({
            "term": 0, "candidate_id": "n3",
            "last_log_term": 0, "last_log_index": 0,
        })
        self.assertFalse(resp["vote_granted"])

    def test_vote_response_triggers_leader(self):
        raft = self._make_raft()
        raft.start_election()
        raft.handle_vote_response({"vote_granted": True, "term": 1, "node_id": "n2"})
        self.assertEqual(raft.state, "LEADER")

    def test_handle_append_entries(self):
        raft = self._make_raft()
        resp = raft.handle_append_entries({
            "term": 1, "leader_id": "n2",
            "prev_log_index": 0, "prev_log_term": 0,
            "entries": [], "leader_commit": 0,
        })
        self.assertTrue(resp["success"])
        self.assertEqual(raft.current_leader, "n2")

    def test_handle_append_entries_rejects_old_term(self):
        raft = self._make_raft()
        raft.term = 5
        resp = raft.handle_append_entries({
            "term": 2, "leader_id": "n2",
            "prev_log_index": 0, "prev_log_term": 0,
            "entries": [], "leader_commit": 0,
        })
        self.assertFalse(resp["success"])

    def test_append_entries_with_entries(self):
        raft = self._make_raft()
        entry_data = LogEntry(term=1, index=1, command={"a": 1}).to_dict()
        resp = raft.handle_append_entries({
            "term": 1, "leader_id": "n2",
            "prev_log_index": 0, "prev_log_term": 0,
            "entries": [entry_data], "leader_commit": 0,
        })
        self.assertTrue(resp["success"])
        self.assertEqual(raft.log.last_index(), 1)

    def test_create_and_install_snapshot(self):
        raft = self._make_raft()
        raft.start_election()
        raft.become_leader()
        raft.propose({"k": "v"})
        raft.commit_index = 2
        raft.apply_committed()
        snap = raft.create_snapshot({"state": "data"})
        self.assertIn("last_index", snap)
        raft2 = self._make_raft("n2")
        self.assertTrue(raft2.install_snapshot(snap))
        self.assertEqual(raft2._state_machine_snapshot, {"state": "data"})

    def test_propose_membership_change(self):
        raft = self._make_raft()
        raft.start_election()
        raft.become_leader()
        entry = raft.propose_membership_change("add", "n4", "h4", 5004)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.entry_type, "config")

    def test_process_message_vote_request(self):
        raft = self._make_raft()
        resp = raft.process_message({
            "type": "VOTE_REQUEST", "term": 1, "candidate_id": "n2",
            "last_log_term": 0, "last_log_index": 0,
        })
        self.assertIsNotNone(resp)

    def test_is_agreement_reached(self):
        raft = self._make_raft()
        raft.start_election()
        raft.become_leader()
        self.assertTrue(raft.is_agreement_reached())


# ======================================================================
# Consensus — PBFT
# ======================================================================
class TestQuantumPBFT(unittest.TestCase):
    def _make_pbft(self, node_id="n1"):
        nm = NodeManager(node_id=node_id)
        nm.register_node(node_id, "localhost", 5000)
        nm.register_node("n2", "localhost", 5001)
        nm.register_node("n3", "localhost", 5002)
        nm.register_node("n4", "localhost", 5003)
        engine = QuantumEngine(num_qubits=2, simulator_type="simulator")
        pbft = QuantumPBFT(nm, engine)
        return pbft

    def test_initial_state(self):
        pbft = self._make_pbft()
        self.assertFalse(pbft.running)
        self.assertEqual(pbft.view, 0)

    def test_start_sets_primary(self):
        pbft = self._make_pbft()
        pbft.start()
        self.assertTrue(pbft.running)
        self.assertIsNotNone(pbft.current_leader)

    def test_f_and_quorum(self):
        pbft = self._make_pbft()
        self.assertEqual(pbft.f, 1)
        self.assertEqual(pbft.quorum, 3)

    def test_submit_request(self):
        pbft = self._make_pbft()
        pbft.start()
        pbft.submit_request("r1", {"cmd": "set x=1"})
        self.assertIn("r1", pbft.pending_requests)


# ======================================================================
# Synchronization — Vector Clocks & CRDTs
# ======================================================================
class TestVectorClock(unittest.TestCase):
    def test_increment(self):
        vc = VectorClock()
        vc2 = vc.increment("n1")
        self.assertEqual(vc2.to_dict(), {"n1": 1})

    def test_merge(self):
        a = VectorClock({"n1": 2, "n2": 1})
        b = VectorClock({"n1": 1, "n2": 3})
        m = a.merge(b)
        self.assertEqual(m.to_dict(), {"n1": 2, "n2": 3})

    def test_ordering(self):
        a = VectorClock({"n1": 1})
        b = VectorClock({"n1": 2})
        self.assertTrue(a < b)
        self.assertTrue(a <= b)
        self.assertFalse(b < a)

    def test_concurrent(self):
        a = VectorClock({"n1": 2, "n2": 1})
        b = VectorClock({"n1": 1, "n2": 2})
        self.assertTrue(a.concurrent(b))

    def test_roundtrip(self):
        vc = VectorClock({"x": 5})
        self.assertEqual(VectorClock.from_dict(vc.to_dict()).to_dict(), {"x": 5})


class TestGCounter(unittest.TestCase):
    def test_increment_and_value(self):
        gc = GCounter()
        gc.increment("n1", 3)
        gc.increment("n2", 2)
        self.assertEqual(gc.value, 5)

    def test_merge_convergence(self):
        a = GCounter()
        a.increment("n1", 5)
        b = GCounter()
        b.increment("n1", 3)
        b.increment("n2", 2)
        merged = a.merge(b)
        self.assertEqual(merged.value, 7)


class TestLWWRegister(unittest.TestCase):
    def test_set_and_merge(self):
        r = LWWRegister()
        r1 = r.set("hello", "n1", timestamp=1.0)
        r2 = r.set("world", "n2", timestamp=2.0)
        merged = r1.merge(r2)
        self.assertEqual(merged.value, "world")

    def test_same_timestamp_tiebreak(self):
        a = LWWRegister(value="a", timestamp=1.0, node_id="n1")
        b = LWWRegister(value="b", timestamp=1.0, node_id="n2")
        merged = a.merge(b)
        self.assertEqual(merged.value, "b")


class TestConflictResolver(unittest.TestCase):
    def test_lww_resolution(self):
        resolver = ConflictResolver(ConflictResolutionPolicy.LAST_WRITER_WINS)
        local = ReplicatedValue(key="k", value="old", timestamp=1.0, origin_node="n1")
        remote = ReplicatedValue(key="k", value="new", timestamp=2.0, origin_node="n2")
        winner = resolver.resolve(local, remote)
        self.assertEqual(winner.value, "new")

    def test_vector_clock_resolution(self):
        resolver = ConflictResolver(ConflictResolutionPolicy.VECTOR_CLOCK)
        vc_local = VectorClock({"n1": 1})
        vc_remote = VectorClock({"n1": 2})
        local = ReplicatedValue(key="k", value="old", vector_clock=vc_local)
        remote = ReplicatedValue(key="k", value="new", vector_clock=vc_remote)
        winner = resolver.resolve(local, remote)
        self.assertEqual(winner.value, "new")


class TestGeoRouter(unittest.TestCase):
    def test_nearest_nodes(self):
        gr = GeoRouter()
        gr.add_region("us-east", latency_ms=10)
        gr.add_region("eu-west", latency_ms=80)
        gr.assign_node("n1", "us-east")
        gr.assign_node("n2", "eu-west")
        nearest = gr.nearest_nodes("us-east", count=2)
        self.assertEqual(nearest[0], "n1")

    def test_region_for_node(self):
        gr = GeoRouter()
        gr.add_region("r1")
        gr.assign_node("n1", "r1")
        self.assertEqual(gr.region_for_node("n1"), "r1")
        self.assertIsNone(gr.region_for_node("n999"))


# ======================================================================
# Synchronization — QuantumStateSynchronizer
# ======================================================================
class TestQuantumStateSynchronizer(unittest.TestCase):
    def setUp(self):
        self.nm = NodeManager(node_id="n1")
        self.engine = QuantumEngine(num_qubits=2, simulator_type="simulator")
        self.bridge = ClassicalBridge(self.engine)
        self.nm.register_node("n1", "localhost", 5001, is_active=True)
        self.nm.register_node("n2", "localhost", 5002, is_active=True)
        self.sync = QuantumStateSynchronizer(
            self.nm, self.engine, self.bridge,
            consistency=ConsistencyLevel.ONE,
        )

    def test_put_and_get(self):
        rv = self.sync.put("key1", "value1")
        self.assertEqual(rv.key, "key1")
        self.assertEqual(rv.value, "value1")
        self.assertGreater(rv.version, 0)
        fetched = self.sync.get("key1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.value, "value1")

    def test_apply_remote_new_key(self):
        rv = ReplicatedValue(key="rk", value=42, version=1, origin_node="n2",
                             vector_clock=VectorClock({"n2": 1}))
        rv.checksum = rv.compute_checksum()
        applied = self.sync.apply_remote(rv)
        self.assertEqual(applied.value, 42)
        self.assertEqual(self.sync.get("rk").value, 42)

    def test_apply_remote_conflict_lww(self):
        self.sync.put("ck", "local_val")
        remote = ReplicatedValue(
            key="ck", value="remote_val", version=2,
            timestamp=time.time() + 100,
            origin_node="n2",
            vector_clock=VectorClock({"n2": 2}),
        )
        remote.checksum = remote.compute_checksum()
        winner = self.sync.apply_remote(remote)
        self.assertEqual(winner.value, "remote_val")


# ======================================================================
# Query processor — partitioning
# ======================================================================
class TestDataPartitioner(unittest.TestCase):
    def test_hash_partition(self):
        dp = DataPartitioner()
        cfg = PartitionConfig(table="users", strategy=PartitionStrategy.HASH,
                              num_partitions=4)
        dp.configure(cfg)
        part = dp.partition_for_key("users", "alice")
        self.assertIn(part, range(4))

    def test_range_partition(self):
        dp = DataPartitioner()
        cfg = PartitionConfig(table="orders", strategy=PartitionStrategy.RANGE,
                              range_boundaries=[100, 200, 300])
        dp.configure(cfg)
        self.assertEqual(dp.partition_for_key("orders", 50), 0)
        self.assertEqual(dp.partition_for_key("orders", 150), 1)
        self.assertEqual(dp.partition_for_key("orders", 999), 3)

    def test_all_partitions(self):
        dp = DataPartitioner()
        dp.configure(PartitionConfig(table="t", num_partitions=3))
        self.assertEqual(dp.all_partitions("t"), [0, 1, 2])

    def test_unknown_table(self):
        dp = DataPartitioner()
        self.assertEqual(dp.partition_for_key("nope", "x"), 0)
        self.assertEqual(dp.all_partitions("nope"), [0])


class TestDistributedQueryPlanner(unittest.TestCase):
    def setUp(self):
        self.nm = NodeManager(node_id="n1")
        self.nm.register_node("n1", "h", 1)
        self.nm.register_node("n2", "h", 2)

    def test_plan_creates_fragments(self):
        planner = DistributedQueryPlanner(self.nm)
        frags = planner.plan("q1", "SELECT * FROM t")
        self.assertGreater(len(frags), 0)
        self.assertEqual(frags[-1].fragment_type, "merge")

    def test_plan_distributes_across_nodes(self):
        dp = DataPartitioner()
        dp.configure(PartitionConfig(table="t", num_partitions=2))
        planner = DistributedQueryPlanner(self.nm, dp)
        frags = planner.plan("q2", "SELECT * FROM t", table="t")
        targets = [f.target_node for f in frags if f.fragment_type == "scan"]
        self.assertIn("n1", targets)
        self.assertIn("n2", targets)


class TestDistributedJoinPlanner(unittest.TestCase):
    def setUp(self):
        self.nm = NodeManager(node_id="n1")
        self.nm.register_node("n1", "h", 1)
        self.nm.register_node("n2", "h", 2)

    def test_broadcast_join(self):
        planner = DistributedJoinPlanner(self.nm)
        frags = planner.plan_join("q1", "left", "right", "id",
                                  DistributedJoinStrategy.BROADCAST)
        join_frags = [f for f in frags if f.fragment_type == "join"]
        self.assertEqual(len(join_frags), 2)

    def test_colocated_join(self):
        planner = DistributedJoinPlanner(self.nm)
        frags = planner.plan_join("q1", "left", "right", "id",
                                  DistributedJoinStrategy.COLOCATED)
        join_frags = [f for f in frags if f.fragment_type == "join"]
        self.assertEqual(len(join_frags), 1)


class TestDistributedAggregator(unittest.TestCase):
    def test_merge_count_and_sum(self):
        agg = DistributedAggregator()
        agg.add_partial("q1", {"COUNT_rows": 10, "SUM_amount": 100})
        agg.add_partial("q1", {"COUNT_rows": 20, "SUM_amount": 200})
        merged = agg.merge("q1")
        self.assertEqual(merged["COUNT_rows"], 30)
        self.assertEqual(merged["SUM_amount"], 300)

    def test_merge_min_max(self):
        agg = DistributedAggregator()
        agg.add_partial("q1", {"MIN_val": 5, "MAX_val": 50})
        agg.add_partial("q1", {"MIN_val": 2, "MAX_val": 80})
        merged = agg.merge("q1")
        self.assertEqual(merged["MIN_val"], 2)
        self.assertEqual(merged["MAX_val"], 80)

    def test_clear(self):
        agg = DistributedAggregator()
        agg.add_partial("q1", {"COUNT_x": 1})
        agg.clear("q1")
        self.assertEqual(agg.merge("q1"), {})


# ======================================================================
# Query processor — 2PC
# ======================================================================
class TestTwoPhaseCommitCoordinator(unittest.TestCase):
    def setUp(self):
        self.nm = NodeManager(node_id="coord")
        self.nm.register_node("coord", "h", 1)
        self.nm.register_node("p1", "h", 2)
        self.nm.register_node("p2", "h", 3)
        self.tpc = TwoPhaseCommitCoordinator(self.nm)

    def test_begin(self):
        txn = self.tpc.begin()
        self.assertEqual(txn.state, TwoPhaseCommitState.INIT)
        self.assertIn("p1", txn.participants)
        self.assertIn("p2", txn.participants)

    def test_prepare_and_commit(self):
        txn = self.tpc.begin()
        self.assertTrue(self.tpc.prepare(txn.txn_id))
        self.assertEqual(txn.state, TwoPhaseCommitState.PREPARED)
        self.assertTrue(self.tpc.commit(txn.txn_id))
        self.assertEqual(txn.state, TwoPhaseCommitState.COMMITTED)

    def test_abort(self):
        txn = self.tpc.begin()
        self.tpc.prepare(txn.txn_id)
        self.assertTrue(self.tpc.abort(txn.txn_id))
        self.assertEqual(txn.state, TwoPhaseCommitState.ABORTED)

    def test_commit_before_prepare_fails(self):
        txn = self.tpc.begin()
        self.assertFalse(self.tpc.commit(txn.txn_id))

    def test_receive_vote(self):
        txn = self.tpc.begin()
        self.tpc.prepare(txn.txn_id)
        self.tpc.receive_vote(txn.txn_id, "p1", False)
        self.assertFalse(txn.votes["p1"])


# ======================================================================
# Query processor — Deadlock detection
# ======================================================================
class TestDistributedDeadlockDetector(unittest.TestCase):
    def test_no_deadlock(self):
        dd = DistributedDeadlockDetector()
        dd.add_wait("t1", "t2")
        dd.add_wait("t2", "t3")
        self.assertEqual(dd.detect_cycles(), [])

    def test_simple_cycle(self):
        dd = DistributedDeadlockDetector()
        dd.add_wait("t1", "t2")
        dd.add_wait("t2", "t1")
        cycles = dd.detect_cycles()
        self.assertGreater(len(cycles), 0)

    def test_remove_wait_breaks_cycle(self):
        dd = DistributedDeadlockDetector()
        dd.add_wait("t1", "t2")
        dd.add_wait("t2", "t1")
        dd.remove_wait("t1", "t2")
        self.assertEqual(dd.detect_cycles(), [])

    def test_select_victim(self):
        dd = DistributedDeadlockDetector()
        victim = dd.select_victim(["t1", "t2", "t3"])
        self.assertIsNotNone(victim)

    def test_select_victim_empty(self):
        dd = DistributedDeadlockDetector()
        self.assertIsNone(dd.select_victim([]))


# ======================================================================
# Cluster manager
# ======================================================================
class TestHelmValues(unittest.TestCase):
    def test_to_dict_roundtrip(self):
        hv = HelmValues(cluster_name="test-cluster", replicas=5)
        d = hv.to_dict()
        self.assertEqual(d["cluster_name"], "test-cluster")
        self.assertEqual(d["replicas"], 5)

    def test_from_dict(self):
        d = {"cluster_name": "my-c", "namespace": "qndb", "replicas": 3,
             "image": "img", "resources": {}, "storage_class": "standard",
             "storage_size": "10Gi", "qubit_limit": 100, "tls_enabled": True,
             "monitoring_enabled": True, "backup_schedule": "* * * * *",
             "topology": {"replicas": 3, "zones": ["z1"], "min_replicas": 1,
                          "max_replicas": 10, "replication_factor": 3}}
        hv = HelmValues.from_dict(d)
        self.assertEqual(hv.cluster_name, "my-c")
        self.assertEqual(hv.topology.zones, ["z1"])


class TestAutoScaler(unittest.TestCase):
    def setUp(self):
        topo = ClusterTopology(replicas=3, min_replicas=1, max_replicas=10)
        self.scaler = AutoScaler(topo, cooldown_seconds=0)

    def test_scale_up_on_high_utilisation(self):
        result = self.scaler.evaluate(ScalingMetrics(qubit_utilisation=0.9))
        self.assertEqual(result, 4)
        self.assertEqual(self.scaler.current_replicas, 4)

    def test_scale_down_on_low_utilisation(self):
        result = self.scaler.evaluate(ScalingMetrics(qubit_utilisation=0.1))
        self.assertEqual(result, 2)

    def test_no_change_in_normal_range(self):
        result = self.scaler.evaluate(ScalingMetrics(qubit_utilisation=0.5))
        self.assertIsNone(result)

    def test_respects_min_max(self):
        topo = ClusterTopology(replicas=1, min_replicas=1, max_replicas=2)
        scaler = AutoScaler(topo, cooldown_seconds=0)
        scaler.evaluate(ScalingMetrics(qubit_utilisation=0.1))
        self.assertEqual(scaler.current_replicas, 1)

    def test_history_tracked(self):
        self.scaler.evaluate(ScalingMetrics(qubit_utilisation=0.9))
        self.assertEqual(len(self.scaler.history), 1)


class TestRollingUpgradeManager(unittest.TestCase):
    def setUp(self):
        self.nm = NodeManager(node_id="n1")
        self.nm.register_node("n1", "h", 1)
        self.nm.register_node("n2", "h", 2)
        self.upgrade_mgr = RollingUpgradeManager(self.nm)

    def test_start_upgrade(self):
        state = self.upgrade_mgr.start_upgrade("2.0.0")
        self.assertEqual(state.target_version, "2.0.0")
        self.assertEqual(state.phase, UpgradePhase.DRAINING)
        self.assertGreater(len(state.nodes_pending), 0)

    def test_upgrade_next_node(self):
        self.upgrade_mgr.start_upgrade("2.0.0")
        nid = self.upgrade_mgr.upgrade_next_node()
        self.assertIsNotNone(nid)
        self.assertIn(nid, self.upgrade_mgr.state.nodes_upgraded)

    def test_upgrade_completes(self):
        self.upgrade_mgr.start_upgrade("2.0.0")
        while self.upgrade_mgr.upgrade_next_node() is not None:
            pass
        self.assertEqual(self.upgrade_mgr.state.phase, UpgradePhase.COMPLETE)

    def test_rollback(self):
        self.upgrade_mgr.start_upgrade("2.0.0")
        self.assertTrue(self.upgrade_mgr.rollback())
        self.assertEqual(self.upgrade_mgr.state.phase, UpgradePhase.FAILED)


class TestBackupManager(unittest.TestCase):
    def setUp(self):
        self.bm = BackupManager()

    def test_create_backup(self):
        manifest = self.bm.create_backup("n1", {"table1": [1, 2, 3]},
                                         tables=["table1"])
        self.assertEqual(manifest.node_id, "n1")
        self.assertGreater(manifest.size_bytes, 0)
        self.assertNotEqual(manifest.checksum, "")

    def test_list_backups(self):
        self.bm.create_backup("n1", {"a": 1})
        self.bm.create_backup("n2", {"b": 2})
        self.assertEqual(len(self.bm.list_backups()), 2)
        self.assertEqual(len(self.bm.list_backups(node_id="n1")), 1)

    def test_get_latest_backup(self):
        self.bm.create_backup("n1", {"v": 1})
        m2 = self.bm.create_backup("n1", {"v": 2})
        latest = self.bm.get_latest_backup("n1")
        self.assertEqual(latest.backup_id, m2.backup_id)

    def test_restore_backup(self):
        m = self.bm.create_backup("n1", {"x": 1})
        restored = self.bm.restore_backup(m.backup_id)
        self.assertIsNotNone(restored)
        self.assertIsNone(self.bm.restore_backup("fake-id"))

    def test_prune_old_backups(self):
        for i in range(7):
            self.bm.create_backup("n1", {"i": i})
        pruned = self.bm.prune_old_backups(keep=3, node_id="n1")
        self.assertEqual(pruned, 4)
        self.assertEqual(len(self.bm.list_backups(node_id="n1")), 3)


class TestClusterManager(unittest.TestCase):
    def setUp(self):
        self.nm = NodeManager(node_id="n1")
        self.nm.register_node("n1", "localhost", 5000)
        self.cm = ClusterManager(self.nm)

    def test_add_and_remove_node(self):
        cn = self.cm.add_node("n2", "localhost", 5001)
        self.assertEqual(cn.node_id, "n2")
        self.assertIn("n2", self.nm.nodes)
        self.assertTrue(self.cm.remove_node("n2"))
        self.assertIsNone(self.cm.get_node("n2"))

    def test_cluster_status(self):
        self.cm.add_node("n2", "localhost", 5001)
        status = self.cm.cluster_status()
        self.assertEqual(status["cluster_name"], "qndb-cluster")
        self.assertEqual(status["total_nodes"], 1)

    def test_evaluate_scaling(self):
        self.cm.auto_scaler.cooldown = 0
        result = self.cm.evaluate_scaling(ScalingMetrics(qubit_utilisation=0.9))
        self.assertIsNotNone(result)

    def test_backup_cluster(self):
        manifest = self.cm.backup_cluster({"users": [1, 2, 3]})
        self.assertIsNotNone(manifest)
        self.assertGreater(manifest.size_bytes, 0)


if __name__ == "__main__":
    unittest.main()
