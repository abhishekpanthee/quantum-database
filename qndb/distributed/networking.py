"""
Networking layer for the distributed quantum database.

Provides gRPC-style transport abstraction, node discovery, health checking,
mutual TLS authentication, and network partition detection.
"""

import time
import enum
import hashlib
import json
import struct
import logging
import threading
import socket
import ssl
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Set, Tuple

logger = logging.getLogger(__name__)

# ── Wire protocol constants ──────────────────────────────────────────
PROTO_VERSION = 1
HEADER_FMT = "!BBI"          # version (1B), msg_type (1B), length (4B)
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# Message types
MSG_HEARTBEAT      = 0x01
MSG_VOTE_REQUEST   = 0x02
MSG_VOTE_RESPONSE  = 0x03
MSG_APPEND_ENTRIES = 0x04
MSG_APPEND_RESP    = 0x05
MSG_CLIENT_REQ     = 0x06
MSG_CLIENT_RESP    = 0x07
MSG_STATE_TRANSFER = 0x08
MSG_DISCOVERY      = 0x09
MSG_PARTITION_PROBE = 0x0A
MSG_QUERY_FRAGMENT = 0x0B
MSG_QUERY_RESULT   = 0x0C
MSG_TWO_PHASE_PREP = 0x0D
MSG_TWO_PHASE_ACK  = 0x0E
MSG_CLUSTER_CMD    = 0x0F


def encode_message(msg_type: int, payload: bytes) -> bytes:
    """Encode a message with the wire protocol header."""
    header = struct.pack(HEADER_FMT, PROTO_VERSION, msg_type, len(payload))
    return header + payload


def decode_header(data: bytes) -> Tuple[int, int, int]:
    """Decode a wire protocol header → (version, msg_type, payload_length)."""
    if len(data) < HEADER_SIZE:
        raise ValueError("Incomplete header")
    return struct.unpack(HEADER_FMT, data[:HEADER_SIZE])


# ── Node health states ───────────────────────────────────────────────
class NodeHealth(enum.Enum):
    HEALTHY = "healthy"
    SUSPECT = "suspect"
    UNREACHABLE = "unreachable"
    DEAD = "dead"


class PartitionState(enum.Enum):
    CONNECTED = "connected"
    PARTIAL = "partial"
    PARTITIONED = "partitioned"


# ── TLS configuration ────────────────────────────────────────────────
@dataclass
class TLSConfig:
    """Mutual TLS configuration for inter-node communication."""
    enabled: bool = False
    cert_file: Optional[str] = None
    key_file: Optional[str] = None
    ca_file: Optional[str] = None
    verify_peer: bool = True
    min_version: str = "TLSv1.3"

    def create_server_context(self) -> Optional[ssl.SSLContext]:
        if not self.enabled:
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        if self.cert_file and self.key_file:
            ctx.load_cert_chain(self.cert_file, self.key_file)
        if self.ca_file:
            ctx.load_verify_locations(self.ca_file)
        if self.verify_peer:
            ctx.verify_mode = ssl.CERT_REQUIRED
        return ctx

    def create_client_context(self) -> Optional[ssl.SSLContext]:
        if not self.enabled:
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        if self.cert_file and self.key_file:
            ctx.load_cert_chain(self.cert_file, self.key_file)
        if self.ca_file:
            ctx.load_verify_locations(self.ca_file)
        ctx.check_hostname = False
        if self.verify_peer:
            ctx.verify_mode = ssl.CERT_REQUIRED
        else:
            ctx.verify_mode = ssl.CERT_NONE
        return ctx


