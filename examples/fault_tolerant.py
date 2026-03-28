"""
Fault-Tolerant Operations — Surface Codes, Logical Qubits, Networking
======================================================================

Demonstrates the Phase 9 fault-tolerant modules: surface-code storage,
logical qubit manipulation, magic state distillation, lattice surgery,
quantum networking, and batch query performance.
"""

from qndb.fault_tolerant import (
    SurfaceCodeStorageLayer,
    LogicalQubit,
    MagicStateDistillery,
    LatticeSurgeryEngine,
    ErrorBudgetTracker,
    LogicalQubitManager,
    MultiZoneProcessor,
    QuantumMemoryBank,
    PetabyteQuantumIndex,
    QuantumInternetGateway,
    EntanglementDistributor,
    QuantumRepeaterChain,
    BellPairLocker,
    QuantumSecureLink,
    BatchQueryEngine,
    CircuitCacheLayer,
    HorizontalScaler,
    QuantumAdvantageBenchmark,
)


def surface_code_demo():
    """Surface code storage and logical qubit operations."""
    print("=== Surface Code Storage ===\n")

    # Surface-code protected storage
    storage = SurfaceCodeStorageLayer(code_distance=5)
    storage.store_logical_data("record:1", b"important-payload")
    data = storage.retrieve_logical_data("record:1")
    print(f"Stored and retrieved: {data}")
    print(f"Error rate: {storage.current_error_rate():.6f}")

    # Logical qubit lifecycle
    lq = LogicalQubit(code_distance=3)
    lq.initialize_logical_zero()
    print(f"Logical |0⟩ fidelity: {lq.fidelity():.4f}")
    lq.apply_logical_x()
    state = lq.measure_logical()
    print(f"After X gate, measured: {state}")

    # Magic state distillation (for T-gates)
    distillery = MagicStateDistillery(code_distance=5, num_factories=2)
    magic_state = distillery.distill()
    print(f"Magic state fidelity: {magic_state.fidelity:.6f}")
    print(f"Distillation rounds: {magic_state.rounds}")

    # Lattice surgery for multi-qubit operations
    engine = LatticeSurgeryEngine(code_distance=5)
    engine.merge(lq, LogicalQubit(code_distance=3))
    print(f"Lattice surgery merge completed")

    # Error budget tracking
    tracker = ErrorBudgetTracker(total_budget=1e-3)
    tracker.allocate("storage", 3e-4)
    tracker.allocate("gates", 5e-4)
    tracker.allocate("measurement", 2e-4)
    print(f"Error budget remaining: {tracker.remaining():.6f}")


def scalable_architecture_demo():
    """Large-scale qubit management and multi-zone processing."""
    print("\n=== Scalable Architecture ===\n")

    # Manage thousands of logical qubits
    manager = LogicalQubitManager(max_qubits=1000)
    ids = [manager.allocate(code_distance=3) for _ in range(5)]
    print(f"Allocated {len(ids)} logical qubits: {ids}")
    print(f"Utilization: {manager.utilization():.1%}")

    # Multi-zone quantum processor
    mzp = MultiZoneProcessor(num_zones=4, qubits_per_zone=64)
    mzp.assign_task("zone-0", "grover_search")
    mzp.assign_task("zone-1", "vqe_optimization")
    status = mzp.zone_status()
    print(f"Zone status: {status}")

    # Quantum memory bank
    bank = QuantumMemoryBank(capacity_gb=256)
    bank.store("dataset:sensor", size_mb=50)
    bank.store("dataset:logs", size_mb=120)
    print(f"Memory used: {bank.used_mb()} MB / {bank.capacity_gb * 1024} MB")

    # Petabyte-scale quantum index
    index = PetabyteQuantumIndex(num_shards=16)
    index.add_entry("key:abc", shard=3, offset=1024)
    loc = index.lookup("key:abc")
    print(f"Index lookup: {loc}")


def networking_demo():
    """Quantum internet, entanglement distribution, secure links."""
    print("\n=== Quantum Networking ===\n")

    # Quantum internet gateway
    gateway = QuantumInternetGateway(node_id="node-alpha")
    gateway.register_peer("node-beta", address="10.0.1.2")
    peers = gateway.list_peers()
    print(f"Peers: {peers}")

    # Entanglement distribution
    distributor = EntanglementDistributor(num_pairs=10)
    pair = distributor.distribute("node-alpha", "node-beta")
    print(f"Bell pair fidelity: {pair.fidelity:.4f}")

    # Quantum repeater chain
    chain = QuantumRepeaterChain(num_repeaters=3, distance_km=100)
    result = chain.establish("node-alpha", "node-gamma")
    print(f"Repeater chain: {result.hops} hops, fidelity={result.end_to_end_fidelity:.4f}")

    # Bell-pair locking (for distributed transactions)
    locker = BellPairLocker()
    lock_id = locker.acquire("node-alpha", "node-beta", timeout_ms=5000)
    print(f"Lock acquired: {lock_id}")
    locker.release(lock_id)
    print("Lock released")

    # QKD-secured link
    link = QuantumSecureLink("node-alpha", "node-beta", protocol="BB84")
    key = link.exchange_key(key_length=256)
    print(f"Shared key length: {len(key)} bits")


def performance_demo():
    """Batch queries, circuit caching, horizontal scaling, benchmarks."""
    print("\n=== Performance ===\n")

    # Batch query engine
    batch = BatchQueryEngine(max_batch_size=256)
    for i in range(5):
        batch.submit(f"SELECT * FROM sensors WHERE id = {i}")
    results = batch.flush()
    print(f"Batch executed: {len(results)} queries")

    # Circuit cache
    cache = CircuitCacheLayer(max_entries=1024)
    cache.put("grover_8q", circuit_data=b"serialized-circuit", cost_ms=45.0)
    hit = cache.get("grover_8q")
    print(f"Cache hit: {hit is not None}, saved {hit.cost_ms if hit else 0}ms")

    # Horizontal scaler
    scaler = HorizontalScaler(min_nodes=2, max_nodes=16)
    scaler.update_metrics(cpu=0.85, queue_depth=120)
    action = scaler.evaluate()
    print(f"Scaling decision: {action}")

    # Quantum advantage benchmark
    bench = QuantumAdvantageBenchmark()
    report = bench.run_suite(
        workloads=["grover_search", "hhl_solve", "qaoa_optimize"],
        num_qubits=8,
        repetitions=10,
    )
    print(f"Benchmark: {len(report.results)} workloads tested")
    for r in report.results:
        print(f"  {r.workload}: quantum={r.quantum_time_ms:.1f}ms, "
              f"classical={r.classical_time_ms:.1f}ms, "
              f"speedup={r.speedup:.2f}x")


def main():
    surface_code_demo()
    scalable_architecture_demo()
    networking_demo()
    performance_demo()


if __name__ == "__main__":
    main()
