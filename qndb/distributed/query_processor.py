"""
Distributed Query Processing

Handles query fragmentation, distributed joins, distributed aggregation,
two-phase commit, distributed deadlock detection, and data partitioning.
"""

import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Data partitioning strategies ──────────────────────────────────────
class PartitionStrategy(Enum):
    HASH = "hash"
    RANGE = "range"
    QUANTUM_AWARE = "quantum_aware"


@dataclass
class PartitionConfig:
    """Configuration for a table partition."""
    table: str
    strategy: PartitionStrategy = PartitionStrategy.HASH
    partition_key: str = "id"
    num_partitions: int = 4
    range_boundaries: List[Any] = field(default_factory=list)


class DataPartitioner:
    """Assigns rows to partitions based on the configured strategy."""

    def __init__(self) -> None:
        self._configs: Dict[str, PartitionConfig] = {}

    def configure(self, config: PartitionConfig) -> None:
        self._configs[config.table] = config

    def partition_for_key(self, table: str, key_value: Any) -> int:
        cfg = self._configs.get(table)
        if cfg is None:
            return 0
        if cfg.strategy == PartitionStrategy.HASH:
            h = int(hashlib.md5(str(key_value).encode()).hexdigest(), 16)
            return h % cfg.num_partitions
        elif cfg.strategy == PartitionStrategy.RANGE:
            for i, boundary in enumerate(cfg.range_boundaries):
                if key_value < boundary:
                    return i
            return len(cfg.range_boundaries)
        return 0  # quantum_aware fallback

    def all_partitions(self, table: str) -> List[int]:
        cfg = self._configs.get(table)
        n = cfg.num_partitions if cfg else 1
        return list(range(n))


# ── Query fragment ────────────────────────────────────────────────────
@dataclass
class QueryFragment:
    """A piece of a distributed query to be executed on one node."""
    fragment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query_id: str = ""
    sql: str = ""
    target_node: str = ""
    partition_id: int = 0
    fragment_type: str = "scan"   # scan, join, aggregate, merge
    status: str = "pending"       # pending, running, completed, failed
    result: Any = None
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fragment_id": self.fragment_id,
            "query_id": self.query_id,
            "sql": self.sql,
            "target_node": self.target_node,
            "partition_id": self.partition_id,
            "fragment_type": self.fragment_type,
            "status": self.status,
        }


# ── Distributed query planner ────────────────────────────────────────
class DistributedQueryPlanner:
    """Fragments a query and assigns fragments to cluster nodes."""

    def __init__(self, node_manager, partitioner: Optional[DataPartitioner] = None):
        self.node_manager = node_manager
        self.partitioner = partitioner or DataPartitioner()

    def plan(self, query_id: str, sql: str,
             table: str = "") -> List[QueryFragment]:
        """Create query fragments distributed across nodes."""
        nodes = self.node_manager.get_active_nodes()
        if not nodes:
            return []

        partitions = self.partitioner.all_partitions(table) if table else [0]
        fragments: List[QueryFragment] = []

        for i, part_id in enumerate(partitions):
            target = nodes[i % len(nodes)]
            frag = QueryFragment(
                query_id=query_id, sql=sql,
                target_node=target.id, partition_id=part_id,
                fragment_type="scan",
            )
            fragments.append(frag)

        # Add merge fragment on coordinator
        merge = QueryFragment(
            query_id=query_id, sql="",
            target_node=self.node_manager.local_node_id,
            fragment_type="merge",
        )
        fragments.append(merge)
        return fragments


# ── Distributed join ──────────────────────────────────────────────────
class DistributedJoinStrategy(Enum):
    BROADCAST = "broadcast"
    HASH_PARTITION = "hash_partition"
    COLOCATED = "colocated"


class DistributedJoinPlanner:
    """Plans distributed join operations."""

    def __init__(self, node_manager, partitioner: Optional[DataPartitioner] = None):
        self.node_manager = node_manager
        self.partitioner = partitioner or DataPartitioner()

    def plan_join(self, query_id: str,
                  left_table: str, right_table: str,
                  join_key: str,
                  strategy: DistributedJoinStrategy = DistributedJoinStrategy.HASH_PARTITION
                  ) -> List[QueryFragment]:
        nodes = self.node_manager.get_active_nodes()
        if not nodes:
            return []
        fragments: List[QueryFragment] = []

        if strategy == DistributedJoinStrategy.BROADCAST:
            # Broadcast smaller table to all nodes executing the larger table
            for node in nodes:
                frag = QueryFragment(
                    query_id=query_id,
                    sql=f"JOIN {left_table} WITH {right_table} ON {join_key}",
                    target_node=node.id,
                    fragment_type="join",
                )
                fragments.append(frag)
        elif strategy == DistributedJoinStrategy.HASH_PARTITION:
            partitions = self.partitioner.all_partitions(left_table)
            for i, part_id in enumerate(partitions):
                target = nodes[i % len(nodes)]
                frag = QueryFragment(
                    query_id=query_id,
                    sql=f"HASH_JOIN {left_table}[{part_id}] WITH {right_table}[{part_id}] ON {join_key}",
                    target_node=target.id,
                    partition_id=part_id,
                    fragment_type="join",
                )
                fragments.append(frag)
        elif strategy == DistributedJoinStrategy.COLOCATED:
            frag = QueryFragment(
                query_id=query_id,
                sql=f"COLOCATED_JOIN {left_table} WITH {right_table} ON {join_key}",
                target_node=self.node_manager.local_node_id,
                fragment_type="join",
            )
            fragments.append(frag)

        # merge
        merge = QueryFragment(
            query_id=query_id, sql="",
            target_node=self.node_manager.local_node_id,
            fragment_type="merge",
        )
        fragments.append(merge)
        return fragments