# ── Phi-accrual failure detector ─────────────────────────────────────
class PhiAccrualFailureDetector:
    """Phi-accrual failure detector for adaptive health checking.

    Tracks heartbeat intervals and computes a suspicion level (phi).
    When phi > threshold the node is considered suspect/dead.
    """

    def __init__(self, threshold: float = 8.0, max_samples: int = 200,
                 min_std_dev_ms: float = 100.0):
        self.threshold = threshold
        self.max_samples = max_samples
        self.min_std_dev_ms = min_std_dev_ms
        self._intervals: List[float] = []
        self._last_heartbeat: Optional[float] = None

    def heartbeat(self) -> None:
        now = time.time()
        if self._last_heartbeat is not None:
            interval = (now - self._last_heartbeat) * 1000  # ms
            self._intervals.append(interval)
            if len(self._intervals) > self.max_samples:
                self._intervals = self._intervals[-self.max_samples:]
        self._last_heartbeat = now

    def phi(self) -> float:
        if self._last_heartbeat is None or len(self._intervals) < 2:
            return 0.0
        elapsed_ms = (time.time() - self._last_heartbeat) * 1000
        mean = sum(self._intervals) / len(self._intervals)
        variance = sum((x - mean) ** 2 for x in self._intervals) / len(self._intervals)
        std_dev = max(variance ** 0.5, self.min_std_dev_ms)
        # Approximate phi using exponential CDF
        y = (elapsed_ms - mean) / std_dev
        import math
        try:
            p = 1.0 / (1.0 + math.exp(-y))
            return -math.log10(1.0 - p + 1e-12)
        except (OverflowError, ValueError):
            return float('inf')

    @property
    def is_available(self) -> bool:
        return self.phi() < self.threshold


# ── Service discovery ─────────────────────────────────────────────────
@dataclass
class ServiceRecord:
    """A discovered service endpoint."""
    node_id: str
    host: str
    port: int
    metadata: Dict[str, str] = field(default_factory=dict)
    ttl: float = 30.0
    registered_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return time.time() - self.registered_at > self.ttl


class ServiceDiscovery:
    """DNS-SD / Consul-style service discovery.

    Nodes register themselves and discover peers via a local registry
    (in-process for single-host testing, backed by a real service
    registry in production).
    """

    def __init__(self, service_name: str = "qndb"):
        self.service_name = service_name
        self._registry: Dict[str, ServiceRecord] = {}
        self._lock = threading.Lock()
        self._watchers: List[Callable[[str, ServiceRecord, str], None]] = []

    def register(self, node_id: str, host: str, port: int,
                 metadata: Optional[Dict[str, str]] = None,
                 ttl: float = 30.0) -> ServiceRecord:
        record = ServiceRecord(node_id=node_id, host=host, port=port,
                               metadata=metadata or {}, ttl=ttl)
        with self._lock:
            self._registry[node_id] = record
        self._notify("register", record)
        logger.info("Registered service %s at %s:%d", node_id, host, port)
        return record

    def deregister(self, node_id: str) -> bool:
        with self._lock:
            rec = self._registry.pop(node_id, None)
        if rec:
            self._notify("deregister", rec)
            return True
        return False

    def discover(self, healthy_only: bool = True) -> List[ServiceRecord]:
        with self._lock:
            records = list(self._registry.values())
        if healthy_only:
            records = [r for r in records if not r.is_expired]
        return records

    def get(self, node_id: str) -> Optional[ServiceRecord]:
        with self._lock:
            return self._registry.get(node_id)

    def add_watcher(self, callback: Callable[[str, ServiceRecord, str], None]) -> None:
        self._watchers.append(callback)

    def _notify(self, event: str, record: ServiceRecord) -> None:
        for cb in self._watchers:
            try:
                cb(self.service_name, record, event)
            except Exception:
                logger.exception("Watcher callback failed")

    def prune_expired(self) -> int:
        expired: List[str] = []
        with self._lock:
            for nid, rec in self._registry.items():
                if rec.is_expired:
                    expired.append(nid)
            for nid in expired:
                del self._registry[nid]
        for nid in expired:
            logger.info("Pruned expired service record for %s", nid)
        return len(expired)


