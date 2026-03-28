"""
Distributed Database — Cluster, Consensus, State Synchronization
=================================================================

Demonstrates cluster setup, quantum Raft consensus, CRDT-based
state synchronization, and distributed query processing.
"""

from qndb.distributed import (
    Node,
    NodeManager,
    QuantumRaft,
    QuantumPBFT,
    QuantumStateSynchronizer,
    VectorClock,
    ConflictResolver,
    ConsistencyLevel,
    ClusterManager,
    AutoScaler,
    DataPartitioner,
    DistributedQueryPlanner,
    DistributedQueryExecutor,
)


def cluster_setup_demo():
    """Set up a multi-node cluster."""
    print("=== Cluster Setup ===\n")

    manager = NodeManager()
    nodes = [
        manager.add_node(Node(node_id=f"node-{i}", host=f"10.0.0.{i+1}", port=5000 + i))
        for i in range(3)
    ]
    print(f"Cluster nodes: {[n.node_id for n in nodes]}")
    print(f"Cluster size: {manager.cluster_size()}")

    # Health checks
    for node in nodes:
        status = manager.health_check(node.node_id)
        print(f"  {node.node_id}: {status}")


def consensus_demo():
    """Quantum Raft and PBFT consensus."""
    print("\n=== Consensus ===\n")

    # Quantum-enhanced Raft
    raft = QuantumRaft(node_ids=["node-0", "node-1", "node-2"])
    raft.start()
    leader = raft.current_leader()
    print(f"Raft leader: {leader}")

    # Propose and commit a log entry
    entry = raft.propose(command="SET key:1 value:hello")
    print(f"Log entry {entry.index}: committed={entry.committed}")

    # PBFT for Byzantine fault tolerance
    pbft = QuantumPBFT(node_ids=["node-0", "node-1", "node-2", "node-3"])
    pbft.start()
    result = pbft.submit_request(operation="INSERT INTO data VALUES (1, 'x')")
    print(f"PBFT consensus reached: {result.agreed}")


def synchronization_demo():
    """State synchronization with CRDTs and vector clocks."""
    print("\n=== State Synchronization ===\n")

    # Vector clock for causality tracking
    vc = VectorClock(node_ids=["node-0", "node-1", "node-2"])
    vc.increment("node-0")
    vc.increment("node-0")
    vc.increment("node-1")
    print(f"Vector clock: {vc.state()}")

    # Quantum state synchronizer
    sync = QuantumStateSynchronizer(
        node_ids=["node-0", "node-1", "node-2"],
        consistency=ConsistencyLevel.QUORUM,
    )
    sync.replicate("key:1", value={"data": "hello"}, source="node-0")
    replicas = sync.replica_status("key:1")
    print(f"Replicas of key:1: {replicas}")

    # Conflict resolution
    resolver = ConflictResolver(strategy="last-writer-wins")
    resolved = resolver.resolve(
        key="key:1",
        versions=[
            {"value": "v1", "timestamp": 1000, "node": "node-0"},
            {"value": "v2", "timestamp": 1001, "node": "node-1"},
        ],
    )
    print(f"Resolved conflict: {resolved}")


def distributed_query_demo():
    """Distributed query planning and execution."""
    print("\n=== Distributed Queries ===\n")

    # Partition data across nodes
    partitioner = DataPartitioner(strategy="hash", num_partitions=3)
    assignments = partitioner.assign(keys=["k1", "k2", "k3", "k4", "k5"])
    print(f"Partition assignments: {assignments}")

    # Query planning
    planner = DistributedQueryPlanner(num_nodes=3)
    plan = planner.plan("SELECT * FROM sensors WHERE region = 'us-west'")
    print(f"Query plan: {plan.num_fragments} fragments, strategy={plan.strategy}")

    # Query execution
    executor = DistributedQueryExecutor(node_ids=["node-0", "node-1", "node-2"])
    result = executor.execute(plan)
    print(f"Query result: {len(result.rows)} rows in {result.duration_ms:.1f}ms")


def cluster_management_demo():
    """Auto-scaling and cluster management."""
    print("\n=== Cluster Management ===\n")

    cm = ClusterManager(node_ids=["node-0", "node-1", "node-2"])
    topology = cm.topology()
    print(f"Topology: {topology}")

    # Auto-scaling
    scaler = AutoScaler(min_nodes=2, max_nodes=8)
    scaler.update_metrics(cpu=0.90, memory=0.75, queue_depth=50)
    decision = scaler.evaluate()
    print(f"Auto-scale decision: {decision}")


def main():
    cluster_setup_demo()
    consensus_demo()
    synchronization_demo()
    distributed_query_demo()
    cluster_management_demo()


if __name__ == "__main__":
    main()
