"""
Benchmarking utilities for quantum database operations.

Features:
 - QuantumBenchmarkSuite (TPC-H quantum subset, Grover search scaling, join perf)
 - CIBenchmarkRunner for automated regression benchmarks
 - Quantum volume and CLOPS metric calculators
 - CircuitMemoryEstimator for memory profiling
"""

import time
import statistics
import math
import json
import os
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Callable, Tuple
import logging

import numpy as np

logger = logging.getLogger(__name__)


# ======================================================================
# Timer
# ======================================================================

class Timer:
    """Simple context manager for timing code execution."""

    def __init__(self, name=None):
        self.name = name
        self.start_time = None
        self.end_time = None
        self.elapsed = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        self.elapsed = self.end_time - self.start_time
        if self.name:
            logger.info("Timer '%s' completed in %.6f seconds", self.name, self.elapsed)


# ======================================================================
# PerformanceCollector
# ======================================================================

class PerformanceCollector:
    """Collects and stores performance metrics for analysis."""

    def __init__(self, storage_path=None):
        self.metrics: List[Dict[str, Any]] = []
        self.storage_path = storage_path

    def add_metrics(self, metrics_dict):
        if 'timestamp' not in metrics_dict:
            metrics_dict['timestamp'] = datetime.now().isoformat()
        self.metrics.append(metrics_dict)
        if self.storage_path:
            self._save_metrics()

    def get_latest_metrics(self):
        return self.metrics[-1] if self.metrics else None

    def get_metrics_by_type(self, operation_type):
        return [m for m in self.metrics if m.get('operation_type') == operation_type]

    def get_all_metrics(self):
        return self.metrics

    def clear(self):
        self.metrics = []

    def to_dataframe(self):
        import pandas as pd
        return pd.DataFrame(self.metrics)

    def _save_metrics(self):
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, 'w') as f:
                json.dump(self.metrics, f, indent=2)
        except Exception as e:
            logger.error("Failed to save metrics to %s: %s", self.storage_path, e)

    def load_metrics(self):
        if not self.storage_path or not os.path.exists(self.storage_path):
            return False
        try:
            with open(self.storage_path, 'r') as f:
                self.metrics = json.load(f)
            return True
        except Exception as e:
            logger.error("Failed to load metrics from %s: %s", self.storage_path, e)
            return False


# ======================================================================
# BenchmarkRunner
# ======================================================================

class BenchmarkRunner:
    """Runs performance benchmarks on quantum algorithms and operations."""

    def __init__(self, collector=None):
        self.collector = collector if collector is not None else PerformanceCollector()

    def run_benchmark(self, func, args=None, kwargs=None, iterations=5, warmup=1,
                      operation_type=None, metadata=None):
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        if metadata is None:
            metadata = {}

        for _ in range(warmup):
            func(*args, **kwargs)

        execution_times: List[float] = []
        results: List[Any] = []

        for i in range(iterations):
            with Timer() as timer:
                result = func(*args, **kwargs)
            execution_times.append(timer.elapsed)
            results.append(result)

        mean_time = statistics.mean(execution_times)
        median_time = statistics.median(execution_times)
        std_dev = statistics.stdev(execution_times) if iterations > 1 else 0

        benchmark_results = {
            'operation_type': operation_type,
            'mean_execution_time': mean_time,
            'median_execution_time': median_time,
            'std_dev': std_dev,
            'min_execution_time': min(execution_times),
            'max_execution_time': max(execution_times),
            'iterations': iterations,
            **metadata,
        }

        if self.collector:
            self.collector.add_metrics(benchmark_results)

        return benchmark_results, results

    def compare_implementations(self, implementations, input_generator, input_sizes,
                                iterations=3, labels=None, plot=True):
        if labels is None:
            labels = [f"Implementation {i+1}" for i in range(len(implementations))]
        if len(implementations) != len(labels):
            raise ValueError("Number of implementations must match number of labels")

        results = []
        for size in input_sizes:
            input_data = input_generator(size)
            for impl, label in zip(implementations, labels):
                br, _ = self.run_benchmark(
                    func=impl, args=(input_data,), iterations=iterations,
                    operation_type=f"comparison_{label}",
                    metadata={'implementation': label, 'input_size': size},
                )
                results.append(br)

        import pandas as pd
        df = pd.DataFrame(results)
        if plot:
            self._plot_comparison_results(df, input_sizes, labels)
        return df

    def _plot_comparison_results(self, results_df, input_sizes, labels):
        import matplotlib.pyplot as plt
        plt.figure(figsize=(12, 8))
        for label in labels:
            impl_data = results_df[results_df['implementation'] == label]
            plt.plot(impl_data['input_size'], impl_data['mean_execution_time'],
                     marker='o', label=label)
        plt.xlabel('Input Size')
        plt.ylabel('Execution Time (seconds)')
        plt.title('Performance Comparison')
        plt.legend()
        plt.grid(True)
        plt.xscale('log')
        plt.yscale('log')
        plt.savefig('performance_comparison.png')
        logger.info("Performance comparison plot saved as 'performance_comparison.png'")


