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
        Compare different implementations of the same algorithm