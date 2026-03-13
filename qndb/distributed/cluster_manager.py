"""
Cluster Management

Kubernetes operator abstractions, Helm chart configuration, auto-scaling,
rolling upgrades with zero downtime, and backup / disaster recovery.
"""

import json
import hashlib
import logging
import time
import uuid
import copy
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Cluster topology ──────────────────────────────────────────────────
class NodeRole(Enum):
    LEADER = "leader"
    FOLLOWER = "follower"
    LEARNER = "learner"          # new node catching up
    OBSERVER = "observer"        # read-only replica


@dataclass
class ClusterNode:
    node_id: str
    host: str
    port: int
    role: NodeRole = NodeRole.FOLLOWER
    zone: str = ""
    version: str = ""
    healthy: bool = True
    last_heartbeat: float = field(default_factory=time.time)
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id, "host": self.host, "port": self.port,
            "role": self.role.value, "zone": self.zone, "version": self.version,
            "healthy": self.healthy,
        }


@dataclass
class ClusterTopology:
    """Describes the desired cluster topology."""
    replicas: int = 3
    zones: List[str] = field(default_factory=lambda: ["default"])
    min_replicas: int = 1
    max_replicas: int = 10
    replication_factor: int = 3


# ── Helm-style config ─────────────────────────────────────────────────
@dataclass
class HelmValues:
    """Helm chart-style configuration for cluster deployment."""
    cluster_name: str = "qndb-cluster"
    namespace: str = "qndb"
    replicas: int = 3
    image: str = "qndb/quantum-database:latest"
    resources: Dict[str, Any] = field(default_factory=lambda: {
        "requests": {"cpu": "500m", "memory": "1Gi"},
        "limits": {"cpu": "2", "memory": "4Gi"},
    })
    storage_class: str = "standard"
    storage_size: str = "10Gi"
    qubit_limit: int = 100
    tls_enabled: bool = True
    monitoring_enabled: bool = True
    backup_schedule: str = "0 2 * * *"  # daily at 2 AM
    topology: ClusterTopology = field(default_factory=ClusterTopology)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_name": self.cluster_name,
            "namespace": self.namespace,
            "replicas": self.replicas,
            "image": self.image,
            "resources": self.resources,
            "storage_class": self.storage_class,
            "storage_size": self.storage_size,
            "qubit_limit": self.qubit_limit,
            "tls_enabled": self.tls_enabled,
            "monitoring_enabled": self.monitoring_enabled,
            "backup_schedule": self.backup_schedule,
            "topology": {
                "replicas": self.topology.replicas,
                "zones": self.topology.zones,
                "min_replicas": self.topology.min_replicas,
                "max_replicas": self.topology.max_replicas,
                "replication_factor": self.topology.replication_factor,
            },
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HelmValues":
        topo_d = d.pop("topology", {})
        topo = ClusterTopology(**topo_d) if topo_d else ClusterTopology()
        return cls(topology=topo, **{k: v for k, v in d.items() if k != "topology"})


# ── Auto-scaler ───────────────────────────────────────────────────────
@dataclass
class ScalingMetrics:
    qubit_utilisation: float = 0.0   # 0.0–1.0
    query_rate: float = 0.0          # queries/sec
    avg_latency_ms: float = 0.0
    pending_jobs: int = 0


class AutoScaler:
    """Scales the cluster based on qubit demand and query load."""

    def __init__(self, topology: ClusterTopology,
                 scale_up_threshold: float = 0.8,
                 scale_down_threshold: float = 0.2,
                 cooldown_seconds: float = 300):
        self.topology = topology
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.cooldown = cooldown_seconds
        self._current_replicas: int = topology.replicas
        self._last_scale_time: float = 0.0
        self._history: List[Dict[str, Any]] = []

    @property
    def current_replicas(self) -> int:
        return self._current_replicas

    def evaluate(self, metrics: ScalingMetrics) -> Optional[int]:
        """Evaluate metrics and return new replica count (or None if no change)."""
        now = time.time()
        if now - self._last_scale_time < self.cooldown:
            return None

        target = self._current_replicas

        if (metrics.qubit_utilisation > self.scale_up_threshold or
                metrics.pending_jobs > self._current_replicas * 10):
            target = min(self._current_replicas + 1, self.topology.max_replicas)
        elif (metrics.qubit_utilisation < self.scale_down_threshold and
              metrics.pending_jobs == 0):
            target = max(self._current_replicas - 1, self.topology.min_replicas)

        if target != self._current_replicas:
            old = self._current_replicas
            self._current_replicas = target
            self._last_scale_time = now
            self._history.append({
                "timestamp": now, "from": old, "to": target,
                "reason": "utilisation" if metrics.qubit_utilisation > self.scale_up_threshold
                          else "idle",
            })
            logger.info("Auto-scaled %d → %d replicas", old, target)
            return target
        return None

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)


