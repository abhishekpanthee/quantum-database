"""
Middleware Cache Module

This module implements caching mechanisms for quantum database operations
to improve performance by avoiding redundant quantum computations.
"""

import time
import json
import hashlib
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
from functools import lru_cache

class QuantumResultCache:
    """Cache for storing results of quantum operations to avoid recomputation."""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """
        Initialize the quantum result cache.
        
        Args:
            max_size: Maximum number of items to store in cache
            ttl: Time-to-live for cache entries in seconds
        """
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._max_size = max_size
        self._ttl = ttl
    
    def _generate_key(self, circuit_data: Any, params: Dict[str, Any]) -> str:
        """
        Generate a unique cache key based on circuit data and parameters.
        
        Args:
            circuit_data: Quantum circuit or operation data
            params: Parameters associated with the operation
            
        Returns:
            A unique hash key for the operation
        """
        # Convert numpy arrays to lists for JSON serialization
        clean_params = {}
        for k, v in params.items():
            if isinstance(v, np.ndarray):
                clean_params[k] = v.tolist()
            else:
                clean_params[k] = v
                
        # Create a string representation of both circuit and parameters
        circuit_str = str(circuit_data)
        params_str = json.dumps(clean_params, sort_keys=True)
        combined = f"{circuit_str}:{params_str}"
        
        # Generate hash
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def get(self, circuit_data: Any, params: Dict[str, Any]) -> Optional[Any]:
        """
        Retrieve a result from cache if available and not expired.
        
        Args:
            circuit_data: Quantum circuit or operation data
            params: Parameters associated with the operation
            
        Returns:
            Cached result or None if not found or expired
        """
        key = self._generate_key(circuit_data, params)
        if key in self._cache:
            result, timestamp = self._cache[key]
            
            # Check if entry has expired
            if time.time() - timestamp <= self._ttl:
                return result
            
            # Remove expired entry
            del self._cache[key]
        
        return None
    
    def put(self, circuit_data: Any, params: Dict[str, Any], result: Any) -> None:
        """
        Store a result in the cache.
        
        Args:
            circuit_data: Quantum circuit or operation data
            params: Parameters associated with the operation
            result: Result to cache
        """
        # Evict entries if cache is full
        if len(self._cache) >= self._max_size:
            # Remove oldest entry (simple LRU implementation)
            oldest_key = min(self._cache.items(), key=lambda x: x[1][1])[0]
            del self._cache[oldest_key]
        
        key = self._generate_key(circuit_data, params)
        self._cache[key] = (result, time.time())
    
    def invalidate(self, pattern: Optional[str] = None) -> None:
        """
        Invalidate cache entries matching the given pattern.
        
        Args:
            pattern: Optional string pattern to match keys against
        """
        if pattern is None:
            self._cache.clear()
            return
            
        keys_to_remove = [k for k in self._cache.keys() if pattern in k]
        for key in keys_to_remove:
            del self._cache[key]
    
    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        current_time = time.time()
        active_entries = sum(1 for _, timestamp in self._cache.values() 
                           if current_time - timestamp <= self._ttl)
        
        return {
            "total_entries": len(self._cache),
            "active_entries": active_entries,
            "expired_entries": len(self._cache) - active_entries,
            "max_size": self._max_size,
            "ttl": self._ttl
        }


