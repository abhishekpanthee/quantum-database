"""
Integration & Ecosystem
~~~~~~~~~~~~~~~~~~~~~~~~

Adapters and connectors for enterprise data ecosystems:

* **JDBCODBCAdapter** — JDBC / ODBC driver adapter
* **SQLAlchemyDialect** — SQLAlchemy dialect for Python ORM
* **ArrowFlightServer** — Apache Arrow Flight for high-speed data transfer
* **KafkaConnector** — Apache Kafka connector for streaming ingestion
* **GraphQLLayer** — GraphQL API layer
* **MetricsExporter** — Prometheus / Grafana metrics export
* **TracingProvider** — OpenTelemetry distributed tracing
"""

import hashlib
import json
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from enum import Enum, auto
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

logger = logging.getLogger(__name__)


# ======================================================================
# JDBC / ODBC Adapter
# ======================================================================

class JDBCODBCAdapter:
    """JDBC / ODBC wire-protocol adapter.

    Translates incoming JDBC/ODBC calls into the internal query
    interface.  Provides ``connect``, ``execute``, ``fetch``,
    ``close`` verbs matching the standard DB-API 2.0 surface.

    Args:
        executor: Callable ``(query_str) -> List[Dict]`` that runs
            queries against the quantum database.
    """

    def __init__(self, executor: Callable[[str], List[Dict[str, Any]]]) -> None:
        self._executor = executor
        self._connections: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def connect(self, dsn: str, user: str = "", password: str = "") -> str:
        """Open a connection and return a connection ID."""
        conn_id = hashlib.sha256(
            f"{dsn}:{user}:{time.time()}".encode()
        ).hexdigest()[:16]
        with self._lock:
            self._connections[conn_id] = {
                "dsn": dsn,
                "user": user,
                "connected_at": datetime.now().isoformat(),
                "cursor": None,
                "results": [],
            }
        logger.info("JDBC/ODBC connection opened: %s", conn_id)
        return conn_id

    def execute(self, conn_id: str, query: str) -> int:
        """Execute a query on an open connection.

        Returns:
            Number of result rows.
        """
        with self._lock:
            conn = self._connections.get(conn_id)
            if conn is None:
                raise ConnectionError(f"Connection '{conn_id}' not found")
        results = self._executor(query)
        with self._lock:
            conn["results"] = results
            conn["cursor"] = 0
        return len(results)

    def fetch(self, conn_id: str, n: int = -1) -> List[Dict[str, Any]]:
        """Fetch *n* rows (-1 = all)."""
        with self._lock:
            conn = self._connections.get(conn_id)
            if conn is None:
                raise ConnectionError(f"Connection '{conn_id}' not found")
            cursor = conn.get("cursor", 0) or 0
            results = conn["results"]
            if n < 0:
                batch = results[cursor:]
                conn["cursor"] = len(results)
            else:
                batch = results[cursor:cursor + n]
                conn["cursor"] = cursor + len(batch)
        return batch

    def close(self, conn_id: str) -> None:
        with self._lock:
            if conn_id in self._connections:
                del self._connections[conn_id]

    def list_connections(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"conn_id": cid, "dsn": c["dsn"], "user": c["user"],
                 "connected_at": c["connected_at"]}
                for cid, c in self._connections.items()
            ]


# ======================================================================
# SQLAlchemy Dialect
# ======================================================================

