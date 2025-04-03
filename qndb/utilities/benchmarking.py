"""
Benchmarking utilities for quantum database operations.

This module provides tools for performance testing, profiling, and benchmarking
quantum database operations and algorithms against classical alternatives.
"""

import time
import statistics
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)

class Timer:
    """Simple context manager for timing code execution."""
    
    def __init__(self, name=None):
        """
        Initialize timer.
        
        Args:
            name (str, optional): Timer name for identification
        """
        self.name = name
        self.start_time = None
        self.end_time = None
        self.elapsed = None
    
    def __enter__(self):
        """Start timer when entering context."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Calculate elapsed time when exiting context."""
        self.end_time = time.time()
        self.elapsed = self.end_time - self.start_time
        if self.name:
            logger.info(f"Timer '{self.name}' completed in {self.elapsed:.6f} seconds")


class PerformanceCollector:
    """Collects and stores performance metrics for analysis."""
    
    def __init__(self, storage_path=None):
        """
        Initialize performance collector.
        
        Args:
            storage_path (str, optional): Path to store performance data
        """
        self.metrics = []
        self.storage_path = storage_path
    
    def add_metrics(self, metrics_dict):
        """
        Add performance metrics.
        
        Args:
            metrics_dict (dict): Dictionary containing performance metrics
        """
        # Add timestamp if not present
        if 'timestamp' not in metrics_dict:
            metrics_dict['timestamp'] = datetime.now().isoformat()
        
        self.metrics.append(metrics_dict)
        
        # Save to storage if path specified
        if self.storage_path:
            self._save_metrics()
    
    def get_latest_metrics(self):
        """
        Get the most recent metrics.
        
        Returns:
            dict: Most recent metrics, or None if no metrics collected
        """
        if not self.metrics:
            return None
        return self.metrics[-1]
    
    def get_metrics_by_type(self, operation_type):
        """
        Get metrics filtered by operation type.
        
        Args:
            operation_type (str): Type of operation to filter by
            
        Returns:
            list: Filtered metrics
        """
        return [m for m in self.metrics if m.get('operation_type') == operation_type]
    
    def get_all_metrics(self):
        """
        Get all collected metrics.
        
        Returns:
            list: All metrics
        """
        return self.metrics
    
    def clear(self):
        """Clear all collected metrics."""
        self.metrics = []
    
    def to_dataframe(self):
        """
        Convert metrics to pandas DataFrame.
        
        Returns:
            pandas.DataFrame: DataFrame containing all metrics
        """
        return pd.DataFrame(self.metrics)
    
    def _save_metrics(self):
        """Save metrics to storage."""
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, 'w') as f:
                json.dump(self.metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metrics to {self.storage_path}: {e}")
    
    def load_metrics(self):
        """
        Load metrics from storage.
        
        Returns:
            bool: True if loaded successfully, False otherwise
        """
        if not self.storage_path or not os.path.exists(self.storage_path):
            return False
        
        try:
            with open(self.storage_path, 'r') as f:
                self.metrics = json.load(f)
            return True
        except Exception as e:
            logger.error(f"Failed to load metrics from {self.storage_path}: {e}")
            return False


class BenchmarkRunner:
    """Runs performance benchmarks on quantum algorithms and operations."""
    
    def __init__(self, collector=None):
        """
        Initialize benchmark runner.
        
        Args:
            collector (PerformanceCollector, optional): Collector for performance metrics
        """
        self.collector = collector if collector is not None else PerformanceCollector()
    
    def run_benchmark(self, func, args=None, kwargs=None, iterations=5, warmup=1, 
                     operation_type=None, metadata=None):
        """
        Run performance benchmark on a function.
        
        Args:
            func (callable): Function to benchmark
            args (tuple, optional): Positional arguments for the function
            kwargs (dict, optional): Keyword arguments for the function
            iterations (int): Number of iterations to run
            warmup (int): Number of warmup iterations to run
            operation_type (str, optional): Type of operation being benchmarked
            metadata (dict, optional): Additional metadata to include
            
        Returns:
            dict: Benchmark results
        """
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        if metadata is None:
            metadata = {}
        
        # Perform warmup iterations
        for _ in range(warmup):
            func(*args, **kwargs)
        
        # Run timed iterations
        execution_times = []
        results = []
        
        for i in range(iterations):
            logger.debug(f"Running benchmark iteration {i+1}/{iterations}")
            
            # Time the execution
            with Timer() as timer:
                result = func(*args, **kwargs)
            
            execution_times.append(timer.elapsed)
            results.append(result)
        
        # Calculate statistics
        mean_time = statistics.mean(execution_times)
        median_time = statistics.median(execution_times)
        std_dev = statistics.stdev(execution_times) if iterations > 1 else 0
        min_time = min(execution_times)
        max_time = max(execution_times)
        
        # Assemble metrics
        benchmark_results = {
            'operation_type': operation_type,
            'mean_execution_time': mean_time,
            'median_execution_time': median_time,
            'std_dev': std_dev,
            'min_execution_time': min_time,
            'max_execution_time': max_time,
            'iterations': iterations,
            **metadata
        }
        
        # Add to collector if available
        if self.collector:
            self.collector.add_metrics(benchmark_results)
        
        return benchmark_results, results
    def compare_implementations(self, implementations, input_generator, input_sizes, 
                              iterations=3, labels=None, plot=True):
        """
        Compare different implementations of the same algorithm.
        
        Args:
            implementations (list): List of functions to compare
            input_generator (callable): Function that generates inputs for a given size
            input_sizes (list): List of input sizes to test
            iterations (int): Number of iterations for each implementation and size
            labels (list, optional): Names for each implementation
            plot (bool): Whether to generate performance comparison plots
            
        Returns:
            pandas.DataFrame: Performance comparison results
        """
        if labels is None:
            labels = [f"Implementation {i+1}" for i in range(len(implementations))]
        
        if len(implementations) != len(labels):
            raise ValueError("Number of implementations must match number of labels")
            
        results = []
        
        # Run benchmarks for each implementation and input size
        for size in input_sizes:
            logger.info(f"Benchmarking input size: {size}")
            input_data = input_generator(size)
            
            for i, (impl, label) in enumerate(zip(implementations, labels)):
                logger.info(f"Running {label} with input size {size}")
                
                benchmark_result, _ = self.run_benchmark(
                    func=impl,
                    args=(input_data,),
                    iterations=iterations,
                    operation_type=f"comparison_{label}",
                    metadata={
                        'implementation': label,
                        'input_size': size
                    }
                )
                
                results.append(benchmark_result)
        
        # Convert results to DataFrame for analysis
        df = pd.DataFrame(results)
        
        if plot:
            self._plot_comparison_results(df, input_sizes, labels)
            
        return df
    
    def _plot_comparison_results(self, results_df, input_sizes, labels):
        """
        Generate plots for implementation comparisons.
        
        Args:
            results_df (pandas.DataFrame): Benchmark results
            input_sizes (list): List of input sizes used
            labels (list): Names of implementations
        """
        plt.figure(figsize=(12, 8))
        
        # Extract data for each implementation
        for label in labels:
            impl_data = results_df[results_df['implementation'] == label]
            plt.plot(
                impl_data['input_size'], 
                impl_data['mean_execution_time'], 
                marker='o', 
                label=label
            )
        
        plt.xlabel('Input Size')
        plt.ylabel('Execution Time (seconds)')
        plt.title('Performance Comparison')
        plt.legend()
        plt.grid(True)
        plt.xscale('log')
        plt.yscale('log')
        
        plt.savefig('performance_comparison.png')
        logger.info("Performance comparison plot saved as 'performance_comparison.png'")


class ScalabilityAnalyzer:
    """Analyzes scalability of quantum algorithms and operations."""
    
    def __init__(self, benchmark_runner=None):
        """
        Initialize scalability analyzer.
        
        Args:
            benchmark_runner (BenchmarkRunner, optional): Runner to use for benchmarks
        """
        self.benchmark_runner = benchmark_runner if benchmark_runner else BenchmarkRunner()
    
    def analyze_scaling(self, algorithm, input_generator, input_sizes, fit_curves=True, 
                       iterations=3, metadata=None):
        """
        Analyze how an algorithm scales with input size.
        
        Args:
            algorithm (callable): Algorithm to analyze
            input_generator (callable): Function to generate inputs of specified size
            input_sizes (list): List of input sizes to test
            fit_curves (bool): Whether to fit scaling curves to the data
            iterations (int): Number of iterations per input size
            metadata (dict, optional): Additional metadata
            
        Returns:
            dict: Scaling analysis results
        """
        if metadata is None:
            metadata = {}
            
        results = []
        execution_times = []
        
        # Benchmark for each input size
        for size in input_sizes:
            logger.info(f"Analyzing scaling for input size: {size}")
            input_data = input_generator(size)
            
            benchmark_result, _ = self.benchmark_runner.run_benchmark(
                func=algorithm,
                args=(input_data,),
                iterations=iterations,
                operation_type="scaling_analysis",
                metadata={**metadata, 'input_size': size}
            )
            
            results.append(benchmark_result)
            execution_times.append(benchmark_result['mean_execution_time'])
        
        analysis_results = {
            'input_sizes': input_sizes,
            'execution_times': execution_times,
            'raw_results': results
        }
        
        # Fit scaling curves if requested
        if fit_curves:
            analysis_results['curve_fits'] = self._fit_scaling_curves(
                input_sizes, execution_times
            )
            
        return analysis_results
    
    def _fit_scaling_curves(self, sizes, times):
        """
        Fit various scaling curves to the data.
        
        Args:
            sizes (list): Input sizes
            times (list): Corresponding execution times
            
        Returns:
            dict: Fitted curves and their parameters
        """
        # Convert to numpy arrays for fitting
        x = np.array(sizes)
        y = np.array(times)
        
        # Define common scaling functions
        def linear(x, a, b):
            return a * x + b
            
        def logarithmic(x, a, b):
            return a * np.log(x) + b
            
        def quadratic(x, a, b, c):
            return a * x**2 + b * x + c
            
        def exponential(x, a, b, c):
            return a * np.exp(b * x) + c
            
        # Try fitting different models
        models = {
            'linear': (linear, (1, 0)),
            'logarithmic': (logarithmic, (1, 0)),
            'quadratic': (quadratic, (1, 1, 0)),
            'exponential': (exponential, (1, 0.1, 0))
        }
        
        fits = {}
        
        for name, (func, p0) in models.items():
            try:
                from scipy.optimize import curve_fit
                params, covariance = curve_fit(func, x, y, p0=p0, maxfev=10000)
                y_pred = func(x, *params)
                
                # Calculate R-squared
                ss_total = np.sum((y - np.mean(y))**2)
                ss_residual = np.sum((y - y_pred)**2)
                r_squared = 1 - (ss_residual / ss_total)
                
                fits[name] = {
                    'parameters': params.tolist(),
                    'r_squared': r_squared,
                    'rmse': np.sqrt(np.mean((y - y_pred)**2))
                }
            except Exception as e:
                logger.warning(f"Failed to fit {name} model: {e}")
                fits[name] = {'error': str(e)}
        
        return fits


class ResourceProfiler:
    """Profiles resource usage during algorithm execution."""
    
    def __init__(self):
        """Initialize resource profiler."""
        # Check for optional dependencies
        self.has_psutil = self._check_dependency('psutil')
        self.has_memory_profiler = self._check_dependency('memory_profiler')

        
        
    def _check_dependency(self, module_name):
        """Check if an optional dependency is available."""
        try:
            __import__(module_name)
            return True
        except ImportError:
            logger.warning(f"Optional dependency '{module_name}' not available.")
            return False
    
    def profile_memory(self, func, *args, **kwargs):
        """
        Profile memory usage of a function.
        
        Args:
            func (callable): Function to profile
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            tuple: (function result, memory usage statistics)
        """
        if not self.has_memory_profiler:
            logger.warning("Memory profiling requires 'memory_profiler' package.")
            result = func(*args, **kwargs)
            return result, None
            
        memory_usage = __import__('memory_profiler').memory_usage
        
        # Create wrapper to capture result
        def wrapper():
            nonlocal result
            result = func(*args, **kwargs)
        
        # Run memory profiling
        result = None
        mem_usage = memory_usage(
            (wrapper, (), {}),
            interval=0.1,
            include_children=True
        )
        
        stats = {
            'min_memory_mb': min(mem_usage),
            'max_memory_mb': max(mem_usage),
            'avg_memory_mb': sum(mem_usage) / len(mem_usage),
            'memory_timeline': mem_usage
        }
        
        return result, stats
    
    def profile_cpu_and_memory(self, func, *args, **kwargs):
        """
        Profile CPU and memory usage of a function.
        
        Args:
            func (callable): Function to profile
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            tuple: (function result, resource usage statistics)
        """
        if not self.has_psutil:
            logger.warning("Resource profiling requires 'psutil' package.")
            result = func(*args, **kwargs)
            return result, None
            
        import psutil
        import threading
        import queue
        
        # Set up monitoring
        stats_queue = queue.Queue()
        stop_monitoring = threading.Event()
        
        # Monitoring thread function
        def monitor_resources():
            process = psutil.Process()
            
            while not stop_monitoring.is_set():
                cpu_percent = process.cpu_percent()
                memory_info = process.memory_info()
                
                stats_queue.put({
                    'timestamp': time.time(),
                    'cpu_percent': cpu_percent,
                    'rss_memory_bytes': memory_info.rss,
                    'vms_memory_bytes': memory_info.vms
                })
                
                time.sleep(0.1)
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_resources)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Execute the function
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
        finally:
            end_time = time.time()
            stop_monitoring.set()
            monitor_thread.join(timeout=1.0)
        
        # Collect and process stats
        resource_stats = []
        while not stats_queue.empty():
            resource_stats.append(stats_queue.get())
        
        # Calculate summary statistics
        if resource_stats:
            cpu_values = [stat['cpu_percent'] for stat in resource_stats]
            rss_values = [stat['rss_memory_bytes'] / (1024 * 1024) for stat in resource_stats]  # Convert to MB
            
            summary = {
                'execution_time': end_time - start_time,
                'avg_cpu_percent': sum(cpu_values) / len(cpu_values),
                'max_cpu_percent': max(cpu_values),
                'avg_memory_mb': sum(rss_values) / len(rss_values),
                'max_memory_mb': max(rss_values),
                'detailed_timeline': resource_stats
            }
        else:
            summary = {
                'execution_time': end_time - start_time,
                'error': 'No resource stats collected'
            }
        
        return result, summary


