"""
Compliance Helpers — SOC 2 & GDPR
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ``SOC2Mapper`` — maps audit events to SOC 2 Type II Common Criteria (CC)
  controls.
* ``GDPRManager`` — handles Data Subject Access Requests (DSAR) and
  right-to-erasure operations.
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional, Set

from .events import AuditEvent, AuditEventType


# ---------------------------------------------------------------------------
# SOC 2 Type II mapping
# ---------------------------------------------------------------------------

# CC controls → relevant audit event types
_SOC2_CONTROL_MAP: Dict[str, List[AuditEventType]] = {
    "CC6.1": [
        AuditEventType.LOGIN,
        AuditEventType.LOGOUT,
        AuditEventType.AUTHENTICATION_FAILURE,
    ],
    "CC6.2": [
        AuditEventType.USER_CREATED,
        AuditEventType.USER_MODIFIED,
        AuditEventType.USER_DELETED,
        AuditEventType.ROLE_CREATED,
        AuditEventType.ROLE_MODIFIED,
        AuditEventType.ROLE_DELETED,
    ],
    "CC6.3": [
        AuditEventType.PERMISSION_GRANTED,
        AuditEventType.PERMISSION_REVOKED,
        AuditEventType.AUTHORIZATION_FAILURE,
    ],
    "CC6.6": [
        AuditEventType.DATA_ACCESS,
        AuditEventType.DATA_MODIFICATION,
        AuditEventType.QUERY_EXECUTED,
    ],
    "CC6.7": [
        AuditEventType.ENCRYPTION_KEY_ROTATION,
        AuditEventType.CONFIGURATION_CHANGE,
    ],
    "CC6.8": [
        AuditEventType.SYSTEM_ERROR,
        AuditEventType.SYSTEM_STARTUP,
        AuditEventType.SYSTEM_SHUTDOWN,
    ],
    "CC7.1": [
        AuditEventType.CONFIGURATION_CHANGE,
    ],
    "CC7.2": [
        AuditEventType.AUTHENTICATION_FAILURE,
        AuditEventType.AUTHORIZATION_FAILURE,
        AuditEventType.SYSTEM_ERROR,
    ],
}


class SOC2Mapper:
    """Maps audit events to SOC 2 Type II controls."""

    def __init__(self) -> None:
        self._map = dict(_SOC2_CONTROL_MAP)

    def get_control(self, event_type: AuditEventType) -> List[str]:
        """Return all CC controls that require this event type."""
        return [
            ctrl
            for ctrl, types in self._map.items()
            if event_type in types
        ]

    def coverage_report(
        self, events: List[AuditEvent]
    ) -> Dict[str, Dict[str, Any]]:
        """Produce a coverage report for a set of audit events."""
        seen: Dict[str, Set[str]] = {ctrl: set() for ctrl in self._map}
        for ev in events:
            for ctrl in self.get_control(ev.event_type):
                seen[ctrl].add(ev.event_type.name)

        report: Dict[str, Dict[str, Any]] = {}
        for ctrl, types in self._map.items():
            expected = {t.name for t in types}
            covered = seen[ctrl]
            report[ctrl] = {
                "expected": sorted(expected),
                "covered": sorted(covered),
                "missing": sorted(expected - covered),
                "coverage_pct": (
                    len(covered) / len(expected) * 100 if expected else 100
                ),
            }
        return report


# ---------------------------------------------------------------------------
# GDPR helpers
# ---------------------------------------------------------------------------

class GDPRDataSubjectRequest:
    """Represents a GDPR data-subject request (DSAR)."""

    def __init__(
        self,
        request_id: str,
        subject_id: str,
        request_type: str,  # "access" or "erasure"
        *,
        requested_at: Optional[float] = None,
    ) -> None:
        self.request_id = request_id
        self.subject_id = subject_id
        self.request_type = request_type
        self.requested_at = requested_at or time.time()
        self.completed_at: Optional[float] = None
        self.status: str = "pending"  # pending, processing, completed, denied
        self.result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "subject_id": self.subject_id,
            "request_type": self.request_type,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "status": self.status,
        }


class GDPRManager:
    """Handles GDPR data-subject access and erasure requests.

    Data collection and deletion are delegated to user-provided callbacks.
    """

    def __init__(self) -> None:
        self._requests: Dict[str, GDPRDataSubjectRequest] = {}
        self._data_collectors: List[
            Callable[[str], Dict[str, Any]]
        ] = []
        self._data_erasers: List[Callable[[str], bool]] = []

    def register_data_collector(
        self, collector: Callable[[str], Dict[str, Any]]
    ) -> None:
        """Register a callback that returns data for a subject_id."""
        self._data_collectors.append(collector)

    def register_data_eraser(
        self, eraser: Callable[[str], bool]
    ) -> None:
        """Register a callback that erases data for a subject_id."""
        self._data_erasers.append(eraser)

    def submit_access_request(
        self, request_id: str, subject_id: str
    ) -> GDPRDataSubjectRequest:
        """Submit a right-to-access request."""
        req = GDPRDataSubjectRequest(
            request_id, subject_id, "access"
        )
        self._requests[request_id] = req
        return req

    def submit_erasure_request(
        self, request_id: str, subject_id: str
    ) -> GDPRDataSubjectRequest:
        """Submit a right-to-erasure (right to be forgotten) request."""
        req = GDPRDataSubjectRequest(
            request_id, subject_id, "erasure"
        )
        self._requests[request_id] = req
        return req

    def process_request(
        self, request_id: str
    ) -> GDPRDataSubjectRequest:
        """Process a pending request.

        For *access* requests, calls all registered collectors and
        aggregates the results.  For *erasure* requests, calls all
        registered erasers.
        """
        req = self._requests.get(request_id)
        if req is None:
            raise KeyError(f"Request {request_id} not found")

        req.status = "processing"

        if req.request_type == "access":
            collected: Dict[str, Any] = {}
            for collector in self._data_collectors:
                try:
                    data = collector(req.subject_id)
                    collected.update(data)
                except Exception:
                    pass
            req.result = collected
            req.status = "completed"
            req.completed_at = time.time()

        elif req.request_type == "erasure":
            all_ok = True
            for eraser in self._data_erasers:
                try:
                    if not eraser(req.subject_id):
                        all_ok = False
                except Exception:
                    all_ok = False
            req.status = "completed" if all_ok else "partial"
            req.completed_at = time.time()

        return req

    def get_request(
        self, request_id: str
    ) -> Optional[GDPRDataSubjectRequest]:
        return self._requests.get(request_id)

    def list_requests(
        self, *, status: Optional[str] = None
    ) -> List[GDPRDataSubjectRequest]:
        reqs = list(self._requests.values())
        if status:
            reqs = [r for r in reqs if r.status == status]
        return reqs
