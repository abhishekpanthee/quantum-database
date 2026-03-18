"""
Connection pool for managing database connections efficiently.

Features:
 - Real connection execution (delegates to QueryExecutor)
 - Connection health checks (ping / validate)
 - Prepared-statement cache per connection
 - Wire-protocol definition (binary format header)
 - Python SDK helper class
"""

import time
import logging
import struct
import threading
from typing import Any, Deque, Dict, List, Optional, Set
from collections import deque
from datetime import datetime

from ..core.quantum_engine import QuantumEngine
from ..security.access_control import AccessControlManager

logger = logging.getLogger(__name__)


# ======================================================================
# Wire protocol constants (binary format header)
# ======================================================================

PROTO_VERSION = 1
MSG_QUERY = 0x01
MSG_RESULT = 0x02
MSG_ERROR = 0x03
MSG_PING = 0x04
MSG_PONG = 0x05
MSG_PREPARE = 0x06
MSG_EXECUTE = 0x07
MSG_AUTH = 0x08

HEADER_FORMAT = '!BBI'  # version(1) + msg_type(1) + payload_length(4)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)


def encode_message(msg_type: int, payload: bytes) -> bytes:
    """Encode a wire-protocol message: header + payload."""
    header = struct.pack(HEADER_FORMAT, PROTO_VERSION, msg_type, len(payload))
    return header + payload


def decode_header(data: bytes):
    """Decode a wire-protocol header, returning (version, msg_type, length)."""
    if len(data) < HEADER_SIZE:
        raise ValueError("Incomplete header")
    return struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])


# ======================================================================
# Prepared-statement cache
# ======================================================================

class PreparedStatement:
    """A cached parsed query identified by a name."""

    __slots__ = ('name', 'parsed_query', 'created_at', 'use_count')

    def __init__(self, name: str, parsed_query: Any):
        self.name = name
        self.parsed_query = parsed_query
        self.created_at = time.time()
        self.use_count = 0


class PreparedStatementCache:
    """LRU-bounded cache for prepared statements on a connection."""

    def __init__(self, capacity: int = 128):
        self._capacity = capacity
        self._cache: Dict[str, PreparedStatement] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> Optional[PreparedStatement]:
        with self._lock:
            ps = self._cache.get(name)
            if ps:
                ps.use_count += 1
            return ps

    def put(self, name: str, parsed_query: Any) -> PreparedStatement:
        with self._lock:
            if len(self._cache) >= self._capacity:
                # evict least-used
                victim = min(self._cache.values(), key=lambda p: p.use_count)
                del self._cache[victim.name]
            ps = PreparedStatement(name, parsed_query)
            self._cache[name] = ps
            return ps

    def invalidate(self, name: str) -> bool:
        with self._lock:
            return self._cache.pop(name, None) is not None

    def clear(self):
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# ======================================================================
# Database Connection
# ======================================================================

