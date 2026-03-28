#!/usr/bin/env python3
"""
Comprehensive benchmark suite for the Quantum Database System (qndb).

Measures performance across all subsystems:
  - Core engine: circuit creation, state vectors, measurements
  - Encoding: amplitude & basis encoding at varying qubit counts
  - Search: Grover's algorithm scaling with database size
  - Storage: store/retrieve throughput
  - Enterprise: columnar insert/scan, window functions
  - Fault-tolerant: surface code storage, logical qubit ops
  - Distributed: consensus, state sync
"""

import time
import statistics
import sys
import os

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(__file__))


def bench(func, label, iterations=5, warmup=1):
    """Run func `iterations` times, return stats dict."""
    for _ in range(warmup):
        func()
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        func()
        times.append(time.perf_counter() - t0)
    mean = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0.0
    mn, mx = min(times), max(times)
    return {"label": label, "mean_ms": mean * 1000, "std_ms": std * 1000,
            "min_ms": mn * 1000, "max_ms": mx * 1000, "iterations": iterations}


def fmt(r):
    return (f"  {r['label']:<55s} "
            f"mean={r['mean_ms']:>8.3f}ms  "
            f"std={r['std_ms']:>7.3f}ms  "
            f"min={r['min_ms']:>8.3f}ms  "
            f"max={r['max_ms']:>8.3f}ms")


# ======================================================================
# 1. Core Engine
# ======================================================================

def bench_core_engine():
    from qndb.core.quantum_engine import QuantumEngine
    import cirq
    results = []

    for nq in [4, 8, 12, 16]:
        def _init(n=nq):
            e = QuantumEngine(num_qubits=n)
            e.apply_operation("H", list(range(n)))
            return e
        results.append(bench(lambda n=nq: _init(n),
                             f"Engine init + H⊗{nq}  ({nq} qubits)"))

    # State vector simulation
    for nq in [4, 8, 12, 16]:
        engine = QuantumEngine(num_qubits=nq)
        engine.apply_operation("H", list(range(nq)))
        results.append(bench(engine.get_state_vector,
                             f"State vector sim  ({nq} qubits)"))

    # Measurement (run_circuit)
    for nq in [4, 8, 12]:
        engine = QuantumEngine(num_qubits=nq)
        engine.apply_operation("H", list(range(nq)))
        engine.measure_qubits(list(range(nq)))
        results.append(bench(lambda e=engine: e.run_circuit(repetitions=1000),
                             f"Measure 1000 shots  ({nq} qubits)"))

    return results


# ======================================================================
# 2. Encoding
# ======================================================================

def bench_encoding():
    from qndb.core.encoding.amplitude_encoder import AmplitudeEncoder
    from qndb.core.encoding.basis_encoder import BasisEncoder
    import cirq
    import numpy as np
    results = []

    for nq in [4, 6, 8, 10]:
        enc = AmplitudeEncoder(num_qubits=nq)
        data = np.random.rand(2**nq).tolist()
        results.append(bench(lambda e=enc, d=data: e.create_encoding_circuit(d),
                             f"Amplitude encode  ({nq} qubits, {2**nq} values)"))

    for nq in [4, 8, 12, 16]:
        enc = BasisEncoder(num_qubits=nq)
        qubits = [cirq.LineQubit(i) for i in range(nq)]
        val = 2**(nq - 1)
        results.append(bench(lambda e=enc, v=val, q=qubits: e.encode_integer(v, q),
                             f"Basis encode  ({nq} qubits, val={val})"))

    return results


# ======================================================================
# 3. Grover Search
# ======================================================================

def bench_grover():
    from qndb.core.operations.search import QuantumSearch
    import cirq
    results = []

    for nq in [3, 4, 5, 6, 7, 8]:
        qs = QuantumSearch(num_qubits=nq)
        target = 2**(nq - 1)  # mark one item

        def _grover(s=qs, t=target):
            circuit = s.grovers_algorithm([t])
            sim = cirq.Simulator()
            return sim.run(circuit, repetitions=100)

        iters = 3 if nq >= 7 else 5
        results.append(bench(_grover,
                             f"Grover search  ({nq} qubits, N={2**nq})",
                             iterations=iters))

    return results


# ======================================================================
# 4. Enterprise — Columnar Storage
# ======================================================================