# ── Network partition detector ────────────────────────────────────────
class PartitionDetector:
    """Detects network partitions by monitoring connectivity to peers.

    Each peer is tracked via a :class:`PhiAccrualFailureDetector`.
    The overall cluster partition state is derived from the fraction
    of reachable peers.
    """

    def __init__(self, quorum_fraction: float = 0.5,
                 phi_threshold: float = 8.0):
        self.quorum_fraction = quorum_fraction
        self.phi_threshold = phi_threshold
        self._detectors: Dict[str, PhiAccrualFailureDetector] = {}
        self._lock = threading.Lock()

    def register_peer(self, peer_id: str) -> None:
        with self._lock:
            if peer_id not in self._detectors:
                self._detectors[peer_id] = PhiAccrualFailureDetector(
                    threshold=self.phi_threshold)

    def remove_peer(self, peer_id: str) -> None:
        with self._lock:
            self._detectors.pop(peer_id, None)

    def record_heartbeat(self, peer_id: str) -> None:
        with self._lock:
            det = self._detectors.get(peer_id)
        if det:
            det.heartbeat()

    def peer_health(self, peer_id: str) -> NodeHealth:
        with self._lock:
            det = self._detectors.get(peer_id)
        if det is None:
            return NodeHealth.DEAD
        phi = det.phi()
        if phi < self.phi_threshold * 0.5:
            return NodeHealth.HEALTHY
        if phi < self.phi_threshold:
            return NodeHealth.SUSPECT
        return NodeHealth.UNREACHABLE

    def reachable_peers(self) -> List[str]:
        with self._lock:
            peers = list(self._detectors.keys())
        return [p for p in peers
                if self.peer_health(p) in (NodeHealth.HEALTHY, NodeHealth.SUSPECT)]

    def unreachable_peers(self) -> List[str]:
        with self._lock:
            peers = list(self._detectors.keys())
        return [p for p in peers
                if self.peer_health(p) in (NodeHealth.UNREACHABLE, NodeHealth.DEAD)]

    @property
    def partition_state(self) -> PartitionState:
        with self._lock:
            total = len(self._detectors)
        if total == 0:
            return PartitionState.CONNECTED
        reachable = len(self.reachable_peers())
        ratio = reachable / total
        if ratio >= 1.0:
            return PartitionState.CONNECTED
        if ratio >= self.quorum_fraction:
            return PartitionState.PARTIAL
        return PartitionState.PARTITIONED

    @property
    def has_quorum(self) -> bool:
        return self.partition_state != PartitionState.PARTITIONED


# ── gRPC-style transport abstraction ─────────────────────────────────
@dataclass
class RPCRequest:
    """An RPC request envelope."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    method: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    sender_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class RPCResponse:
    """An RPC response envelope."""
    request_id: str = ""
    success: bool = True
    payload: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    sender_id: str = ""
    timestamp: float = field(default_factory=time.time)


class TransportChannel:
    """In-process gRPC-style transport channel between two nodes.

    In production this would be backed by a real gRPC or TCP channel.
    For testing / single-host deployments it uses in-memory queues.
    """

    def __init__(self, local_id: str, remote_id: str,
                 tls_config: Optional[TLSConfig] = None):
        self.local_id = local_id
        self.remote_id = remote_id
        self.tls_config = tls_config
        self._inbox: List[RPCRequest] = []
        self._outbox: List[RPCRequest] = []
        self._lock = threading.Lock()
        self._connected = True
        self._bytes_sent: int = 0
        self._bytes_received: int = 0
        self._messages_sent: int = 0
        self._messages_received: int = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    def send(self, request: RPCRequest) -> bool:
        if not self._connected:
            return False
        with self._lock:
            payload_size = len(json.dumps(request.payload).encode())
            self._outbox.append(request)
            self._bytes_sent += payload_size
            self._messages_sent += 1
        return True

    def receive(self) -> List[RPCRequest]:
        with self._lock:
            msgs = list(self._inbox)
            for m in msgs:
                self._bytes_received += len(json.dumps(m.payload).encode())
                self._messages_received += 1
            self._inbox.clear()
        return msgs

    def deliver(self, request: RPCRequest) -> None:
        """Deliver a message *into* this channel's inbox (called by transport layer)."""
        with self._lock:
            self._inbox.append(request)

    def close(self) -> None:
        self._connected = False

    def stats(self) -> Dict[str, Any]:
        return {
            "local_id": self.local_id,
            "remote_id": self.remote_id,
            "connected": self._connected,
            "bytes_sent": self._bytes_sent,
            "bytes_received": self._bytes_received,
            "messages_sent": self._messages_sent,
            "messages_received": self._messages_received,
        }