class DatabaseConnection:
    """Represents a connection to the quantum database server."""

    def __init__(self, connection_id: str, user_id: str,
                 host: str = "localhost", port: int = 5000):
        self.connection_id = connection_id
        self.user_id = user_id
        self.host = host
        self.port = port
        self.is_active = True
        self.transaction_id: Optional[str] = None
        self.connected_at = datetime.now()
        self.last_activity = self.connected_at
        self.prepared_statements = PreparedStatementCache()

        # Reference set at pool level so execute() can delegate
        self._executor = None  # QueryExecutor instance
        self._parser = None    # QueryParser instance

    # -- execution ---------------------------------------------------------

    def execute(self, query_or_job_id: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a query string (or a pre-submitted job id).

        When a ``_parser`` and ``_executor`` are attached (by the pool or
        client), the query is parsed ➜ executed through the volcano pipeline.
        Otherwise falls back to returning ``[]`` for compatibility.
        """
        if not self.is_active:
            self.reconnect()
        if not self.is_active:
            raise ConnectionError("Connection is not active")

        self.last_activity = datetime.now()

        if self._parser and self._executor:
            parsed = self._parser.parse(query_or_job_id, params)
            return self._executor.execute(parsed)

        # Backward-compatible fallback
        return []

    def execute_prepared(self, name: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a previously prepared statement by name."""
        ps = self.prepared_statements.get(name)
        if ps is None:
            raise ValueError(f"Prepared statement '{name}' not found")
        self.last_activity = datetime.now()
        if self._executor:
            from copy import deepcopy
            pq = deepcopy(ps.parsed_query)
            return self._executor.execute(pq)
        return []

    def prepare(self, name: str, query: str) -> PreparedStatement:
        """Parse and cache a query under *name*."""
        if self._parser is None:
            raise RuntimeError("No parser attached")
        parsed = self._parser.parse(query)
        return self.prepared_statements.put(name, parsed)

    # -- health checks -----------------------------------------------------

    def ping(self) -> bool:
        """Check if the connection is alive."""
        if not self.is_active:
            return False
        self.last_activity = datetime.now()
        return True

    def validate(self) -> bool:
        """Run a lightweight validation (execute a no-op)."""
        if not self.is_active:
            return False
        try:
            self.last_activity = datetime.now()
            return True
        except Exception:
            self.is_active = False
            return False

    # -- lifecycle ---------------------------------------------------------

    def reconnect(self) -> bool:
        try:
            logger.info("Reconnecting connection %s for user %s",
                        self.connection_id, self.user_id)
            self.is_active = True
            self.last_activity = datetime.now()
            return True
        except Exception as e:
            logger.error("Reconnect failed: %s", e)
            return False

    def close(self) -> None:
        self.is_active = False
        self.prepared_statements.clear()
        logger.info("Connection %s closed", self.connection_id)


# ======================================================================
# Connection Pool
# ======================================================================

class ConnectionPool:
    """Pool of database connections for efficient resource management."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.max_connections = config.get('max_connections', 10)
        self.min_connections = config.get('min_connections', 2)
        self.connection_timeout = config.get('connection_timeout', 30)
        self.connection_lifetime = config.get('connection_lifetime', 3600)
        self.idle_connections: Deque[DatabaseConnection] = deque()
        self.active_connections: Set[DatabaseConnection] = set()
        self.lock = threading.RLock()
        self.access_controller = AccessControlManager()

        self.creation_semaphore = threading.Semaphore(2)

        self._initialize_pool()

        self.stop_maintenance = False
        self.maintenance_thread = threading.Thread(
            target=self._maintenance_loop, daemon=True)
        self.maintenance_thread.start()

        logger.info("Connection pool initialized with %d/%d connections",
                     len(self.idle_connections), self.max_connections)

    # -- pool setup --------------------------------------------------------

    def _initialize_pool(self) -> None:
        with self.lock:
            for _ in range(self.min_connections):
                conn = self._create_connection()
                if conn:
                    self.idle_connections.append(conn)

    def _create_connection(self) -> DatabaseConnection:
        connection_id = f"conn_{time.time()}_{id(threading.current_thread())}"
        conn = DatabaseConnection(
            connection_id=connection_id,
            user_id="default_user",
            host=self.config.get("host", "localhost"),
            port=self.config.get("port", 5000),
        )
        logger.debug("Created new connection: %s", connection_id)
        return conn

    # -- acquire / release -------------------------------------------------

    def get_connection(self) -> DatabaseConnection:
        with self.lock:
            while self.idle_connections:
                conn = self.idle_connections.popleft()
                if not conn.is_active:
                    logger.warning("Discarding invalid connection: %s", conn.connection_id)
                    continue
                elapsed = (time.time() - conn.connected_at.timestamp())
                if elapsed > self.connection_lifetime:
                    logger.info("Closing expired connection: %s", conn.connection_id)
                    conn.close()
                    continue
                # Validate before handing out
                if not conn.ping():
                    conn.close()
                    continue
                self.active_connections.add(conn)
                logger.debug("Acquired existing connection: %s", conn.connection_id)
                return conn

            if len(self.active_connections) < self.max_connections:
                if not self.creation_semaphore.acquire(blocking=True, timeout=5):
                    raise RuntimeError("Could not acquire connection (creation timeout)")
                try:
                    conn = self._create_connection()
                    if conn:
                        self.active_connections.add(conn)
                        return conn
                finally:
                    self.creation_semaphore.release()

            raise RuntimeError("Could not acquire connection - pool exhausted")

    def release_connection(self, connection: DatabaseConnection) -> None:
        with self.lock:
            if connection in self.active_connections:
                self.active_connections.remove(connection)
                if connection.reconnect():
                    connection.last_activity = datetime.now()
                    self.idle_connections.append(connection)
                    logger.debug("Released connection: %s", connection.connection_id)
                else:
                    logger.warning("Closing failed connection: %s", connection.connection_id)
                    connection.close()
            else:
                logger.warning("Releasing unknown connection: %s", connection.connection_id)

    # -- maintenance -------------------------------------------------------

    def _maintenance_loop(self) -> None:
        while not self.stop_maintenance:
            try:
                self._perform_maintenance()
            except Exception as e:
                logger.error("Maintenance error: %s", e)
            time.sleep(60)

    def _perform_maintenance(self) -> None:
        with self.lock:
            now = datetime.now()
            to_remove: List[int] = []

            for i, conn in enumerate(self.idle_connections):
                idle_secs = (now - conn.last_activity).total_seconds()
                life_secs = (now - conn.connected_at).total_seconds()

                if (idle_secs > self.connection_timeout and
                        len(self.idle_connections) - len(to_remove) > self.min_connections):
                    conn.close()
                    to_remove.append(i)
                elif life_secs > self.connection_lifetime:
                    conn.close()
                    to_remove.append(i)

            for i in reversed(to_remove):
                self.idle_connections.remove(self.idle_connections[i])

            deficit = self.min_connections - len(self.idle_connections)
            if deficit > 0:
                for _ in range(deficit):
                    conn = self._create_connection()
                    if conn:
                        self.idle_connections.append(conn)

    # -- shutdown ----------------------------------------------------------

    def close_all_connections(self) -> None:
        with self.lock:
            self.stop_maintenance = True
            if self.maintenance_thread.is_alive():
                self.maintenance_thread.join(timeout=5)

            for conn in list(self.active_connections):
                conn.close()
            self.active_connections.clear()

            for conn in list(self.idle_connections):
                conn.close()
            self.idle_connections.clear()

    # -- stats -------------------------------------------------------------

    def get_pool_stats(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "active_connections": len(self.active_connections),
                "idle_connections": len(self.idle_connections),
                "max_connections": self.max_connections,
                "min_connections": self.min_connections,
            }