def bench_enterprise():
    from qndb.enterprise import ColumnarStorage, QuantumDataType, WindowFunction
    import tempfile, shutil
    results = []

    # Columnar insert
    for n_rows in [100, 500, 1000]:
        def _insert(nr=n_rows):
            d = tempfile.mkdtemp()
            try:
                store = ColumnarStorage(storage_dir=d)
                store.create_table("bench", {
                    "id": QuantumDataType.CLASSICAL_INT,
                    "val": QuantumDataType.CLASSICAL_FLOAT,
                    "tag": QuantumDataType.CLASSICAL_STRING,
                })
                rows = [{"id": i, "val": float(i) * 0.1, "tag": f"t{i % 10}"} for i in range(nr)]
                store.insert_rows("bench", rows)
            finally:
                shutil.rmtree(d, ignore_errors=True)
        results.append(bench(_insert,
                             f"Columnar insert  ({n_rows} rows)", iterations=3))

    # Columnar scan
    for n_rows in [100, 500, 1000]:
        d = tempfile.mkdtemp()
        store = ColumnarStorage(storage_dir=d)
        store.create_table("scan", {
            "id": QuantumDataType.CLASSICAL_INT,
            "val": QuantumDataType.CLASSICAL_FLOAT,
        })
        store.insert_rows("scan", [{"id": i, "val": float(i)} for i in range(n_rows)])
        results.append(bench(lambda s=store: s.scan_rows("scan"),
                             f"Columnar scan  ({n_rows} rows)", iterations=5))
        shutil.rmtree(d, ignore_errors=True)

    # Window function
    for size in [100, 500, 1000]:
        wf = WindowFunction()
        rows = [{"id": i, "val": float(i)} for i in range(size)]
        results.append(bench(
            lambda w=wf, r=rows: w.apply(r, func=WindowFunction.Func.AVG, value_column="val"),
            f"Window AVG  ({size} rows)"))

    return results


# ======================================================================
# 5. Fault-Tolerant
# ======================================================================

def bench_fault_tolerant():
    from qndb.fault_tolerant import (
        SurfaceCodeStorageLayer, LogicalQubit, MagicStateDistillery,
    )
    results = []

    # Surface code patch creation + syndrome round
    for d in [3, 5]:
        def _patch(cd=d):
            s = SurfaceCodeStorageLayer(code_distance=cd)
            s.create_patch("p1")
            s.encode_logical_zero("p1")
            s.run_syndrome_round("p1")
        results.append(bench(_patch,
                             f"Surface code create+encode+syndrome  (d={d})"))

    # Logical qubit operations
    for d in [3, 5]:
        def _lq(cd=d):
            sl = SurfaceCodeStorageLayer(code_distance=cd)
            lq = LogicalQubit("q0", sl)
            lq.logical_x()
            lq.logical_z()
            lq.logical_h()
            lq.logical_measure()
        results.append(bench(_lq,
                             f"Logical qubit X+Z+H+measure  (d={d})"))

    # Magic state distillation
    for d in [3, 5]:
        def _magic(cd=d):
            m = MagicStateDistillery()
            m.distill()
        results.append(bench(_magic,
                             f"Magic state distillation  (15-to-1)", iterations=3))

    return results


# ======================================================================
# 6. Distributed
# ======================================================================

def bench_distributed():
    from qndb.distributed import NodeManager, VectorClock
    results = []

    # Node manager
    for n in [3, 10, 50]:
        def _cluster(nn=n):
            mgr = NodeManager()
            for i in range(nn):
                mgr.register_node(f"n-{i}", host=f"10.0.0.{i+1}", port=5000+i)
        results.append(bench(_cluster,
                             f"Cluster setup  ({n} nodes)"))

    # Vector clock
    def _vc():
        vc = VectorClock()
        for _ in range(100):
            vc = vc.increment("n-0")
    results.append(bench(_vc, "Vector clock 100 increments"))

    return results


# ======================================================================
# 7. Security
# ======================================================================

def bench_security():
    from qndb.security.quantum_encryption import QuantumEncryption
    from qndb.security.access_control import AccessControlManager, Permission
    results = []

    enc = QuantumEncryption()
    results.append(bench(lambda: enc.generate_key(key_size=256),
                         "QKD key generation  (256-bit)"))

    def _acl():
        acm = AccessControlManager()
        acm.create_user("alice", "alice")
        acm.assign_role("alice", "admin")
        for _ in range(100):
            acm.acl.has_permission("system", "admin", Permission.READ)
    results.append(bench(_acl, "ACL setup + 100 permission checks"))

    return results


# ======================================================================
# Main
# ======================================================================

def main():
    print("=" * 90)
    print("  Quantum Database System (qndb) — Benchmark Suite")
    print("=" * 90)
    print()

    sections = [
        ("Core Engine", bench_core_engine),
        ("Encoding", bench_encoding),
        ("Grover Search (circuit build + simulate)", bench_grover),
        ("Enterprise (Columnar / Window)", bench_enterprise),
        ("Fault-Tolerant", bench_fault_tolerant),
        ("Distributed", bench_distributed),
        ("Security", bench_security),
    ]

    all_results = []
    for title, func in sections:
        print(f"--- {title} ---")
        try:
            results = func()
            for r in results:
                print(fmt(r))
            all_results.extend(results)
        except Exception as e:
            print(f"  [ERROR] {e}")
        print()

    print("=" * 90)
    print(f"  {len(all_results)} benchmarks completed")
    print("=" * 90)


if __name__ == "__main__":
    main()