# ======================================================================
# ScalabilityAnalyzer
# ======================================================================

class ScalabilityAnalyzer:
    """Analyzes scalability of quantum algorithms and operations."""

    def __init__(self, benchmark_runner=None):
        self.benchmark_runner = benchmark_runner if benchmark_runner else BenchmarkRunner()

    def analyze_scaling(self, algorithm, input_generator, input_sizes, fit_curves=True,
                        iterations=3, metadata=None):
        if metadata is None:
            metadata = {}
        results = []
        execution_times = []
        for size in input_sizes:
            input_data = input_generator(size)
            br, _ = self.benchmark_runner.run_benchmark(
                func=algorithm, args=(input_data,), iterations=iterations,
                operation_type="scaling_analysis", metadata={**metadata, 'input_size': size},
            )
            results.append(br)
            execution_times.append(br['mean_execution_time'])

        analysis = {'input_sizes': input_sizes, 'execution_times': execution_times, 'raw_results': results}
        if fit_curves:
            analysis['curve_fits'] = self._fit_scaling_curves(input_sizes, execution_times)
        return analysis

    def _fit_scaling_curves(self, sizes, times):
        x = np.array(sizes)
        y = np.array(times)

        def linear(x, a, b): return a * x + b
        def logarithmic(x, a, b): return a * np.log(x) + b
        def quadratic(x, a, b, c): return a * x**2 + b * x + c
        def exponential(x, a, b, c): return a * np.exp(b * x) + c

        models = {
            'linear': (linear, (1, 0)),
            'logarithmic': (logarithmic, (1, 0)),
            'quadratic': (quadratic, (1, 1, 0)),
            'exponential': (exponential, (1, 0.1, 0)),
        }
        fits = {}
        for name, (func, p0) in models.items():
            try:
                from scipy.optimize import curve_fit
                params, _ = curve_fit(func, x, y, p0=p0, maxfev=10000)
                y_pred = func(x, *params)
                ss_total = np.sum((y - np.mean(y))**2)
                ss_res = np.sum((y - y_pred)**2)
                fits[name] = {
                    'parameters': params.tolist(),
                    'r_squared': 1 - ss_res / ss_total if ss_total else 0,
                    'rmse': float(np.sqrt(np.mean((y - y_pred)**2))),
                }
            except Exception as e:
                fits[name] = {'error': str(e)}
        return fits


# ======================================================================
# ResourceProfiler
# ======================================================================

class ResourceProfiler:
    """Profiles resource usage during algorithm execution."""

    def __init__(self):
        self.has_psutil = self._check_dependency('psutil')
        self.has_memory_profiler = self._check_dependency('memory_profiler')

    @staticmethod
    def _check_dependency(module_name):
        try:
            __import__(module_name)
            return True
        except ImportError:
            return False

    def profile_memory(self, func, *args, **kwargs):
        if not self.has_memory_profiler:
            return func(*args, **kwargs), None
        memory_usage = __import__('memory_profiler').memory_usage
        result = None

        def wrapper():
            nonlocal result
            result = func(*args, **kwargs)

        mem_usage = memory_usage((wrapper, (), {}), interval=0.1, include_children=True)
        return result, {
            'min_memory_mb': min(mem_usage), 'max_memory_mb': max(mem_usage),
            'avg_memory_mb': sum(mem_usage) / len(mem_usage), 'memory_timeline': mem_usage,
        }

    def profile_cpu_and_memory(self, func, *args, **kwargs):
        if not self.has_psutil:
            return func(*args, **kwargs), None

        import psutil, queue as _q, threading
        stats_queue = _q.Queue()
        stop = threading.Event()

        def monitor():
            proc = psutil.Process()
            while not stop.is_set():
                stats_queue.put({
                    'timestamp': time.time(),
                    'cpu_percent': proc.cpu_percent(),
                    'rss_memory_bytes': proc.memory_info().rss,
                    'vms_memory_bytes': proc.memory_info().vms,
                })
                time.sleep(0.1)

        t = threading.Thread(target=monitor, daemon=True)
        t.start()
        start = time.time()
        try:
            result = func(*args, **kwargs)
        finally:
            end = time.time()
            stop.set()
            t.join(timeout=1.0)

        stats = []
        while not stats_queue.empty():
            stats.append(stats_queue.get())

        if stats:
            cpus = [s['cpu_percent'] for s in stats]
            rss = [s['rss_memory_bytes'] / (1024 * 1024) for s in stats]
            summary = {
                'execution_time': end - start,
                'avg_cpu_percent': sum(cpus) / len(cpus),
                'max_cpu_percent': max(cpus),
                'avg_memory_mb': sum(rss) / len(rss),
                'max_memory_mb': max(rss),
                'detailed_timeline': stats,
            }
        else:
            summary = {'execution_time': end - start, 'error': 'No resource stats collected'}
        return result, summary


