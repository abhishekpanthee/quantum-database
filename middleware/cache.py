"""
Result Caching

This module implements a caching system for quantum database query results,
optimizing performance by storing and retrieving previously computed results.
"""

import logging
import time
import hashlib
import json
import threading
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timedelta
import pickle

logger = logging.getLogger(__name__)

class CacheEntry:
    """
    Represents a single entry in the result cache.
    """
    
    def __init__(self, key: str, value: Any, ttl: int = 3600):
        """
        Initialize a cache entry.
        
        Args:
            key: Cache key
            value: Cached value
            ttl: Time to live in seconds
        """
        self.key = key
        self.value = value
        self.creation_time = datetime.now()
        self.last_access_time = self.creation_time
        self.ttl = ttl
        self.access_count = 0

    def is_expired(self) -> bool:
        """
        Check if this entry has expired.
        
        Returns:
            True if expired, False otherwise
        """
        return (datetime.now() - self.creation_time).total_seconds() > self.ttl

    def touch(self) -> None:
        """Update the last access time and increment access count."""
        self.last_access_time = datetime.now()
        self.access_count += 1


class QueryCache:
    """
    Cache for quantum database query results.
    """
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600, 
                 cleanup_interval: int = 300):
        """
        Initialize the query cache.
        
        Args:
            max_size: Maximum number of entries in the cache
            default_ttl: Default time to live in seconds
            cleanup_interval: Interval for cleanup in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cleanup_interval = cleanup_interval
        
        self.cache: Dict[str, CacheEntry] = {}
        self.lock = threading.RLock()
        
        # Start cleanup thread
        self.running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop)
        self.cleanup_thread.daemon = True
        self.cleanup_thread.start()
        
        logger.info(f"Query cache initialized with max size {max_size}, TTL {default_ttl}s")

    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value, or None if not found
        """
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                
                if entry.is_expired():
                    logger.debug(f"Cache entry {key} expired")
                    del self.cache[key]
                    return None
                    
                entry.touch()
                logger.debug(f"Cache hit for {key}")
                return entry.value
                
            logger.debug(f"Cache miss for {key}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set a value in the cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds, or None to use default
        """
        ttl = ttl if ttl is not None else self.default_ttl
        
        with self.lock:
            # If at max size, evict an entry
            if len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_entry()
                
            self.cache[key] = CacheEntry(key, value, ttl)
            logger.debug(f"Cached entry {key} with TTL {ttl}s")

    def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted, False if not found
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                logger.debug(f"Deleted cache entry {key}")
                return True
                
            return False

    def clear(self) -> None:
        """Clear all entries from the cache."""
        with self.lock:
            self.cache.clear()
            logger.info("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache.
        
        Returns:
            Dictionary with cache statistics
        """
        with self.lock:
            total_size = len(self.cache)
            expired_count = sum(1 for entry in self.cache.values() if entry.is_expired())
            
            # Calculate average age and access count
            if total_size > 0:
                avg_age = sum((datetime.now() - entry.creation_time).total_seconds() 
                             for entry in self.cache.values()) / total_size
                avg_access = sum(entry.access_count for entry in self.cache.values()) / total_size
            else:
                avg_age = 0
                avg_access = 0
                
            return {
                'total_entries': total_size,
                'max_size': self.max_size,
                'expired_entries': expired_count,
                'usage_percent': (total_size / self.max_size) * 100 if self.max_size > 0 else 0,
                'avg_entry_age_seconds': avg_age,
                'avg_access_count': avg_access
            }

    def stop(self) -> None:
        """Stop the cache cleanup thread."""
        self.running = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=self.cleanup_interval + 1)

    def _evict_entry(self) -> None:
        """Evict an entry from the cache using LRU policy."""
        if not self.cache:
            return
            
        # Find least recently used entry
        lru_key = min(self.cache.items(), 
                     key=lambda x: x[1].last_access_time)[0]
                     
        del self.cache[lru_key]
        logger.debug(f"Evicted LRU cache entry {lru_key}")

    def _cleanup_loop(self) -> None:
        """Background thread that periodically cleans up expired entries."""
        while self.running:
            time.sleep(self.cleanup_interval)
            try:
                self._remove_expired()
            except Exception as e:
                logger.error(f"Error in cache cleanup: {str(e)}")

    def _remove_expired(self) -> int:
        """
        Remove all expired entries from the cache.
        
        Returns:
            Number of entries removed
        """
        with self.lock:
            expired_keys = [k for k, v in self.cache.items() if v.is_expired()]
            
            for key in expired_keys:
                del self.cache[key]
                
            if expired_keys:
                logger.debug(f"Removed {len(expired_keys)} expired cache entries")
                
            return len(expired_keys)


class ResultCache:
    """
    Cache for quantum database query results with advanced features.
    """
    
    def __init__(self, max_size_mb: int = 100, default_ttl: int = 3600):
        """
        Initialize the result cache.
        
        Args:
            max_size_mb: Maximum cache size in megabytes
            default_ttl: Default time to live in seconds
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.default_ttl = default_ttl
        self.current_size_bytes = 0
        
        self.query_cache = QueryCache(max_size=10