class TransportLayer:
    """Manages all transport channels for a single node.

    Acts as a multiplexer: RPC handlers are registered by method name
    and dispatched when messages arrive.
    """

    def __init__(self, node_id: str, tls_config: Optional[TLSConfig] = None):
        self.node_id = node_id
        self.tls_config = tls_config
        self._channels: Dict[str, TransportChannel] = {}
        self._handlers: Dict[str, Callable[[RPCRequest], RPCResponse]] = {}
        self._lock = threading.Lock()

    def connect(self, remote_id: str) -> TransportChannel:
        with self._lock:
            if remote_id in self._channels:
                return self._channels[remote_id]
            ch = TransportChannel(self.node_id, remote_id, self.tls_config)
            self._channels[remote_id] = ch
        logger.debug("Opened channel %s → %s", self.node_id, remote_id)
        return ch

    def disconnect(self, remote_id: str) -> None:
        with self._lock:
            ch = self._channels.pop(remote_id, None)
        if ch:
            ch.close()

    def register_handler(self, method: str,
                         handler: Callable[[RPCRequest], RPCResponse]) -> None:
        self._handlers[method] = handler

    def send(self, remote_id: str, method: str,
             payload: Dict[str, Any]) -> bool:
        ch = self._channels.get(remote_id)
        if ch is None:
            ch = self.connect(remote_id)
        req = RPCRequest(method=method, payload=payload, sender_id=self.node_id)
        return ch.send(req)

    def broadcast(self, method: str, payload: Dict[str, Any],
                  exclude: Optional[Set[str]] = None) -> int:
        sent = 0
        exclude = exclude or set()
        for rid, ch in list(self._channels.items()):
            if rid in exclude:
                continue
            req = RPCRequest(method=method, payload=payload, sender_id=self.node_id)
            if ch.send(req):
                sent += 1
        return sent

    def poll(self) -> List[Tuple[str, RPCRequest]]:
        """Poll all channels for incoming messages."""
        results: List[Tuple[str, RPCRequest]] = []
        for rid, ch in list(self._channels.items()):
            for msg in ch.receive():
                results.append((rid, msg))
        return results

    def dispatch(self) -> List[RPCResponse]:
        """Poll and dispatch messages to registered handlers."""
        responses: List[RPCResponse] = []
        for rid, req in self.poll():
            handler = self._handlers.get(req.method)
            if handler:
                try:
                    resp = handler(req)
                    responses.append(resp)
                except Exception as exc:
                    responses.append(RPCResponse(
                        request_id=req.request_id, success=False,
                        error=str(exc), sender_id=self.node_id))
            else:
                responses.append(RPCResponse(
                    request_id=req.request_id, success=False,
                    error=f"Unknown method: {req.method}",
                    sender_id=self.node_id))
        return responses

    def get_channel(self, remote_id: str) -> Optional[TransportChannel]:
        return self._channels.get(remote_id)

    def connected_peers(self) -> List[str]:
        return [rid for rid, ch in self._channels.items() if ch.is_connected]

    def stats(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "channels": {rid: ch.stats() for rid, ch in self._channels.items()},
        }