# ======================================================================
# ParallelBenchmarker
# ======================================================================

class ParallelBenchmarker:
    """Runs benchmarks in parallel."""

    def __init__(self, max_workers=None):
        self.max_workers = max_workers

    def parallel_benchmark(self, func_args_list, iterations=3, warmup=1):
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for func, args, kwargs in func_args_list:
                def task(f=func, a=args, k=kwargs):
                    runner = BenchmarkRunner()
                    r, _ = runner.run_benchmark(func=f, args=a, kwargs=k,
                                                iterations=iterations, warmup=warmup)
                    return r
                futures.append(executor.submit(task))
            results = []
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append({'error': str(e)})
            return results


# ======================================================================
# CrossValidationBenchmarker
# ======================================================================

class CrossValidationBenchmarker:
    """Benchmarks algorithms using cross-validation techniques."""

    def __init__(self, benchmark_runner=None):
        self.benchmark_runner = benchmark_runner if benchmark_runner else BenchmarkRunner()

    def cross_validate(self, func, data_generator, folds=5, iterations=3, metadata=None):
        if metadata is None:
            metadata = {}
        fold_results = []
        for fold in range(folds):
            train, test = data_generator(fold, folds)

            def fold_func(tr=train, te=test):
                return func(tr, te)

            r, _ = self.benchmark_runner.run_benchmark(
                func=fold_func, iterations=iterations,
                operation_type="cross_validation", metadata={**metadata, 'fold': fold},
            )
            fold_results.append(r)

        mean_times = [r['mean_execution_time'] for r in fold_results]
        return {
            'fold_results': fold_results,
            'mean_execution_time': statistics.mean(mean_times),
            'std_dev_across_folds': statistics.stdev(mean_times) if len(mean_times) > 1 else 0,
            'min_fold_time': min(mean_times),
            'max_fold_time': max(mean_times),
        }


# ======================================================================
# QuantumBenchmarkSuite
# ======================================================================

