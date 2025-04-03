"""
Connection pool for managing database connections efficiently.
"""

import time
import logging
import threading
from typing import Dict, List, Any, Optional, Set, Deque
from collections import deque
import queue
from datetime import datetime

from ..core.quantum_engine import QuantumEngine
from ..security.access_control import AccessControlManager

logger = logging.getLogger(__name__)

class DatabaseConnection:
    """Represents a connection to the quantum database server."""
    
    def __init__(self, connection_id: str, user_id: str, host: str = "localhost", port: int = 5000):
        """
        Initialize a new database connection.
        
        Args:
            connection_id: Unique identifier for this connection
            user_id: ID of the user this connection belongs to
            host: Database server hostname
            port: Database server port
        """
        self.connection_id = connection_id
        self.user_id = user_id
        self.host = host
        self.port = port
        self.is_active = True
        self.transaction_id = None
        self.connected_at = datetime.now() if datetime else None
        self.last_activity = self.connected_at
        
    def execute(self, job_id: str) -> Any:
        """
        Execute a job on this connection.
        
        Args:
            job_id: ID of the job to execute
            
        Returns:
            Result of the execution
        """
        # Check if connection is active
        if not self.is_active:
            self.reconnect()
            
        if not self.is_active:
            raise ConnectionError("Connection is not active")
            
        # In a real implementation, this would send the job to the server
        # For this example, just simulate some results based on job_id
        self.last_activity = datetime.now() if datetime else None
        
        # Since this is not fully implemented yet, just return an empty list
        # Later this would return actual query results
        return []
    
    def reconnect(self) -> bool:
        """
        Attempt to reconnect the database connection.
        
        Returns:
            True if reconnection was successful, False otherwise
        """
        try:
            logger.info(f"Attempting to reconnect connection {self.connection_id} for user {self.user_id}")
            # In a real implementation, this would reconnect to the server
            # For now, just set is_active to True
            self.is_active = True
            self.last_activity = datetime.now() if datetime else None
            return True
        except Exception as e:
            logger.error(f"Failed to reconnect: {str(e)}")
            return False
    
    def close(self) -> None:
        """Close the database connection."""
        self.is_active = False
        logger.info(f"Connection {self.connection_id} closed")

