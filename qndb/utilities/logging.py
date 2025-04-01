"""
Logging framework for quantum database operations.

This module provides structured logging capabilities tailored for quantum
database operations, including circuit execution tracking, error handling,
and performance monitoring.
"""

import logging
import sys
import os
import json
import time
from datetime import datetime
import threading
import traceback

# Default configuration
DEFAULT_LOG_LEVEL = logging.INFO
DEFAULT_LOG_FORMAT = '%(asctime)s [%(levelname)s] [%(name)s] [%(threadName)s] %(message)s'
DEFAULT_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
DEFAULT_LOG_DIR = 'logs'
DEFAULT_MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5

# Thread-local storage for context information
_thread_local = threading.local()


def configure_logging(config=None):
    """
    Configure the logging system based on provided configuration.
    
    Args:
        config (dict, optional): Logging configuration dictionary
    
    Returns:
        logging.Logger: Root logger instance
    """
    if config is None:
        config = {}
    
    log_level = config.get('log_level', DEFAULT_LOG_LEVEL)
    log_format = config.get('log_format', DEFAULT_LOG_FORMAT)
    date_format = config.get('date_format', DEFAULT_DATE_FORMAT)
    log_to_console = config.get('log_to_console', True)
    log_to_file = config.get('log_to_file', False)
    log_dir = config.get('log_dir', DEFAULT_LOG_DIR)
    log_filename = config.get('log_filename', 'quantum_db.log')
    max_log_size = config.get('max_log_size', DEFAULT_MAX_LOG_SIZE)
    backup_count = config.get('backup_count', DEFAULT_BACKUP_COUNT)
    
    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    formatter = logging.Formatter(log_format, date_format)
    
    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # File handler
    if log_to_file:
        try:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, log_filename)
            
            if config.get('use_rotating_file', True):
                from logging.handlers import RotatingFileHandler
                file_handler = RotatingFileHandler(
                    log_path, 
                    maxBytes=max_log_size,
                    backupCount=backup_count
                )
            else:
                file_handler = logging.FileHandler(log_path)
            
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            root_logger.error(f"Failed to configure file logging: {e}")
    
    return root_logger


class ContextAdapter(logging.LoggerAdapter):
    """Logger adapter that adds context information to log records."""
    
    def process(self, msg, kwargs):
        """Add context information to the log message."""
        # Get context from thread-local storage
        context = getattr(_thread_local, 'context', {})
        
        # Format context as string if present
        context_str = ""
        if context:
            context_parts = [f"{k}={v}" for k, v in context.items()]
            context_str = f"[{' '.join(context_parts)}] "
        
        return f"{context_str}{msg}", kwargs


def get_logger(name):
    """
    Get a logger with the specified name, enhanced with context capabilities.
    
    Args:
        name (str): Logger name
    
    Returns:
        ContextAdapter: Context-aware logger
    """
    logger = logging.getLogger(name)
    return ContextAdapter(logger, {})


def set_context(key, value):
    """
    Set a context value for the current thread.
    
    Args:
        key (str): Context key
        value: Context value
    """
    if not hasattr(_thread_local, 'context'):
        _thread_local.context = {}
    
    _thread_local.context[key] = value


def clear_context():
    """Clear all context values for the current thread."""
    if hasattr(_thread_local, 'context'):
        _thread_local.context.clear()


