"""
Distributed node management for quantum database system.

Features:
- Transport-layer integration (gRPC-style channels)
- Service discovery integration
- Health checking via phi-accrual failure detector
- Membership change protocol
- Resource tracking per node
"""
from typing import List, Dict, Tuple, Optional, Union, Set, Any, Callable
import uuid
import logging
import threading
import time
import json
import hashlib

from qndb.distributed.networking import (
    TransportLayer, TransportChannel, ServiceDiscovery, ServiceRecord,
    PartitionDetector, PhiAccrualFailureDetector, NodeHealth, PartitionState,
    TLSConfig, RPCRequest, RPCResponse,
)

logger = logging.getLogger(__name__)


class Node:
    """Represents a node in the distributed quantum database cluster."""

    def __init__(self, node_id: str, host: str, port: int,
                 is_active: bool = True):
        self.id = node_id
        self.host = host
        self.port = port
        self.is_active = is_active
        self.last_sync_time = time.time()
        self.message_queue: List[Dict] = []
        self.metadata: Dict[str, str] = {}
        self.resources: Dict[str, Any] = {"qubits": 0, "qubits_available": 0}
        self.joined_at: float = time.time()

    def __str__(self):
        return (f"Node({self.id}, {self.host}:{self.port}, "
                f"{'active' if self.is_active else 'inactive'})")

    def __repr__(self):
        return self.__str__()

    def send_message(self, message_type, message_data=None):
        message = {
            "type": message_type,
            "data": message_data,
            "timestamp": time.time(),
        }
        self.message_queue.append(message)
        return {"status": "success", "has_updates": False,
                "message": f"Processed {message_type} message"}

    def receive_messages(self):
        messages = list(self.message_queue)
        self.message_queue.clear()
        return messages