# ── Distributed aggregation ───────────────────────────────────────────
class DistributedAggregator:
    """Collects partial aggregation results from nodes and merges them."""

    def __init__(self) -> None:
        self._partials: Dict[str, List[Dict[str, Any]]] = {}

    def add_partial(self, query_id: str, partial: Dict[str, Any]) -> None:
        self._partials.setdefault(query_id, []).append(partial)

    def merge(self, query_id: str) -> Dict[str, Any]:
        partials = self._partials.get(query_id, [])
        if not partials:
            return {}

        merged: Dict[str, Any] = {}
        for p in partials:
            for key, val in p.items():
                if key.startswith("COUNT"):
                    merged[key] = merged.get(key, 0) + val
                elif key.startswith("SUM"):
                    merged[key] = merged.get(key, 0) + val
                elif key.startswith("MIN"):
                    if key not in merged or val < merged[key]:
                        merged[key] = val
                elif key.startswith("MAX"):
                    if key not in merged or val > merged[key]:
                        merged[key] = val
                elif key.startswith("AVG"):
                    # need count+sum — callers should provide SUM/COUNT pairs
                    merged.setdefault(key, [])
                    merged[key].append(val)
                else:
                    merged[key] = val
        return merged

    def clear(self, query_id: str) -> None:
        self._partials.pop(query_id, None)


# ── Two-phase commit (2PC) ───────────────────────────────────────────
class TwoPhaseCommitState(Enum):
    INIT = "INIT"
    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"


@dataclass
class TwoPhaseTransaction:
    txn_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: TwoPhaseCommitState = TwoPhaseCommitState.INIT
    participants: List[str] = field(default_factory=list)
    votes: Dict[str, bool] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    timeout: float = 10.0


class TwoPhaseCommitCoordinator:
    """Coordinates distributed transactions via 2PC."""

    def __init__(self, node_manager):
        self.node_manager = node_manager
        self._transactions: Dict[str, TwoPhaseTransaction] = {}
        self._lock = threading.Lock()

    def begin(self, participants: Optional[List[str]] = None) -> TwoPhaseTransaction:
        txn = TwoPhaseTransaction()
        if participants is None:
            participants = [n.id for n in self.node_manager.get_active_nodes()
                            if n.id != self.node_manager.local_node_id]
        txn.participants = list(participants)
        with self._lock:
            self._transactions[txn.txn_id] = txn
        return txn

    def prepare(self, txn_id: str) -> bool:
        """Send PREPARE to all participants and collect votes."""
        with self._lock:
            txn = self._transactions.get(txn_id)
        if txn is None:
            return False

        msg = {
            "type": "TWO_PHASE_PREPARE",
            "txn_id": txn_id,
            "coordinator": self.node_manager.local_node_id,
        }
        for pid in txn.participants:
            self.node_manager.send_message(pid, msg)

        # In a real system we'd wait for responses; here we optimistically
        # record votes as True (the handler will send actual votes)
        for pid in txn.participants:
            txn.votes[pid] = True

        txn.state = TwoPhaseCommitState.PREPARED
        return True

    def commit(self, txn_id: str) -> bool:
        with self._lock:
            txn = self._transactions.get(txn_id)
        if txn is None or txn.state != TwoPhaseCommitState.PREPARED:
            return False

        if not all(txn.votes.get(pid, False) for pid in txn.participants):
            return self.abort(txn_id)

        msg = {"type": "TWO_PHASE_COMMIT", "txn_id": txn_id,
               "coordinator": self.node_manager.local_node_id}
        for pid in txn.participants:
            self.node_manager.send_message(pid, msg)

        txn.state = TwoPhaseCommitState.COMMITTED
        return True

    def abort(self, txn_id: str) -> bool:
        with self._lock:
            txn = self._transactions.get(txn_id)
        if txn is None:
            return False

        msg = {"type": "TWO_PHASE_ABORT", "txn_id": txn_id,
               "coordinator": self.node_manager.local_node_id}
        for pid in txn.participants:
            self.node_manager.send_message(pid, msg)

        txn.state = TwoPhaseCommitState.ABORTED
        return True

    def receive_vote(self, txn_id: str, participant: str, vote: bool) -> None:
        with self._lock:
            txn = self._transactions.get(txn_id)
        if txn:
            txn.votes[participant] = vote

    def get_transaction(self, txn_id: str) -> Optional[TwoPhaseTransaction]:
        return self._transactions.get(txn_id)