# ── Rolling upgrade ───────────────────────────────────────────────────
class UpgradePhase(Enum):
    IDLE = "idle"
    DRAINING = "draining"
    UPGRADING = "upgrading"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class UpgradeState:
    upgrade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    target_version: str = ""
    phase: UpgradePhase = UpgradePhase.IDLE
    nodes_upgraded: List[str] = field(default_factory=list)
    nodes_pending: List[str] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""


class RollingUpgradeManager:
    """Orchestrates zero-downtime rolling upgrades.

    Upgrades one node at a time: drain → upgrade → verify → proceed.
    """

    def __init__(self, node_manager):
        self.node_manager = node_manager
        self._current: Optional[UpgradeState] = None
        self._lock = threading.Lock()

    def start_upgrade(self, target_version: str,
                      node_order: Optional[List[str]] = None) -> UpgradeState:
        with self._lock:
            if self._current and self._current.phase not in (
                    UpgradePhase.IDLE, UpgradePhase.COMPLETE, UpgradePhase.FAILED):
                raise RuntimeError("Upgrade already in progress")
            nodes = node_order or [n.id for n in self.node_manager.get_all_nodes()]
            state = UpgradeState(
                target_version=target_version,
                nodes_pending=list(nodes),
                started_at=time.time(),
                phase=UpgradePhase.DRAINING,
            )
            self._current = state
        logger.info("Rolling upgrade started → v%s (%d nodes)",
                     target_version, len(nodes))
        return state

    def upgrade_next_node(self) -> Optional[str]:
        with self._lock:
            if not self._current or not self._current.nodes_pending:
                if self._current:
                    self._current.phase = UpgradePhase.COMPLETE
                    self._current.completed_at = time.time()
                return None
            node_id = self._current.nodes_pending.pop(0)
            self._current.phase = UpgradePhase.UPGRADING

        # Drain traffic (mark inactive)
        self.node_manager.mark_node_inactive(node_id)

        # Simulate upgrade (in production this would restart the process)
        node = self.node_manager.get_node(node_id)
        if node:
            node.metadata["version"] = self._current.target_version

        # Mark active again
        self.node_manager.mark_node_active(node_id)

        with self._lock:
            self._current.nodes_upgraded.append(node_id)
            self._current.phase = UpgradePhase.VERIFYING

        logger.info("Upgraded node %s to v%s", node_id, self._current.target_version)
        return node_id

    def rollback(self) -> bool:
        with self._lock:
            if not self._current:
                return False
            self._current.phase = UpgradePhase.FAILED
            self._current.error = "Manual rollback"
        logger.warning("Rolling upgrade rolled back")
        return True

    @property
    def state(self) -> Optional[UpgradeState]:
        return self._current


# ── Backup & disaster recovery ────────────────────────────────────────
@dataclass
class BackupManifest:
    backup_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    node_id: str = ""
    tables: List[str] = field(default_factory=list)
    size_bytes: int = 0
    checksum: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "timestamp": self.timestamp,
            "node_id": self.node_id,
            "tables": self.tables,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
            "metadata": self.metadata,
        }