class ParallelBenchmarker:
    """Runs benchmarks in parallel for faster execution."""
    
    def __init__(self, max_workers=None):
        """
        Initialize parallel benchmarker.
        
        Args:
            max_workers (int, optional): Maximum number of worker threads
        """
        self.max_workers = max_workers

    
    def parallel_benchmark(self, func_args_list, iterations=3, warmup=1):
        """
        Run multiple benchmarks in parallel.
        
        Args:
            func_args_list (list): List of (func, args, kwargs) tuples to benchmark
            iterations (int): Number of iterations per benchmark
            warmup (int): Number of warmup iterations
            
        Returns:
            list: Benchmark results for each function
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Create benchmark tasks
            futures = []
            
            for func, args, kwargs in func_args_list:
                # Create a benchmark task for each function
                def benchmark_task():
                    runner = BenchmarkRunner()
                    result, _ = runner.run_benchmark(
                        func=func,
                        args=args,
                        kwargs=kwargs,
                        iterations=iterations,
                        warmup=warmup
                    )
                    return result
                
                futures.append(executor.submit(benchmark_task))
            
            # Collect results
            results = []
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Benchmark failed: {e}")
                    results.append({'error': str(e)})
            
            return results
        


class CrossValidationBenchmarker:
    """Benchmarks algorithms using cross-validation techniques."""
    
    def __init__(self, benchmark_runner=None):
        """
        Initialize cross-validation benchmarker.
        
        Args:
            benchmark_runner (BenchmarkRunner, optional): Runner for benchmarks
        """
        self.benchmark_runner = benchmark_runner if benchmark_runner else BenchmarkRunner()
    
    def cross_validate(self, func, data_generator, folds=5, iterations=3, metadata=None):
        """
        Benchmark using cross-validation.
        
        Args:
            func (callable): Function to benchmark
            data_generator (callable): Function that generates training/testing data for each fold
            folds (int): Number of cross-validation folds
            iterations (int): Number of iterations per fold
            metadata (dict, optional): Additional metadata
            
        Returns:
            dict: Cross-validation results
        """
        if metadata is None:
            metadata = {}
        
        fold_results = []
        
        for fold in range(folds):
            logger.info(f"Running fold {fold+1}/{folds}")
            
            # Generate data for this fold
            train_data, test_data = data_generator(fold, folds)
            
            # Define fold-specific function that uses the generated data
            def fold_func():
                return func(train_data, test_data)
            
            # Run benchmark
            result, _ = self.benchmark_runner.run_benchmark(
                func=fold_func,
                iterations=iterations,
                operation_type="cross_validation",
                metadata={**metadata, 'fold': fold}
            )
            
            fold_results.append(result)
        
        # Calculate aggregate statistics
        mean_times = [r['mean_execution_time'] for r in fold_results]
        
        cv_results = {
            'fold_results': fold_results,
            'mean_execution_time': statistics.mean(mean_times),
            'std_dev_across_folds': statistics.stdev(mean_times) if len(mean_times) > 1 else 0,
            'min_fold_time': min(mean_times),
            'max_fold_time': max(mean_times)
        }
        
        return cv_results


def cost_estimator(circuit, hardware_params=None):
    """
    Estimate the cost of running a quantum circuit based on various parameters.
    
    Args:
        circuit: The quantum circuit to be estimated
        hardware_params (dict, optional): Dictionary of hardware parameters for cost calculation
        
    Returns:
        float: Estimated cost of running the circuit
    """
    # Default hardware parameters if none provided
    if hardware_params is None:
        hardware_params = {
            'qubit_cost': 1.0,
            'gate_cost': 0.1,
            'measurement_cost': 0.5,
            'time_cost': 2.0
        }
    
    # Simple cost model - you can make this more sophisticated
    num_qubits = getattr(circuit, 'num_qubits', 0)
    if not num_qubits and hasattr(circuit, 'qubits'):
        num_qubits = len(circuit.qubits)
    
    num_gates = getattr(circuit, 'num_gates', 0)
    if not num_gates and hasattr(circuit, 'operations'):
        num_gates = len(circuit.operations) 
    
    num_measurements = getattr(circuit, 'num_measurements', 0)
    if not num_measurements:
        # Estimate based on circuit properties
        num_measurements = num_qubits  # Simple estimate
    
    # Circuit depth as a proxy for time
    circuit_depth = getattr(circuit, 'depth', 1)
    
    # Calculate total cost
    total_cost = (num_qubits * hardware_params['qubit_cost'] +
                 num_gates * hardware_params['gate_cost'] +
                 num_measurements * hardware_params['measurement_cost'] +
                 circuit_depth * hardware_params['time_cost'])
    
    return total_cost

# Export common utilities
__all__ = [
    'Timer', 
    'PerformanceCollector', 
    'BenchmarkRunner',
    'ScalabilityAnalyzer',
    'ResourceProfiler',
    'ParallelBenchmarker',
    'CrossValidationBenchmarker',
    'cost_estimator'
]