class ConnectionPool:
    """Pool of database connections for efficient resource management."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the connection pool.
        
        Args:
            config: Configuration dictionary for connections
        """
        self.config = config
        self.max_connections = config.get('max_connections', 10)
        self.min_connections = config.get('min_connections', 2)
        self.connection_timeout = config.get('connection_timeout', 30)
        self.connection_lifetime = config.get('connection_lifetime', 3600)
        self.idle_connections = deque()
        self.active_connections = set()
        self.lock = threading.RLock()
        self.access_controller = AccessControlManager()
        
        # Connection creation semaphore to limit concurrent creation
        self.creation_semaphore = threading.Semaphore(2)
        
        # Initialize the minimum number of connections
        self._initialize_pool()
        
        # Start maintenance thread
        self.stop_maintenance = False
        self.maintenance_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self.maintenance_thread.start()
        
        logger.info("Connection pool initialized with %d/%d connections", 
                   len(self.idle_connections), self.max_connections)
    
    def _initialize_pool(self) -> None:
        """Initialize the connection pool with the minimum number of connections."""
        with self.lock:
            for _ in range(self.min_connections):
                connection = self._create_connection()
                if connection:
                    self.idle_connections.append(connection)
    
    def _create_connection(self) -> DatabaseConnection:
        """Create a new database connection."""
        connection_id = f"conn_{time.time()}_{id(threading.current_thread())}"
        user_id = "default_user"  # Placeholder for user ID
        connection = DatabaseConnection(
            connection_id=connection_id,
            user_id=user_id,
            host=self.config.get("host", "localhost"),
            port=self.config.get("port", 5000)
        )
        
        logger.debug("Created new connection: %s", connection_id)
        return connection
    
    def get_connection(self) -> DatabaseConnection:
        """
        Get a connection from the pool.
        
        Returns:
            DatabaseConnection
            
        Raises:
            RuntimeError: If no connection could be acquired
        """
        with self.lock:
            # Try to get an idle connection
            while self.idle_connections:
                connection = self.idle_connections.popleft()
                
                # Check if the connection is still valid
                if not connection.is_active:
                    logger.warning("Discarding invalid connection: %s", connection.connection_id)
                    continue
                
                # Check if the connection has exceeded its lifetime
                if (time.time() - connection.connected_at.timestamp()) > self.connection_lifetime:
                    logger.info("Closing connection that exceeded lifetime: %s", 
                               connection.connection_id)
                    connection.close()
                    continue
                
                # We found a valid connection
                self.active_connections.add(connection)
                logger.debug("Acquired existing connection: %s", connection.connection_id)
                return connection
            
            # No idle connections available, create a new one if possible
            if len(self.active_connections) < self.max_connections:
                # Use semaphore to limit concurrent connection creation
                if not self.creation_semaphore.acquire(blocking=True, timeout=5):
                    logger.warning("Connection creation semaphore timeout")
                    raise RuntimeError("Could not acquire connection (creation timeout)")
                
                try:
                    connection = self._create_connection()
                    if connection:
                        self.active_connections.add(connection)
                        return connection
                finally:
                    self.creation_semaphore.release()
            
            # If we get here, we couldn't get a connection
            logger.error("Could not acquire connection - pool exhausted")
            raise RuntimeError("Could not acquire connection - pool exhausted")
    
    def release_connection(self, connection: DatabaseConnection) -> None:
        """
        Return a connection to the pool.
        
        Args:
            connection: The connection to release
        """
        with self.lock:
            if connection in self.active_connections:
                self.active_connections.remove(connection)
                
                # Reset the connection before returning it to the pool
                if connection.reconnect():
                    connection.last_activity = datetime.now() if datetime else None
                    self.idle_connections.append(connection)
                    logger.debug("Released connection back to pool: %s", connection.connection_id)
                else:
                    logger.warning("Closing failed connection: %s", connection.connection_id)
                    connection.close()
            else:
                logger.warning("Attempt to release unknown connection: %s", connection.connection_id)
    
    def _maintenance_loop(self) -> None:
        """Background thread for pool maintenance."""
        while not self.stop_maintenance:
            try:
                self._perform_maintenance()
            except Exception as e:
                logger.error("Error in connection pool maintenance: %s", str(e))
            
            # Sleep for maintenance interval
            time.sleep(60)  # Check every minute
    
    def _perform_maintenance(self) -> None:
        """Perform pool maintenance: close idle and expired connections."""
        with self.lock:
            current_time = datetime.now()
            
            # Check idle connections
            idle_size = len(self.idle_connections)
            to_remove = []
            
            for i, conn in enumerate(self.idle_connections):
                # Close connections that have been idle for too long, but keep minimum connections
                if ((current_time - conn.last_activity).total_seconds() > self.connection_timeout and 
                    idle_size - len(to_remove) > self.min_connections):
                    logger.info("Closing idle connection: %s", conn.connection_id)
                    conn.close()
                    to_remove.append(i)
                
                # Close connections that have exceeded their lifetime
                elif (current_time - conn.connected_at).total_seconds() > self.connection_lifetime:
                    logger.info("Closing expired connection: %s", conn.connection_id)
                    conn.close()
                    to_remove.append(i)
            
            # Remove closed connections from idle list
            for i in reversed(to_remove):
                self.idle_connections.remove(self.idle_connections[i])
            
            # Ensure we have the minimum number of connections
            if len(self.idle_connections) < self.min_connections:
                needed = self.min_connections - len(self.idle_connections)
                logger.info("Creating %d connections to maintain minimum pool size", needed)
                
                for _ in range(needed):
                    connection = self._create_connection()
                    if connection:
                        self.idle_connections.append(connection)
            
            # Log pool status
            logger.debug("Connection pool status: %d active, %d idle", 
                       len(self.active_connections), len(self.idle_connections))
    
    def close_all_connections(self) -> None:
        """Close all connections in the pool."""
        with self.lock:
            # Stop maintenance thread
            self.stop_maintenance = True
            if self.maintenance_thread.is_alive():
                self.maintenance_thread.join(timeout=5)
            
            # Close all connections
            logger.info("Closing all connections in pool")
            
            for conn in list(self.active_connections):
                conn.close()
            self.active_connections.clear()
            
            for conn in list(self.idle_connections):
                conn.close()
            self.idle_connections.clear()
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the connection pool.
        
        Returns:
            Dictionary containing pool statistics
        """
        with self.lock:
            return {
                "active_connections": len(self.active_connections),
                "idle_connections": len(self.idle_connections),
                "max_connections": self.max_connections,
                "min_connections": self.min_connections
            }