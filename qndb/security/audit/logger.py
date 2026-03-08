"""
Central Audit Logger
~~~~~~~~~~~~~~~~~~~~~
Receives events from all subsystems, dispatches to sinks, and maintains
an in-memory event-log for queries.
"""

import logging
import socket
import time
import uuid
from typing import Any, Dict, List, Optional

from .events import AuditEvent, AuditEventType
from .sinks import AuditEventSink

logger = logging.getLogger(__name__)


class AuditLogger:
    """Central audit logging facade.

    Usage::

        audit = AuditLogger()
        audit.add_sink(FileAuditEventSink("/var/log/qndb/audit.jsonl"))
        audit.add_sink(StreamAuditEventSink())

        audit.log_event("alice", "QUERY_EXECUTED", resource="table:orders",
                        details={"sql": "SELECT * FROM orders"})
    """

    def __init__(self) -> None:
        self.sinks: List[AuditEventSink] = []
        self.logs: Dict[str, Dict[str, Any]] = {}
        self._logger = logger

    def add_sink(self, sink: AuditEventSink) -> None:
        self.sinks.append(sink)

    def remove_sink(self, sink: AuditEventSink) -> None:
        self.sinks = [s for s in self.sinks if s is not sink]

    # ------------------------------------------------------------------
    # Core log method (backward-compatible signature)
    # ------------------------------------------------------------------

    def log_event(
        self,
        user_id: str,
        action: str,
        resource: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Log an audit event and dispatch to all sinks.

        Returns the generated event ID.
        """
        event_id = str(uuid.uuid4())

        # In-memory record (backward compat)
        event_record = {
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "status": status,
            "timestamp": time.time(),
            "details": details or {},
        }
        self.logs[event_id] = event_record

        # Build a proper AuditEvent for sinks
        event_type = self._resolve_event_type(action)
        audit_event = AuditEvent(
            event_type=event_type,
            user_id=user_id,
            resource_id=resource,
        )
        if details:
            for k, v in details.items():
                audit_event.add_detail(k, v)
        audit_event.set_success(status.lower() == "success")

        # Source info
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            audit_event.set_source(ip, hostname)
        except OSError:
            pass

        # Dispatch
        for sink in self.sinks:
            try:
                sink.write_event(audit_event)
            except Exception as exc:
                self._logger.error("Sink write failed: %s", exc)

        return event_id

    def log_query(
        self,
        user_id: str,
        query: str,
        *,
        resource: Optional[str] = None,
        execution_plan: Optional[str] = None,
        duration_ms: Optional[float] = None,
        status: str = "success",
    ) -> str:
        """Convenience wrapper: log a query with its execution plan."""
        details: Dict[str, Any] = {"query": query}
        if execution_plan:
            details["execution_plan"] = execution_plan
        if duration_ms is not None:
            details["duration_ms"] = duration_ms
        return self.log_event(
            user_id, "QUERY_EXECUTED", resource=resource,
            status=status, details=details,
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_user_events(self, user_id: str) -> List[Dict[str, Any]]:
        return [e for e in self.logs.values() if e["user_id"] == user_id]

    def get_resource_events(self, resource: str) -> List[Dict[str, Any]]:
        return [e for e in self.logs.values() if e.get("resource") == resource]

    def get_events_by_timerange(
        self, start: float, end: float
    ) -> List[Dict[str, Any]]:
        return [
            e for e in self.logs.values()
            if start <= e["timestamp"] <= end
        ]

    def search_events(self, **filters: Any) -> List[Dict[str, Any]]:
        result = []
        for ev in self.logs.values():
            if all(ev.get(k) == v for k, v in filters.items()):
                result.append(ev)
        return result

    def clear_logs(self) -> None:
        self.logs.clear()

    def flush_all_sinks(self) -> None:
        for sink in self.sinks:
            try:
                sink.flush()
            except Exception as exc:
                self._logger.error("Sink flush failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_event_type(action: str) -> AuditEventType:
        try:
            return AuditEventType.from_string(action)
        except KeyError:
            return AuditEventType.DATA_ACCESS