class QueryCache:
    """Specialized cache for quantum query results with query plan awareness."""
    
    def __init__(self, max_size: int = 500, ttl: int = 1800):
        """
        Initialize the query cache.
        
        Args:
            max_size: Maximum number of queries to cache
            ttl: Time-to-live for cache entries in seconds
        """
        self._result_cache = QuantumResultCache(max_size, ttl)
        self._query_plans: Dict[str, str] = {}  # Maps query hash to execution plan hash
    
    def _hash_query(self, query_string: str, query_params: Dict) -> str:
        """
        Generate a hash for a query string and its parameters.
        
        Args:
            query_string: SQL-like query string
            query_params: Query parameters
            
        Returns:
            Hash representing the query
        """
        query_data = f"{query_string}:{json.dumps(query_params, sort_keys=True)}"
        return hashlib.md5(query_data.encode()).hexdigest()
    
    def store_plan(self, query_string: str, query_params: Dict, plan_hash: str) -> None:
        """
        Store the execution plan hash for a query.
        
        Args:
            query_string: SQL-like query string
            query_params: Query parameters
            plan_hash: Hash of the execution plan
        """
        query_hash = self._hash_query(query_string, query_params)
        self._query_plans[query_hash] = plan_hash
    
    def get_result(self, query_string: str, query_params: Dict) -> Optional[Any]:
        """
        Get cached result for a query if available.
        
        Args:
            query_string: SQL-like query string
            query_params: Query parameters
            
        Returns:
            Cached result or None if not found
        """
        query_hash = self._hash_query(query_string, query_params)
        
        if query_hash in self._query_plans:
            plan_hash = self._query_plans[query_hash]
            return self._result_cache.get(plan_hash, query_params)
        
        return None
    
    def store_result(self, query_string: str, query_params: Dict, 
                    plan_hash: str, result: Any) -> None:
        """
        Store result for a query.
        
        Args:
            query_string: SQL-like query string
            query_params: Query parameters
            plan_hash: Hash of the execution plan
            result: Query result to cache
        """
        query_hash = self._hash_query(query_string, query_params)
        self._query_plans[query_hash] = plan_hash
        self._result_cache.put(plan_hash, query_params, result)
    
    def invalidate_query(self, query_string: str, query_params: Dict) -> None:
        """
        Invalidate cache for a specific query.
        
        Args:
            query_string: SQL-like query string
            query_params: Query parameters
        """
        query_hash = self._hash_query(query_string, query_params)
        if query_hash in self._query_plans:
            plan_hash = self._query_plans[query_hash]
            self._result_cache.invalidate(plan_hash)
            del self._query_plans[query_hash]
    
    def invalidate_by_table(self, table_name: str) -> None:
        """
        Invalidate all cached queries related to a specific table.
        
        Args:
            table_name: Name of the table
        """
        # This is a simplified implementation - a real system would need
        # to track table dependencies for queries
        keys_to_remove = []
        for query_hash, plan_hash in self._query_plans.items():
            # Simple heuristic: if table name appears in the query hash
            if table_name in query_hash:
                self._result_cache.invalidate(plan_hash)
                keys_to_remove.append(query_hash)
        
        for key in keys_to_remove:
            del self._query_plans[key]


# Decorator for caching function results
def cache_quantum_result(func):
    """
    Decorator for caching results of quantum operations.
    """
    # Use Python's built-in LRU cache with custom key function
    @lru_cache(maxsize=128)
    def cached_key(*args, **kwargs):
        # Generate a stable key from the arguments
        key_parts = [str(arg) for arg in args]
        key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
        return hashlib.md5(":".join(key_parts).encode()).hexdigest()
    
    def wrapper(*args, **kwargs):
        key = cached_key(*args, **kwargs)
        # Check if this is a cache hit
        if hasattr(wrapper, "_results") and key in wrapper._results:
            result, timestamp = wrapper._results[key]
            # Check TTL (30 minutes)
            if time.time() - timestamp < 1800:
                return result
                
        # Cache miss or expired, compute the result
        result = func(*args, **kwargs)
        
        # Initialize cache dictionary if it doesn't exist
        if not hasattr(wrapper, "_results"):
            wrapper._results = {}
            
        # Store the result with current timestamp
        wrapper._results[key] = (result, time.time())
        
        return result
        
    # Add cache control methods to the wrapper
    def clear_cache():
        if hasattr(wrapper, "_results"):
            wrapper._results.clear()
    
    wrapper.clear_cache = clear_cache
    return wrapper