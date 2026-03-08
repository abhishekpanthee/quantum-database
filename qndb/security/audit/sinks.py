"""
Audit Log Sinks
~~~~~~~~~~~~~~~~
Pluggable backends for persisting audit events.

* ``FileAuditEventSink`` — rotating JSON-lines file.
* ``StreamAuditEventSink`` — in-memory queue for real-time consumers.
"""

import json
import logging
import os
import queue
import threading
from typing import Any, Callable, Dict, List, Optional

from .events import AuditEvent

logger = logging.getLogger(__name__)


class AuditEventSink:
    """Abstract base for audit event sinks."""

    def write_event(self, event: AuditEvent) -> bool:
        raise NotImplementedError

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class FileAuditEventSink(AuditEventSink):
    """Rotating JSON-lines file sink.

    Files are rotated when ``rotate_size_mb`` is exceeded.  Up to
    ``max_files`` rotated copies are kept.
    """

    def __init__(
        self,
        filename: str,
        rotate_size_mb: int = 10,
        max_files: int = 5,
    ) -> None:
        self.filename = filename
        self.rotate_size_bytes = rotate_size_mb * 1024 * 1024
        self.max_files = max_files
        self._lock = threading.Lock()
        self.file = None
        self.current_size = 0
        self._open_file()

    def _open_file(self) -> None:
        if os.path.exists(self.filename):
            self.current_size = os.path.getsize(self.filename)
        else:
            self.current_size = 0
        self.file = open(self.filename, "a", encoding="utf-8")

    def _rotate_file(self) -> None:
        if self.file:
            self.file.close()

        for i in range(self.max_files - 1, 0, -1):
            old = f"{self.filename}.{i}"
            new = f"{self.filename}.{i + 1}"
            if os.path.exists(old):
                if i == self.max_files - 1:
                    os.remove(old)
                else:
                    os.rename(old, new)

        if os.path.exists(self.filename):
            os.rename(self.filename, f"{self.filename}.1")

        self._open_file()

    def write_event(self, event: AuditEvent) -> bool:
        with self._lock:
            if not self.file:
                try:
                    self._open_file()
                except OSError:
                    return False
            try:
                line = event.to_json() + "\n"
                self.file.write(line)
                self.file.flush()
                self.current_size += len(line)
                if self.current_size >= self.rotate_size_bytes:
                    self._rotate_file()
                return True
            except OSError:
                return False

    def flush(self) -> None:
        with self._lock:
            if self.file:
                self.file.flush()

    def close(self) -> None:
        with self._lock:
            if self.file:
                self.file.close()
                self.file = None


class StreamAuditEventSink(AuditEventSink):
    """In-memory queue-based real-time audit stream.

    Consumers call ``subscribe()`` to receive events pushed as
    dictionaries.  Non-blocking; events are dropped if the subscriber
    queue is full.
    """

    def __init__(self, max_queue_size: int = 10000) -> None:
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()
        self._max_queue = max_queue_size
        self._total_events: int = 0
        self._dropped_events: int = 0

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=self._max_queue)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subscribers = [
                s for s in self._subscribers if s is not q
            ]

    def write_event(self, event: AuditEvent) -> bool:
        data = event.to_dict()
        with self._lock:
            self._total_events += 1
            for q in self._subscribers:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    self._dropped_events += 1
        return True

    @property
    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "total_events": self._total_events,
                "dropped_events": self._dropped_events,
                "subscribers": len(self._subscribers),
            }

    def close(self) -> None:
        with self._lock:
            self._subscribers.clear()