def with_context(context_dict):
    """
    Decorator for adding context to a function.
    
    Args:
        context_dict (dict): Context dictionary or function returning a dict
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Save original context
            original_context = getattr(_thread_local, 'context', {}).copy()
            
            try:
                # Apply new context
                context = context_dict
                if callable(context):
                    context = context(*args, **kwargs)
                
                if not hasattr(_thread_local, 'context'):
                    _thread_local.context = {}
                
                for key, value in context.items():
                    _thread_local.context[key] = value
                
                # Call the function
                return func(*args, **kwargs)
            finally:
                # Restore original context
                _thread_local.context = original_context
        
        return wrapper
    return decorator


class CircuitLogger:
    """Logger specialized for quantum circuit operations."""
    
    def __init__(self, logger_name="quantum.circuit"):
        """
        Initialize circuit logger.
        
        Args:
            logger_name (str): Logger name
        """
        self.logger = get_logger(logger_name)
        self.circuit_id = None
    
    def start_circuit(self, circuit_id, metadata=None):
        """
        Log the start of a circuit execution.
        
        Args:
            circuit_id (str): Circuit identifier
            metadata (dict, optional): Additional metadata
        """
        self.circuit_id = circuit_id
        set_context('circuit_id', circuit_id)
        
        metadata_str = ""
        if metadata:
            metadata_str = f" metadata={json.dumps(metadata)}"
        
        self.logger.info(f"Circuit execution started{metadata_str}")
    
    def log_gate(self, gate_name, qubits, parameters=None):
        """
        Log a gate operation.
        
        Args:
            gate_name (str): Name of the gate
            qubits (list): Qubits the gate acts on
            parameters (dict, optional): Gate parameters
        """
        params_str = ""
        if parameters:
            params_str = f" params={json.dumps(parameters)}"
        
        self.logger.debug(f"Gate {gate_name} applied to qubits {qubits}{params_str}")
    
    def log_measurement(self, qubits, results):
        """
        Log measurement results.
        
        Args:
            qubits (list): Measured qubits
            results (dict): Measurement results
        """
        self.logger.info(f"Measurement on qubits {qubits}: {json.dumps(results)}")
    
    def end_circuit(self, success=True, error=None):
        """
        Log the end of a circuit execution.
        
        Args:
            success (bool): Whether the circuit executed successfully
            error (Exception, optional): Error if execution failed
        """
        if success:
            self.logger.info(f"Circuit execution completed successfully")
        else:
            error_info = ""
            if error:
                error_info = f": {str(error)}"
            self.logger.error(f"Circuit execution failed{error_info}")
        
        clear_context()
        self.circuit_id = None


class QueryLogger:
    """Logger specialized for quantum database queries."""
    
    def __init__(self, logger_name="quantum.query"):
        """
        Initialize query logger.
        
        Args:
            logger_name (str): Logger name
        """
        self.logger = get_logger(logger_name)
        self.start_time = None
        self.query_id = None
    
    def start_query(self, query_id, query_text):
        """
        Log the start of a query execution.
        
        Args:
            query_id (str): Query identifier
            query_text (str): Query text
        """
        self.query_id = query_id
        self.start_time = time.time()
        
        set_context('query_id', query_id)
        
        # Truncate very long queries in the log
        log_query = query_text
        if len(log_query) > 1000:
            log_query = log_query[:997] + "..."
        
        self.logger.info(f"Query execution started: {log_query}")
    
    def log_plan(self, execution_plan):
        """
        Log the query execution plan.
        
        Args:
            execution_plan (dict): Query execution plan
        """
        self.logger.debug(f"Execution plan: {json.dumps(execution_plan)}")
    
    def log_step(self, step_name, details=None):
        """
        Log a query execution step.
        
        Args:
            step_name (str): Step name
            details (dict, optional): Step details
        """
        details_str = ""
        if details:
            details_str = f": {json.dumps(details)}"
        
        self.logger.debug(f"Query step '{step_name}'{details_str}")
    
    def end_query(self, success=True, result_summary=None, error=None):
        """
        Log the end of a query execution.
        
        Args:
            success (bool): Whether the query executed successfully
            result_summary (dict, optional): Summary of query results
            error (Exception, optional): Error if execution failed
        """
        duration = None
        if self.start_time:
            duration = time.time() - self.start_time
        
        if success:
            summary_str = ""
            if result_summary:
                summary_str = f": {json.dumps(result_summary)}"
            
            duration_str = ""
            if duration:
                duration_str = f" in {duration:.3f}s"
            
            self.logger.info(f"Query execution completed{duration_str}{summary_str}")
        else:
            error_info = ""
            if error:
                error_info = f": {str(error)}"
            
            duration_str = ""
            if duration:
                duration_str = f" after {duration:.3f}s"
            
            self.logger.error(f"Query execution failed{duration_str}{error_info}")
            
            if error and self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(f"Error traceback: {traceback.format_exc()}")
        
        clear_context()
        self.query_id = None
        self.start_time = None


class PerformanceLogger:
    """Logger specialized for performance metrics."""
    
    def __init__(self, logger_name="quantum.performance"):
        """
        Initialize performance logger.
        
        Args:
            logger_name (str): Logger name
        """
        self.logger = get_logger(logger_name)
    
    def log_execution_time(self, operation, execution_time, metadata=None):
        """
        Log execution time for an operation.
        
        Args:
            operation (str): Operation name
            execution_time (float): Execution time in seconds
            metadata (dict, optional): Additional metadata
        """
        metadata_str = ""
        if metadata:
            metadata_str = f" metadata={json.dumps(metadata)}"
        
        self.logger.info(f"Operation '{operation}' completed in {execution_time:.6f}s{metadata_str}")
    
    def log_resource_usage(self, operation, cpu_percent, memory_mb, metadata=None):
        """
        Log resource usage for an operation.
        
        Args:
            operation (str): Operation name
            cpu_percent (float): CPU usage percentage
            memory_mb (float): Memory usage in MB
            metadata (dict, optional): Additional metadata
        """
        metadata_str = ""
        if metadata:
            metadata_str = f" metadata={json.dumps(metadata)}"
        
        self.logger.info(
            f"Resource usage for '{operation}': CPU={cpu_percent:.1f}%, "
            f"Memory={memory_mb:.2f}MB{metadata_str}"
        )
    
    def log_benchmark(self, benchmark_results):
        """
        Log benchmark results.
        
        Args:
            benchmark_results (dict): Benchmark results
        """
        self.logger.info(f"Benchmark results: {json.dumps(benchmark_results)}")


class LogAnalyzer:
    """Analyzes log files to extract insights."""
    
    def __init__(self, log_file=None):
        """
        Initialize log analyzer.
        
        Args:
            log_file (str, optional): Path to log file
        """
        self.log_file = log_file
    
    def parse_logs(self, start_time=None, end_time=None, log_level=None):
        """
        Parse logs within a time range and level.
        
        Args:
            start_time (datetime, optional): Start time filter
            end_time (datetime, optional): End time filter
            log_level (str, optional): Filter by log level
            
        Returns:
            list: Parsed log entries
        """
        if not self.log_file or not os.path.exists(self.log_file):
            raise ValueError(f"Log file not found: {self.log_file}")
        
        # Parse log level string to int if provided
        level_filter = None
        if log_level:
            level_filter = getattr(logging, log_level.upper(), None)
            if level_filter is None:
                raise ValueError(f"Invalid log level: {log_level}")
        
        # Convert datetime objects to strings for comparison
        start_str = start_time.strftime(DEFAULT_DATE_FORMAT) if start_time else None
        end_str = end_time.strftime(DEFAULT_DATE_FORMAT) if end_time else None
        
        entries = []
        
        with open(self.log_file, 'r') as f:
            for line in f:
                try:
                    # Extract timestamp and level
                    parts = line.split('[', 2)
                    if len(parts) < 3:
                        continue
                    
                    timestamp_str = parts[0].strip()
                    level_str = parts[1].strip().rstrip(']')
                    
                    # Apply time filter
                    if start_str and timestamp_str < start_str:
                        continue
                    if end_str and timestamp_str > end_str:
                        continue
                    
                    # Apply level filter
                    if level_filter is not None:
                        level_int = getattr(logging, level_str, None)
                        if level_int is None or level_int < level_filter:
                            continue
                    
                    # Parse the entry
                    entry = {
                        'timestamp': timestamp_str,
                        'level': level_str,
                        'message': line.strip()
                    }
                    
                    entries.append(entry)
                except Exception:
                    # Skip malformed lines
                    continue
        
        return entries
    
    def extract_performance_metrics(self):
        """
        Extract performance metrics from logs.
        
        Returns:
            dict: Performance metrics by operation
        """
        metrics = {}
        
        entries = self.parse_logs(log_level='INFO')
        
        for entry in entries:
            message = entry['message']
            
            # Look for execution time logs
            if "completed in" in message and "operation" in message.lower():
                try:
                    # Extract operation name and time
                    operation = message.split("'")[1]
                    time_str = message.split("in ")[1].split("s")[0]
                    execution_time = float(time_str)
                    
                    if operation not in metrics:
                        metrics[operation] = {
                            'count': 0,
                            'total_time': 0,
                            'min_time': float('inf'),
                            'max_time': 0,
                            'times': []
                        }
                    
                    metrics[operation]['count'] += 1
                    metrics[operation]['total_time'] += execution_time
                    metrics[operation]['min_time'] = min(
                        metrics[operation]['min_time'], execution_time
                    )
                    metrics[operation]['max_time'] = max(
                        metrics[operation]['max_time'], execution_time
                    )
                    metrics[operation]['times'].append(execution_time)
                except Exception:
                    continue
        
        # Calculate averages
        for operation, data in metrics.items():
            if data['count'] > 0:
                data['avg_time'] = data['total_time'] / data['count']
            
            # Don't need to keep all individual times in the summary
            if 'times' in data:
                del data['times']
        
        return metrics
    
    def extract_error_summary(self):
        """
        Extract error summary from logs.
        
        Returns:
            dict: Error summary by error type
        """
        errors = {}
        
        entries = self.parse_logs(log_level='ERROR')
        
        for entry in entries:
            message = entry['message']
            
            # Extract error type if present
            error_type = "Unknown Error"
            if ":" in message:
                parts = message.split(":", 1)
                prefix = parts[0]
                
                # Try to extract most specific error type
                if "Exception" in prefix or "Error" in prefix:
                    words = prefix.split()
                    for word in reversed(words):
                        if "Exception" in word or "Error" in word:
                            error_type = word
                            break
            
            if error_type not in errors:
                errors[error_type] = {
                    'count': 0,
                    'examples': []
                }
            
            errors[error_type]['count'] += 1
            
            # Keep track of unique examples (up to 3)
            if len(errors[error_type]['examples']) < 3:
                if message not in errors[error_type]['examples']:
                    errors[error_type]['examples'].append(message)
        
        return errors


# Initialize module-level logger
logger = get_logger(__name__)


# Export common utilities
__all__ = [
    'configure_logging',
    'get_logger',
    'set_context',
    'clear_context',
    'with_context',
    'CircuitLogger',
    'QueryLogger',
    'PerformanceLogger',
    'LogAnalyzer'
]