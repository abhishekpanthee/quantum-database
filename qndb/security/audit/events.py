"""
Audit Event Types & Models
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Canonical event taxonomy and the ``AuditEvent`` data class used across
all sinks and compliance reporters.
"""

import json
import os
import socket
import threading
import time
import uuid
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, Optional


class AuditEventType(Enum):
    """Canonical audit event types."""
    LOGIN = auto()
    LOGOUT = auto()
    AUTHENTICATION_FAILURE = auto()
    AUTHORIZATION_FAILURE = auto()
    USER_CREATED = auto()
    USER_MODIFIED = auto()
    USER_DELETED = auto()
    ROLE_CREATED = auto()
    ROLE_MODIFIED = auto()
    ROLE_DELETED = auto()
    PERMISSION_GRANTED = auto()
    PERMISSION_REVOKED = auto()
    RESOURCE_CREATED = auto()
    RESOURCE_MODIFIED = auto()
    RESOURCE_DELETED = auto()
    QUERY_EXECUTED = auto()
    DATABASE_CREATED = auto()
    DATABASE_MODIFIED = auto()
    DATABASE_DELETED = auto()
    TABLE_CREATED = auto()
    TABLE_MODIFIED = auto()
    TABLE_DELETED = auto()
    DATA_ACCESS = auto()
    DATA_MODIFICATION = auto()
    CONFIGURATION_CHANGE = auto()
    ENCRYPTION_KEY_ROTATION = auto()
    BACKUP_CREATED = auto()
    BACKUP_RESTORED = auto()
    SYSTEM_ERROR = auto()
    SYSTEM_STARTUP = auto()
    SYSTEM_SHUTDOWN = auto()
    QUANTUM_CIRCUIT_EXECUTION = auto()
    DISTRIBUTED_CONSENSUS = auto()
    QUANTUM_STATE_ACCESS = auto()
    COMPLIANCE_CHECK = auto()

    @classmethod
    def from_string(cls, event_str: str) -> "AuditEventType":
        return cls[event_str.upper()]


class AuditEvent:
    """Immutable audit event record."""

    def __init__(
        self,
        event_type: AuditEventType,
        user_id: str,
        resource_id: Optional[str] = None,
    ) -> None:
        self.event_id: str = str(uuid.uuid4())
        self.event_type = event_type
        self.timestamp: float = time.time()
        self.user_id = user_id
        self.resource_id = resource_id
        self.details: Dict[str, Any] = {}
        self.source_ip: Optional[str] = None
        self.source_hostname: Optional[str] = None
        self.success: bool = True
        self.process_id: int = os.getpid()
        self.thread_id: int = threading.get_ident()
        self.severity: str = "INFO"  # INFO, WARNING, ERROR, CRITICAL
        self.query_plan: Optional[str] = None

    def add_detail(self, key: str, value: Any) -> "AuditEvent":
        self.details[key] = value
        return self

    def set_source(
        self, ip: str, hostname: Optional[str] = None
    ) -> "AuditEvent":
        self.source_ip = ip
        self.source_hostname = hostname
        return self

    def set_success(self, success: bool) -> "AuditEvent":
        self.success = success
        if not success:
            self.severity = "WARNING"
        return self

    def set_severity(self, severity: str) -> "AuditEvent":
        self.severity = severity
        return self

    def set_query_plan(self, plan: str) -> "AuditEvent":
        self.query_plan = plan
        return self

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.name,
            "timestamp": self.timestamp,
            "datetime": datetime.fromtimestamp(self.timestamp).isoformat(),
            "user_id": self.user_id,
            "resource_id": self.resource_id,
            "details": self.details,
            "source_ip": self.source_ip,
            "source_hostname": self.source_hostname,
            "success": self.success,
            "process_id": self.process_id,
            "thread_id": self.thread_id,
            "severity": self.severity,
            "query_plan": self.query_plan,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def to_cef(self) -> str:
        """Render in ArcSight Common Event Format."""
        sev_map = {"INFO": 1, "WARNING": 5, "ERROR": 8, "CRITICAL": 10}
        sev = sev_map.get(self.severity, 1)
        ext = " ".join(
            f"{k}={v}" for k, v in self.details.items() if v is not None
        )
        return (
            f"CEF:0|QNDB|QuantumDB|1.0|{self.event_type.name}|"
            f"{self.event_type.name}|{sev}|"
            f"src={self.source_ip or '-'} "
            f"suser={self.user_id} "
            f"outcome={'success' if self.success else 'failure'} "
            f"{ext}"
        )

    def to_ocsf(self) -> Dict[str, Any]:
        """Render in Open Cybersecurity Schema Framework (OCSF) v1."""
        return {
            "class_uid": 3001,  # API Activity
            "activity_id": 1,
            "severity_id": {"INFO": 1, "WARNING": 3,
                            "ERROR": 4, "CRITICAL": 5}.get(self.severity, 1),
            "time": int(self.timestamp * 1000),
            "message": self.event_type.name,
            "actor": {"user": {"uid": self.user_id}},
            "src_endpoint": {"ip": self.source_ip or ""},
            "status": "Success" if self.success else "Failure",
            "unmapped": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEvent":
        event = cls(
            AuditEventType.from_string(data["event_type"]),
            data["user_id"],
            data.get("resource_id"),
        )
        event.event_id = data["event_id"]
        event.timestamp = data["timestamp"]
        event.details = data.get("details", {})
        event.source_ip = data.get("source_ip")
        event.source_hostname = data.get("source_hostname")
        event.success = data.get("success", True)
        event.process_id = data.get("process_id", 0)
        event.thread_id = data.get("thread_id", 0)
        event.severity = data.get("severity", "INFO")
        event.query_plan = data.get("query_plan")
        return event
