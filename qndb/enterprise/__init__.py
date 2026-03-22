"""
qndb.enterprise — Enterprise Features
========================================

Production-grade modules for enterprise database workloads:

* **storage** — columnar formats, quantum-native types, tiered storage
* **query** — window functions, CTEs, UDQFs, stored procedures, views
* **admin** — monitoring, slow-query log, dashboards, alerts
* **integration** — JDBC/ODBC adapters, SQLAlchemy dialect, Arrow/Kafka, GraphQL, metrics export
"""

from qndb.enterprise.storage import (  # noqa: F401
    ColumnarStorage,
    QuantumDataType,
    QuantumColumnCompressor,
    MaterializedViewManager,
    PartitionManager,
    TieredStorageManager,
)
from qndb.enterprise.query import (  # noqa: F401
    WindowFunction,
    CTEResolver,
    UDQFRegistry,
    StoredProcedure,
    ViewManager,
    QuantumFullTextSearch,
    QuantumGeospatialIndex,
)
from qndb.enterprise.admin import (  # noqa: F401
    AdminConsole,
    QueryPerformanceMonitor,
    SlowQueryLog,
    StorageAnalytics,
    QuantumResourceDashboard,
    AlertManager,
)
from qndb.enterprise.integration import (  # noqa: F401
    JDBCODBCAdapter,
    SQLAlchemyDialect,
    ArrowFlightServer,
    KafkaConnector,
    GraphQLLayer,
    MetricsExporter,
    TracingProvider,
)

__all__ = [
    # 8.1 Advanced Storage
    "ColumnarStorage", "QuantumDataType", "QuantumColumnCompressor",
    "MaterializedViewManager", "PartitionManager", "TieredStorageManager",
    # 8.2 Advanced Query Features
    "WindowFunction", "CTEResolver", "UDQFRegistry", "StoredProcedure",
    "ViewManager", "QuantumFullTextSearch", "QuantumGeospatialIndex",
    # 8.3 Administration
    "AdminConsole", "QueryPerformanceMonitor", "SlowQueryLog",
    "StorageAnalytics", "QuantumResourceDashboard", "AlertManager",
    # 8.4 Integration & Ecosystem
    "JDBCODBCAdapter", "SQLAlchemyDialect", "ArrowFlightServer",
    "KafkaConnector", "GraphQLLayer", "MetricsExporter", "TracingProvider",
]