class NodeManager:
    """Manages distributed nodes in a quantum database cluster.

    Phase-5 enhancements
    --------------------
    * Integrated :class:`TransportLayer` for gRPC-style messaging
    * :class:`ServiceDiscovery` for peer registration / lookup
    * :class:`PartitionDetector` for network-partition awareness
    * Membership change protocol (add / remove with cluster agreement)
    * Per-node resource tracking
    """

    def __init__(self, node_id: Optional[str] = None,
                 is_leader: bool = False,
                 host: str = "localhost",
                 port: int = 5000,
                 tls_config: Optional[TLSConfig] = None):
        self.local_node_id = node_id or str(uuid.uuid4())
        self.is_leader = is_leader
        self.host = host
        self.port = port
        self.nodes: Dict[str, Node] = {}
        self.lock = threading.RLock()

        # Networking sub-systems
        self.transport = TransportLayer(self.local_node_id, tls_config)
        self.discovery = ServiceDiscovery()
        self.partition_detector = PartitionDetector()
        self.tls_config = tls_config

        # Current node reference (set via register_node or auto-created)
        self.current_node: Optional[Node] = None

        # Membership version (monotonically increasing)
        self._membership_version: int = 0

        # Callbacks
        self._on_node_join: List[Callable[[Node], None]] = []
        self._on_node_leave: List[Callable[[str], None]] = []

        logger.info("NodeManager initialised (id=%s)", self.local_node_id)

    # ------------------------------------------------------------------
    # Resource helpers
    # ------------------------------------------------------------------
    def _get_resources(self) -> Dict[str, Any]:
        return {"qubits": 100, "qubits_available": 100}

    # ------------------------------------------------------------------
    # Node registration (backward compat + new transport integration)
    # ------------------------------------------------------------------
    def register_node(self, node_id: str, host: str, port: int,
                      is_active: bool = True,
                      metadata: Optional[Dict[str, str]] = None) -> Node:
        node = Node(node_id, host, port, is_active)
        node.metadata = metadata or {}
        with self.lock:
            self.nodes[node_id] = node
            self._membership_version += 1

        # Also register with discovery + partition detector + open channel
        self.discovery.register(node_id, host, port,
                                metadata=node.metadata)
        if node_id != self.local_node_id:
            self.partition_detector.register_peer(node_id)
            self.transport.connect(node_id)

        if node_id == self.local_node_id:
            self.current_node = node

        for cb in self._on_node_join:
            try:
                cb(node)
            except Exception:
                logger.exception("on_node_join callback error")

        logger.info("Registered node %s at %s:%d", node_id, host, port)
        return node

    def deregister_node(self, node_id: str) -> bool:
        with self.lock:
            node = self.nodes.pop(node_id, None)
            if node is None:
                return False
            self._membership_version += 1

        self.discovery.deregister(node_id)
        self.partition_detector.remove_peer(node_id)
        self.transport.disconnect(node_id)

        for cb in self._on_node_leave:
            try:
                cb(node_id)
            except Exception:
                logger.exception("on_node_leave callback error")

        logger.info("Deregistered node %s", node_id)
        return True

    # ------------------------------------------------------------------
    # Legacy query helpers
    # ------------------------------------------------------------------
    def get_active_nodes(self) -> List[Node]:
        return [n for n in self.nodes.values() if n.is_active]

    def get_all_nodes(self) -> List[Node]:
        return list(self.nodes.values())

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

    def mark_node_inactive(self, node_id: str) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].is_active = False

    def mark_node_active(self, node_id: str) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].is_active = True

    # ------------------------------------------------------------------
    # Transport helpers (message passing via channels)
    # ------------------------------------------------------------------
    def send_message(self, target_id: str, message: Dict[str, Any]) -> bool:
        method = message.get("type", "generic")
        return self.transport.send(target_id, method, message)

    def broadcast_message(self, message: Dict[str, Any],
                          exclude: Optional[Set[str]] = None) -> int:
        method = message.get("type", "generic")
        exclude = (exclude or set()) | {self.local_node_id}
        return self.transport.broadcast(method, message, exclude=exclude)

    def get_messages(self) -> List[Dict[str, Any]]:
        """Retrieve all pending messages from all channels."""
        items = self.transport.poll()
        return [req.payload for (_rid, req) in items]

    # ------------------------------------------------------------------
    # Health / partition
    # ------------------------------------------------------------------
    def record_heartbeat(self, peer_id: str) -> None:
        self.partition_detector.record_heartbeat(peer_id)
        if peer_id in self.nodes:
            self.nodes[peer_id].last_sync_time = time.time()

    def peer_health(self, peer_id: str) -> NodeHealth:
        return self.partition_detector.peer_health(peer_id)

    @property
    def partition_state(self) -> PartitionState:
        return self.partition_detector.partition_state

    @property
    def has_quorum(self) -> bool:
        return self.partition_detector.has_quorum

    @property
    def membership_version(self) -> int:
        return self._membership_version

    # ------------------------------------------------------------------
    # Membership change protocol
    # ------------------------------------------------------------------
    def propose_add_node(self, node_id: str, host: str, port: int) -> bool:
        """Propose adding a node (broadcasts to cluster for agreement)."""
        self.broadcast_message({
            "type": "MEMBERSHIP_CHANGE",
            "action": "ADD",
            "node_id": node_id,
            "host": host,
            "port": port,
            "proposer": self.local_node_id,
            "version": self._membership_version,
        })
        # Optimistically apply locally
        self.register_node(node_id, host, port, is_active=True)
        return True

    def propose_remove_node(self, node_id: str) -> bool:
        """Propose removing a node from the cluster."""
        self.broadcast_message({
            "type": "MEMBERSHIP_CHANGE",
            "action": "REMOVE",
            "node_id": node_id,
            "proposer": self.local_node_id,
            "version": self._membership_version,
        })
        self.deregister_node(node_id)
        return True

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def on_node_join(self, callback: Callable[[Node], None]) -> None:
        self._on_node_join.append(callback)

    def on_node_leave(self, callback: Callable[[str], None]) -> None:
        self._on_node_leave.append(callback)

    # ------------------------------------------------------------------
    # Qubit transfer (quantum-specific, simulated)
    # ------------------------------------------------------------------
    def send_qubit(self, target_id: str, qubit: Any) -> bool:
        """Send a qubit reference to a target node (simulated)."""
        return self.send_message(target_id, {
            "type": "QUBIT_TRANSFER",
            "qubit": str(qubit),
            "sender": self.local_node_id,
        })

    # ------------------------------------------------------------------
    # Cluster summary
    # ------------------------------------------------------------------
    def cluster_info(self) -> Dict[str, Any]:
        return {
            "local_node_id": self.local_node_id,
            "membership_version": self._membership_version,
            "total_nodes": len(self.nodes),
            "active_nodes": len(self.get_active_nodes()),
            "partition_state": self.partition_state.value,
            "has_quorum": self.has_quorum,
            "nodes": {nid: str(n) for nid, n in self.nodes.items()},
        }