class SQLAlchemyDialect:
    """Minimal SQLAlchemy-compatible dialect for quantum DB.

    Provides the surface required by SQLAlchemy's ``create_engine``
    and ``MetaData.reflect`` workflows so that users can use the
    standard Python ORM with a quantum backend.
    """

    name = "qndb"
    supports_alter = False
    supports_unicode_statements = True
    default_schema_name = "public"

    def __init__(
        self,
        executor: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
        schema_provider: Optional[Callable[[], Dict[str, List[str]]]] = None,
    ) -> None:
        self._executor = executor or (lambda q: [])
        self._schema_provider = schema_provider or (lambda: {})

    def get_table_names(self, connection: Any = None, schema: Optional[str] = None) -> List[str]:
        tables = self._schema_provider()
        return list(tables.keys())

    def get_columns(
        self, table_name: str, connection: Any = None, schema: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        tables = self._schema_provider()
        cols = tables.get(table_name, [])
        return [{"name": c, "type": "VARCHAR", "nullable": True} for c in cols]

    def execute(self, query: str) -> List[Dict[str, Any]]:
        return self._executor(query)

    def has_table(self, table_name: str, schema: Optional[str] = None) -> bool:
        return table_name in self._schema_provider()


# ======================================================================
# Apache Arrow Flight Server
# ======================================================================

class ArrowFlightServer:
    """Apache Arrow Flight interface for high-speed data transfer.

    Provides ``do_get`` / ``do_put`` semantics for bulk data exchange
    between quantum DB and Arrow-compatible clients (Spark, Pandas,
    DuckDB, etc.).

    Args:
        executor: Query executor callable.
    """

    def __init__(self, executor: Callable[[str], List[Dict[str, Any]]]) -> None:
        self._executor = executor
        self._tickets: Dict[str, List[Dict[str, Any]]] = {}
        self._put_buffer: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def get_flight_info(self, query: str) -> Dict[str, Any]:
        """Prepare a flight plan and return a ticket.

        Returns:
            Dict with ``ticket``, ``schema``, ``num_rows``.
        """
        results = self._executor(query)
        ticket = hashlib.sha256(f"{query}:{time.time()}".encode()).hexdigest()[:16]
        with self._lock:
            self._tickets[ticket] = results
        schema = list(results[0].keys()) if results else []
        return {"ticket": ticket, "schema": schema, "num_rows": len(results)}

    def do_get(self, ticket: str) -> List[Dict[str, Any]]:
        """Retrieve data for a given ticket."""
        with self._lock:
            data = self._tickets.pop(ticket, None)
        if data is None:
            raise KeyError(f"Ticket '{ticket}' not found or already consumed")
        return data

    def do_put(self, table_name: str, rows: List[Dict[str, Any]]) -> int:
        """Ingest data via Arrow Flight put.

        Returns:
            Number of rows buffered.
        """
        with self._lock:
            buf = self._put_buffer.setdefault(table_name, [])
            buf.extend(rows)
        return len(rows)

    def flush_put_buffer(self, table_name: str) -> List[Dict[str, Any]]:
        """Drain and return the put buffer for *table_name*."""
        with self._lock:
            return self._put_buffer.pop(table_name, [])


# ======================================================================
# Kafka Connector
# ======================================================================

class KafkaConnector:
    """Apache Kafka connector for streaming ingestion.

    Provides an in-process message buffer that mimics Kafka's
    consumer/producer API so that qndb can ingest streaming data
    without requiring a live Kafka cluster.

    Args:
        bootstrap_servers: Comma-separated broker addresses (for docs).
        group_id: Consumer group ID.
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        group_id: str = "qndb-consumer",
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self._topics: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=100_000))
        self._offsets: Dict[str, int] = defaultdict(int)
        self._lock = threading.RLock()

    def produce(self, topic: str, key: Optional[str], value: Any) -> int:
        """Produce a message.

        Returns:
            Offset of the produced message.
        """
        with self._lock:
            q = self._topics[topic]
            offset = len(q)
            q.append({
                "key": key,
                "value": value,
                "offset": offset,
                "timestamp": time.time(),
            })
            return offset

    def consume(self, topic: str, max_messages: int = 100) -> List[Dict[str, Any]]:
        """Consume messages from the current offset.

        Returns:
            List of message dicts.
        """
        with self._lock:
            q = self._topics.get(topic)
            if q is None:
                return []
            start = self._offsets.get(topic, 0)
            msgs = list(q)[start:start + max_messages]
            self._offsets[topic] = start + len(msgs)
            return msgs

    def seek(self, topic: str, offset: int) -> None:
        with self._lock:
            self._offsets[topic] = offset

    def topic_stats(self, topic: str) -> Dict[str, Any]:
        with self._lock:
            q = self._topics.get(topic, deque())
            return {
                "topic": topic,
                "message_count": len(q),
                "current_offset": self._offsets.get(topic, 0),
                "lag": len(q) - self._offsets.get(topic, 0),
            }

    def list_topics(self) -> List[str]:
        with self._lock:
            return list(self._topics.keys())


# ======================================================================
# GraphQL Layer
# ======================================================================

class GraphQLLayer:
    """GraphQL API layer for quantum database queries.

    Resolves GraphQL-style queries and mutations against the
    underlying data store via registered resolvers.
    """

    def __init__(self) -> None:
        self._query_resolvers: Dict[str, Callable[..., Any]] = {}
        self._mutation_resolvers: Dict[str, Callable[..., Any]] = {}
        self._lock = threading.RLock()

    def register_query(self, name: str, resolver: Callable[..., Any]) -> None:
        with self._lock:
            self._query_resolvers[name] = resolver

    def register_mutation(self, name: str, resolver: Callable[..., Any]) -> None:
        with self._lock:
            self._mutation_resolvers[name] = resolver

    def execute(self, operation: str, name: str, **kwargs: Any) -> Any:
        """Execute a GraphQL operation.

        Args:
            operation: ``"query"`` or ``"mutation"``.
            name: Resolver name.
            **kwargs: Arguments forwarded to the resolver.

        Returns:
            Resolver result.
        """
        with self._lock:
            if operation == "query":
                resolver = self._query_resolvers.get(name)
            elif operation == "mutation":
                resolver = self._mutation_resolvers.get(name)
            else:
                raise ValueError(f"Unknown operation '{operation}'")

        if resolver is None:
            raise KeyError(f"No resolver for {operation}.{name}")
        return resolver(**kwargs)

    def introspect(self) -> Dict[str, List[str]]:
        with self._lock:
            return {
                "queries": list(self._query_resolvers.keys()),
                "mutations": list(self._mutation_resolvers.keys()),
            }


# ======================================================================
# Prometheus / Grafana Metrics Exporter
# ======================================================================

class MetricsExporter:
    """Prometheus-compatible metrics export.

    Maintains gauges, counters, and histograms that can be scraped
    by Prometheus or polled programmatically.  Exposes an
    ``exposition()`` method returning the standard text format.
    """

    class _MetricType(Enum):
        COUNTER = auto()
        GAUGE = auto()
        HISTOGRAM = auto()

    def __init__(self, prefix: str = "qndb") -> None:
        self._prefix = prefix
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.RLock()

    def inc_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._histograms[key].append(value)

    def exposition(self) -> str:
        """Return Prometheus text exposition format."""
        lines: List[str] = []
        with self._lock:
            for key, val in self._counters.items():
                lines.append(f"# TYPE {key} counter")
                lines.append(f"{key} {val}")
            for key, val in self._gauges.items():
                lines.append(f"# TYPE {key} gauge")
                lines.append(f"{key} {val}")
            for key, vals in self._histograms.items():
                lines.append(f"# TYPE {key} histogram")
                if vals:
                    lines.append(f"{key}_count {len(vals)}")
                    lines.append(f"{key}_sum {sum(vals)}")
        return "\n".join(lines) + "\n"

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: list(v) for k, v in self._histograms.items()},
            }

    def _key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        base = f"{self._prefix}_{name}"
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            return f"{base}{{{label_str}}}"
        return base


# ======================================================================
# OpenTelemetry Tracing
# ======================================================================

class TracingProvider:
    """OpenTelemetry-compatible distributed tracing.

    Generates spans for quantum circuit execution, query planning,
    and network calls.  Spans can be exported to Jaeger, Zipkin, or
    any OTLP-compatible backend.
    """

    def __init__(self, service_name: str = "qndb") -> None:
        self.service_name = service_name
        self._spans: Deque[Dict[str, Any]] = deque(maxlen=50_000)
        self._active: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def start_span(
        self,
        name: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a new span and return its span ID."""
        span_id = hashlib.sha256(
            f"{name}:{time.time()}:{id(self)}".encode()
        ).hexdigest()[:16]
        trace_id = trace_id or hashlib.sha256(
            f"trace:{time.time()}".encode()
        ).hexdigest()[:32]
        span = {
            "span_id": span_id,
            "trace_id": trace_id,
            "parent_span_id": parent_span_id,
            "name": name,
            "service": self.service_name,
            "start_time": time.time(),
            "end_time": None,
            "attributes": attributes or {},
            "status": "IN_PROGRESS",
        }
        with self._lock:
            self._active[span_id] = span
        return span_id

    def end_span(self, span_id: str, status: str = "OK", attributes: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            span = self._active.pop(span_id, None)
        if span is None:
            return
        span["end_time"] = time.time()
        span["duration_ms"] = (span["end_time"] - span["start_time"]) * 1000
        span["status"] = status
        if attributes:
            span["attributes"].update(attributes)
        with self._lock:
            self._spans.append(span)

    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return [s for s in self._spans if s["trace_id"] == trace_id]

    def recent_spans(self, n: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._spans)[-n:]

    def export_otlp(self) -> List[Dict[str, Any]]:
        """Export all finished spans in OTLP-compatible format."""
        with self._lock:
            return [
                {
                    "traceId": s["trace_id"],
                    "spanId": s["span_id"],
                    "parentSpanId": s.get("parent_span_id", ""),
                    "operationName": s["name"],
                    "serviceName": s["service"],
                    "startTimeUnixNano": int(s["start_time"] * 1e9),
                    "endTimeUnixNano": int((s["end_time"] or s["start_time"]) * 1e9),
                    "durationMs": s.get("duration_ms", 0),
                    "status": s["status"],
                    "attributes": s["attributes"],
                }
                for s in self._spans
            ]