class QuantumBenchmarkSuite:
    """Standard benchmark suite for quantum database operations.

    Includes:
     - TPC-H–inspired quantum subset (simplified queries)
     - Grover search scaling
     - Quantum join performance
    """

    def __init__(self, runner: Optional[BenchmarkRunner] = None):
        self.runner = runner or BenchmarkRunner()

    # -- TPC-H quantum subset --

    def tpch_q1_pricing_summary(self, query_func: Callable, sizes: List[int],
                                iterations: int = 3) -> Dict[str, Any]:
        """Benchmark a TPC-H Q1–style pricing summary aggregation."""
        results = []
        for sz in sizes:
            data = self._generate_lineitem(sz)
            r, _ = self.runner.run_benchmark(
                func=query_func, args=(data,), iterations=iterations,
                operation_type="tpch_q1", metadata={'input_size': sz},
            )
            results.append(r)
        return {'benchmark': 'tpch_q1', 'results': results}

    def tpch_q6_revenue_forecast(self, query_func: Callable, sizes: List[int],
                                 iterations: int = 3) -> Dict[str, Any]:
        results = []
        for sz in sizes:
            data = self._generate_lineitem(sz)
            r, _ = self.runner.run_benchmark(
                func=query_func, args=(data,), iterations=iterations,
                operation_type="tpch_q6", metadata={'input_size': sz},
            )
            results.append(r)
        return {'benchmark': 'tpch_q6', 'results': results}

    @staticmethod
    def _generate_lineitem(n: int) -> List[Dict[str, Any]]:
        rng = np.random.default_rng(42)
        return [
            {'l_quantity': float(rng.integers(1, 50)),
             'l_extendedprice': round(float(rng.uniform(1, 1000)), 2),
             'l_discount': round(float(rng.uniform(0, 0.10)), 2),
             'l_tax': round(float(rng.uniform(0, 0.08)), 2),
             'l_returnflag': rng.choice(['A', 'N', 'R']),
             'l_linestatus': rng.choice(['O', 'F']),
             'l_shipdate': f"199{rng.integers(2,8)}-{rng.integers(1,13):02d}-{rng.integers(1,29):02d}"}
            for _ in range(n)
        ]

    # -- Grover search scaling --

    def grover_scaling(self, search_func: Callable, sizes: List[int],
                       iterations: int = 3) -> Dict[str, Any]:
        """Benchmark Grover search across increasing database sizes."""
        results = []
        for sz in sizes:
            data = list(range(sz))
            target = sz // 2
            r, _ = self.runner.run_benchmark(
                func=search_func, args=(data, target), iterations=iterations,
                operation_type="grover_scaling", metadata={'input_size': sz},
            )
            results.append(r)
        return {'benchmark': 'grover_scaling', 'results': results}

    # -- Join performance --

    def join_benchmark(self, join_func: Callable, sizes: List[int],
                       iterations: int = 3) -> Dict[str, Any]:
        results = []
        for sz in sizes:
            left = [{'id': i, 'val': i * 10} for i in range(sz)]
            right = [{'id': i, 'val': i * 20} for i in range(sz)]
            r, _ = self.runner.run_benchmark(
                func=join_func, args=(left, right), iterations=iterations,
                operation_type="join_benchmark", metadata={'input_size': sz},
            )
            results.append(r)
        return {'benchmark': 'join_benchmark', 'results': results}


# ======================================================================
# CIBenchmarkRunner
# ======================================================================

class CIBenchmarkRunner:
    """Automated CI regression benchmarks.

    Stores baselines in a JSON file and compares subsequent runs against them.
    """

    def __init__(self, baseline_path: str = "benchmark_baselines.json",
                 regression_threshold: float = 0.20):
        self.baseline_path = baseline_path
        self.regression_threshold = regression_threshold
        self.runner = BenchmarkRunner()
        self._baselines: Dict[str, float] = {}
        self._load_baselines()

    def _load_baselines(self) -> None:
        if os.path.exists(self.baseline_path):
            with open(self.baseline_path, 'r') as f:
                self._baselines = json.load(f)

    def save_baselines(self) -> None:
        with open(self.baseline_path, 'w') as f:
            json.dump(self._baselines, f, indent=2)

    def run_and_compare(self, name: str, func: Callable, args=None, kwargs=None,
                        iterations: int = 5) -> Dict[str, Any]:
        r, _ = self.runner.run_benchmark(func=func, args=args, kwargs=kwargs,
                                          iterations=iterations,
                                          operation_type=f"ci_{name}")
        mean = r['mean_execution_time']
        baseline = self._baselines.get(name)
        result: Dict[str, Any] = {'name': name, 'mean_time': mean, 'baseline': baseline}
        if baseline is None:
            self._baselines[name] = mean
            result['status'] = 'baseline_set'
        else:
            regression = (mean - baseline) / baseline
            result['regression_pct'] = round(regression * 100, 2)
            result['status'] = 'regression' if regression > self.regression_threshold else 'ok'
        return result

    def run_suite(self, tests: Dict[str, Tuple[Callable, tuple, dict]],
                  iterations: int = 5) -> List[Dict[str, Any]]:
        results = []
        for name, (func, args, kwargs) in tests.items():
            results.append(self.run_and_compare(name, func, args, kwargs, iterations))
        self.save_baselines()
        return results


# ======================================================================
# Quantum volume & CLOPS
# ======================================================================

