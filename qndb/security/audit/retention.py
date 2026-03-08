"""
Audit Log Retention Policies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Manages tiered retention, automatic archival, and purging of audit logs.
"""

import os
import shutil
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .._standards import RETENTION_HOT, RETENTION_WARM, RETENTION_COLD


class RetentionPolicy:
    """Defines a named retention tier."""

    def __init__(
        self,
        name: str,
        duration_seconds: int,
        *,
        archive_fn: Optional[Callable[[str, str], bool]] = None,
    ) -> None:
        self.name = name
        self.duration_seconds = duration_seconds
        self.archive_fn = archive_fn  # (src_path, dst_path) → ok

    def is_expired(self, event_timestamp: float) -> bool:
        return (time.time() - event_timestamp) > self.duration_seconds


class RetentionManager:
    """Enforces tiered retention across audit log files.

    Default tiers::

        hot  → 30 days  (live, queryable)
        warm → 1 year   (compressed archive)
        cold → 7 years  (external / object store)
    """

    def __init__(self) -> None:
        self.policies: List[RetentionPolicy] = []
        self._lock = threading.Lock()
        self._init_defaults()

    def _init_defaults(self) -> None:
        self.add_policy(RetentionPolicy("hot", RETENTION_HOT))
        self.add_policy(RetentionPolicy("warm", RETENTION_WARM))
        self.add_policy(RetentionPolicy("cold", RETENTION_COLD))

    def add_policy(self, policy: RetentionPolicy) -> None:
        with self._lock:
            self.policies.append(policy)
            self.policies.sort(key=lambda p: p.duration_seconds)

    def remove_policy(self, name: str) -> None:
        with self._lock:
            self.policies = [
                p for p in self.policies if p.name != name
            ]

    def classify_event(self, event_timestamp: float) -> str:
        """Return the tier name for an event based on its age."""
        for policy in self.policies:
            if not policy.is_expired(event_timestamp):
                return policy.name
        return "expired"

    def apply_retention(
        self,
        log_dir: str,
        archive_dir: Optional[str] = None,
    ) -> Dict[str, int]:
        """Scan *log_dir* for audit files and enforce retention.

        Returns counts of files processed per action.
        """
        if not os.path.isdir(log_dir):
            return {"skipped": 0, "archived": 0, "deleted": 0}

        stats = {"skipped": 0, "archived": 0, "deleted": 0}
        now = time.time()

        for fname in sorted(os.listdir(log_dir)):
            fpath = os.path.join(log_dir, fname)
            if not os.path.isfile(fpath):
                continue

            mtime = os.path.getmtime(fpath)
            tier = self.classify_event(mtime)

            if tier == "hot":
                stats["skipped"] += 1
            elif tier in ("warm", "cold"):
                if archive_dir:
                    dest = os.path.join(archive_dir, tier, fname)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.move(fpath, dest)
                    stats["archived"] += 1
                else:
                    stats["skipped"] += 1
            elif tier == "expired":
                os.remove(fpath)
                stats["deleted"] += 1

        return stats

    def get_policies(self) -> List[Dict[str, Any]]:
        return [
            {"name": p.name, "duration_seconds": p.duration_seconds}
            for p in self.policies
        ]