class BackupManager:
    """Manages cluster backups and restoration."""

    def __init__(self, backup_dir: str = "/tmp/qndb_backups"):
        self.backup_dir = backup_dir
        self._manifests: List[BackupManifest] = []
        self._lock = threading.Lock()

    def create_backup(self, node_id: str, data: Dict[str, Any],
                      tables: Optional[List[str]] = None) -> BackupManifest:
        serialised = json.dumps(data, sort_keys=True, default=str)
        checksum = hashlib.sha256(serialised.encode()).hexdigest()
        manifest = BackupManifest(
            node_id=node_id,
            tables=tables or [],
            size_bytes=len(serialised.encode()),
            checksum=checksum,
        )
        with self._lock:
            self._manifests.append(manifest)
        logger.info("Backup created: %s (%d bytes)", manifest.backup_id, manifest.size_bytes)
        return manifest

    def list_backups(self, node_id: Optional[str] = None) -> List[BackupManifest]:
        with self._lock:
            if node_id:
                return [m for m in self._manifests if m.node_id == node_id]
            return list(self._manifests)

    def get_latest_backup(self, node_id: Optional[str] = None) -> Optional[BackupManifest]:
        backups = self.list_backups(node_id)
        if not backups:
            return None
        return max(backups, key=lambda m: m.timestamp)

    def restore_backup(self, backup_id: str) -> Optional[BackupManifest]:
        with self._lock:
            for m in self._manifests:
                if m.backup_id == backup_id:
                    logger.info("Restoring backup %s", backup_id)
                    return m
        return None

    def prune_old_backups(self, keep: int = 5,
                          node_id: Optional[str] = None) -> int:
        with self._lock:
            if node_id:
                target = [m for m in self._manifests if m.node_id == node_id]
                rest = [m for m in self._manifests if m.node_id != node_id]
            else:
                target = list(self._manifests)
                rest = []
            target.sort(key=lambda m: m.timestamp, reverse=True)
            pruned = target[keep:]
            kept = target[:keep]
            self._manifests = rest + kept
        return len(pruned)


# ── Cluster manager (orchestrator) ────────────────────────────────────
class ClusterManager:
    """Top-level orchestrator for cluster lifecycle.

    Ties together topology, auto-scaling, rolling upgrades,
    and backup management.
    """

    def __init__(self, node_manager, values: Optional[HelmValues] = None):
        self.node_manager = node_manager
        self.values = values or HelmValues()
        self.auto_scaler = AutoScaler(self.values.topology)
        self.upgrade_manager = RollingUpgradeManager(node_manager)
        self.backup_manager = BackupManager()
        self._cluster_nodes: Dict[str, ClusterNode] = {}

    def add_node(self, node_id: str, host: str, port: int,
                 role: NodeRole = NodeRole.FOLLOWER,
                 zone: str = "default") -> ClusterNode:
        cn = ClusterNode(node_id=node_id, host=host, port=port,
                         role=role, zone=zone,
                         version=self.values.image)
        self._cluster_nodes[node_id] = cn
        self.node_manager.register_node(node_id, host, port)
        return cn

    def remove_node(self, node_id: str) -> bool:
        cn = self._cluster_nodes.pop(node_id, None)
        if cn:
            self.node_manager.deregister_node(node_id)
            return True
        return False

    def get_node(self, node_id: str) -> Optional[ClusterNode]:
        return self._cluster_nodes.get(node_id)

    def cluster_status(self) -> Dict[str, Any]:
        return {
            "cluster_name": self.values.cluster_name,
            "total_nodes": len(self._cluster_nodes),
            "healthy_nodes": sum(1 for cn in self._cluster_nodes.values() if cn.healthy),
            "current_replicas": self.auto_scaler.current_replicas,
            "nodes": {nid: cn.to_dict() for nid, cn in self._cluster_nodes.items()},
        }

    def evaluate_scaling(self, metrics: ScalingMetrics) -> Optional[int]:
        return self.auto_scaler.evaluate(metrics)

    def start_rolling_upgrade(self, version: str) -> UpgradeState:
        return self.upgrade_manager.start_upgrade(version)

    def backup_cluster(self, data: Dict[str, Any]) -> BackupManifest:
        return self.backup_manager.create_backup(
            self.node_manager.local_node_id, data,
            tables=list(data.keys()) if isinstance(data, dict) else [])