class QuantumVolumeCalculator:
    """Calculate quantum volume metric."""

    @staticmethod
    def estimate(num_qubits: int, success_rate: float, depth: int) -> int:
        """Estimate quantum volume as 2^d where d is the largest depth where
        success_rate > 2/3 for a d-qubit, d-depth random circuit."""
        if success_rate < 2.0 / 3.0:
            return 1
        d = min(num_qubits, depth)
        return 2 ** d

    @staticmethod
    def benchmark(circuit_runner: Callable, max_qubits: int = 10,
                  shots: int = 1000) -> Dict[str, Any]:
        """Run QV benchmark across qubit counts."""
        results = []
        best_d = 0
        for d in range(2, max_qubits + 1):
            try:
                success = circuit_runner(d, shots)
            except Exception:
                success = 0.0
            passed = success > 2.0 / 3.0
            if passed:
                best_d = d
            results.append({'depth': d, 'success_rate': success, 'passed': passed})
        return {'quantum_volume': 2 ** best_d, 'best_depth': best_d, 'per_depth': results}


class CLOPSCalculator:
    """Circuit Layer Operations Per Second (CLOPS) metric."""

    @staticmethod
    def measure(circuit_runner: Callable, num_qubits: int = 5,
                depth: int = 10, num_circuits: int = 100,
                shots_per_circuit: int = 100) -> Dict[str, Any]:
        start = time.time()
        for _ in range(num_circuits):
            circuit_runner(num_qubits, depth, shots_per_circuit)
        elapsed = time.time() - start
        total_layers = num_circuits * depth
        clops = total_layers / elapsed if elapsed > 0 else 0
        return {
            'clops': round(clops, 2),
            'total_circuits': num_circuits,
            'total_layers': total_layers,
            'elapsed_seconds': round(elapsed, 4),
        }


# ======================================================================
# CircuitMemoryEstimator
# ======================================================================

class CircuitMemoryEstimator:
    """Estimate memory footprint of quantum circuits."""

    BYTES_PER_QUBIT_STATE = 16  # complex128
    BYTES_PER_GATE = 64  # rough gate object overhead

    @classmethod
    def estimate(cls, num_qubits: int, num_gates: int, depth: int) -> Dict[str, Any]:
        state_vector_bytes = (2 ** num_qubits) * cls.BYTES_PER_QUBIT_STATE
        gate_bytes = num_gates * cls.BYTES_PER_GATE
        total = state_vector_bytes + gate_bytes
        return {
            'state_vector_bytes': state_vector_bytes,
            'gate_storage_bytes': gate_bytes,
            'total_bytes': total,
            'total_mb': round(total / (1024 * 1024), 2),
            'num_qubits': num_qubits,
            'num_gates': num_gates,
            'depth': depth,
        }

    @classmethod
    def from_circuit(cls, circuit) -> Dict[str, Any]:
        nq = getattr(circuit, 'num_qubits', 0)
        if not nq and hasattr(circuit, 'qubits'):
            nq = len(circuit.qubits)
        ng = getattr(circuit, 'num_gates', 0)
        if not ng and hasattr(circuit, 'operations'):
            ng = len(list(circuit.operations)) if hasattr(circuit.operations, '__iter__') else 0
        depth = getattr(circuit, 'depth', 1)
        return cls.estimate(nq, ng, depth)


# ======================================================================
# cost_estimator (kept backward-compatible)
# ======================================================================

def cost_estimator(circuit, hardware_params=None):
    if hardware_params is None:
        hardware_params = {
            'qubit_cost': 1.0, 'gate_cost': 0.1,
            'measurement_cost': 0.5, 'time_cost': 2.0,
        }
    num_qubits = getattr(circuit, 'num_qubits', 0)
    if not num_qubits and hasattr(circuit, 'qubits'):
        num_qubits = len(circuit.qubits)
    num_gates = getattr(circuit, 'num_gates', 0)
    if not num_gates and hasattr(circuit, 'operations'):
        num_gates = len(circuit.operations)
    num_measurements = getattr(circuit, 'num_measurements', 0) or num_qubits
    circuit_depth = getattr(circuit, 'depth', 1)
    return (num_qubits * hardware_params['qubit_cost']
            + num_gates * hardware_params['gate_cost']
            + num_measurements * hardware_params['measurement_cost']
            + circuit_depth * hardware_params['time_cost'])


# ======================================================================
# Exports
# ======================================================================

__all__ = [
    'Timer',
    'PerformanceCollector',
    'BenchmarkRunner',
    'ScalabilityAnalyzer',
    'ResourceProfiler',
    'ParallelBenchmarker',
    'CrossValidationBenchmarker',
    'QuantumBenchmarkSuite',
    'CIBenchmarkRunner',
    'QuantumVolumeCalculator',
    'CLOPSCalculator',
    'CircuitMemoryEstimator',
    'cost_estimator',
]