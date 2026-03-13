"""Distributed subsystem — networking, consensus, replication, queries, cluster management."""

from qndb.distributed.networking import (
    NodeHealth,
    PartitionState,
    PhiAccrualFailureDetector,
    ServiceDiscovery,
    ServiceRecord,
    PartitionDetector,
    TLSConfig,
    TransportChannel,
    TransportLayer,
    RPCRequest,
    RPCResponse,
)

from qndb.distributed.node_manager import Node, NodeManager

from qndb.distributed.consensus import (
    LogEntry,
    PersistentLog,
    ConsensusMetrics,
    QuantumConsensusProtocol,
    QuantumRaft,
    QuantumPBFT,
)

from qndb.distributed.synchronization import (
    ConsistencyLevel,
    VectorClock,
    GCounter,
    LWWRegister,
    ConflictResolutionPolicy,
    ReplicatedValue,
    ConflictResolver,
    GeoRouter,
    QuantumStateSynchronizer,
)

from qndb.distributed.query_processor import (
    PartitionStrategy,
    PartitionConfig,
    DataPartitioner,
    QueryFragment,
    DistributedQueryPlanner,
    DistributedJoinStrategy,
    DistributedJoinPlanner,
    DistributedAggregator,
    TwoPhaseCommitCoordinator,
    DistributedDeadlockDetector,
    DistributedQueryExecutor,
)

from qndb.distributed.cluster_manager import (
    NodeRole,
    ClusterNode,
    ClusterTopology,
    HelmValues,
    ScalingMetrics,
    AutoScaler,
    UpgradePhase,
    UpgradeState,
    RollingUpgradeManager,
    BackupManifest,
    BackupManager,
    ClusterManager,
)

__all__ = [
    # networking
    "NodeHealth", "PartitionState", "PhiAccrualFailureDetector",
    "ServiceDiscovery", "ServiceRecord", "PartitionDetector",
    "TLSConfig", "TransportChannel", "TransportLayer",
    "RPCRequest", "RPCResponse",
    # node_manager
    "Node", "NodeManager",
    # consensus
    "LogEntry", "PersistentLog", "ConsensusMetrics",
    "QuantumConsensusProtocol", "QuantumRaft", "QuantumPBFT",
    # synchronization
    "ConsistencyLevel", "VectorClock", "GCounter", "LWWRegister",
    "ConflictResolutionPolicy", "ReplicatedValue", "ConflictResolver",
    "GeoRouter", "QuantumStateSynchronizer",
    # query_processor
    "PartitionStrategy", "PartitionConfig", "DataPartitioner",
    "QueryFragment", "DistributedQueryPlanner",
    "DistributedJoinStrategy", "DistributedJoinPlanner",
    "DistributedAggregator", "TwoPhaseCommitCoordinator",
    "DistributedDeadlockDetector", "DistributedQueryExecutor",
    # cluster_manager
    "NodeRole", "ClusterNode", "ClusterTopology", "HelmValues",
    "ScalingMetrics", "AutoScaler", "UpgradePhase", "UpgradeState",
    "RollingUpgradeManager", "BackupManifest", "BackupManager",
    "ClusterManager",
]