# ── Distributed deadlock detection ────────────────────────────────────
class DistributedDeadlockDetector:
    """Builds a cluster-wide wait-for graph and detects cycles."""

    def __init__(self) -> None:
        self._wait_for: Dict[str, Set[str]] = {}
        self._lock = threading.Lock()

    def add_wait(self, waiter: str, holder: str) -> None:
        with self._lock:
            self._wait_for.setdefault(waiter, set()).add(holder)

    def remove_wait(self, waiter: str, holder: Optional[str] = None) -> None:
        with self._lock:
            if holder:
                s = self._wait_for.get(waiter)
                if s:
                    s.discard(holder)
            else:
                self._wait_for.pop(waiter, None)

    def detect_cycles(self) -> List[List[str]]:
        """Return all cycles in the wait-for graph."""
        with self._lock:
            graph = {k: set(v) for k, v in self._wait_for.items()}

        cycles: List[List[str]] = []
        visited: Set[str] = set()

        def dfs(node: str, path: List[str], on_stack: Set[str]) -> None:
            visited.add(node)
            on_stack.add(node)
            path.append(node)
            for neighbour in graph.get(node, set()):
                if neighbour in on_stack:
                    idx = path.index(neighbour)
                    cycles.append(list(path[idx:]))
                elif neighbour not in visited:
                    dfs(neighbour, path, on_stack)
            path.pop()
            on_stack.discard(node)

        for node in list(graph.keys()):
            if node not in visited:
                dfs(node, [], set())

        return cycles

    def select_victim(self, cycle: List[str]) -> Optional[str]:
        """Select youngest transaction as deadlock victim."""
        if not cycle:
            return None
        return cycle[-1]  # youngest = last added

    @property
    def has_deadlock(self) -> bool:
        return len(self.detect_cycles()) > 0


# ── Distributed query executor ────────────────────────────────────────
class DistributedQueryExecutor:
    """Orchestrates distributed query execution across the cluster."""

    def __init__(self, node_manager,
                 partitioner: Optional[DataPartitioner] = None):
        self.node_manager = node_manager
        self.planner = DistributedQueryPlanner(node_manager, partitioner)
        self.join_planner = DistributedJoinPlanner(node_manager, partitioner)
        self.aggregator = DistributedAggregator()
        self.deadlock_detector = DistributedDeadlockDetector()
        self.two_pc = TwoPhaseCommitCoordinator(node_manager)
        self._results: Dict[str, List[Any]] = {}

    def execute_query(self, sql: str, table: str = "") -> str:
        """Fragment, distribute, and begin executing a query.

        Returns the query_id.  Results are collected asynchronously and
        can be retrieved via :meth:`get_results`.
        """
        query_id = str(uuid.uuid4())
        fragments = self.planner.plan(query_id, sql, table)

        for frag in fragments:
            if frag.fragment_type == "merge":
                continue
            self.node_manager.send_message(frag.target_node, {
                "type": "QUERY_FRAGMENT",
                "fragment": frag.to_dict(),
            })
            frag.status = "running"

        self._results[query_id] = []
        return query_id

    def receive_result(self, query_id: str, fragment_id: str,
                       result: Any) -> None:
        self._results.setdefault(query_id, []).append(result)

    def get_results(self, query_id: str) -> List[Any]:
        return self._results.get(query_id, [])

    def execute_distributed_join(self, left_table: str, right_table: str,
                                 join_key: str,
                                 strategy: DistributedJoinStrategy =
                                 DistributedJoinStrategy.HASH_PARTITION
                                 ) -> str:
        query_id = str(uuid.uuid4())
        fragments = self.join_planner.plan_join(
            query_id, left_table, right_table, join_key, strategy)
        for frag in fragments:
            if frag.fragment_type == "merge":
                continue
            self.node_manager.send_message(frag.target_node, {
                "type": "QUERY_FRAGMENT",
                "fragment": frag.to_dict(),
            })
        self._results[query_id] = []
        return query_id

    def execute_with_2pc(self, sql: str, table: str = "") -> Tuple[str, str]:
        """Execute a write query under 2PC.

        Returns (query_id, txn_id).
        """
        txn = self.two_pc.begin()
        query_id = self.execute_query(sql, table)
        self.two_pc.prepare(txn.txn_id)
        self.two_pc.commit(txn.txn_id)
        return query_id, txn.txn_id
