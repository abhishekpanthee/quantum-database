"""
Tamper-Evident Hash-Chained Audit Log
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Each entry stores ``prev_hash`` — the SHA-256 of the previous entry.
Any modification to a historical entry invalidates all subsequent hashes,
making tampering detectable.
"""

import hashlib
import json
import threading
import time
from typing import Any, Dict, List, Optional

from .events import AuditEvent
from .._standards import TamperDetectedException


class HashChainEntry:
    """A single entry in the hash chain."""

    __slots__ = ("sequence", "event", "prev_hash", "entry_hash")

    def __init__(
        self,
        sequence: int,
        event: AuditEvent,
        prev_hash: str,
    ) -> None:
        self.sequence = sequence
        self.event = event
        self.prev_hash = prev_hash
        self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = json.dumps(
            {
                "seq": self.sequence,
                "event": self.event.to_dict(),
                "prev": self.prev_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event": self.event.to_dict(),
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


class HashChainAuditLog:
    """Append-only, tamper-evident audit log backed by a SHA-256 chain."""

    GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        self._chain: List[HashChainEntry] = []
        self._lock = threading.Lock()

    @property
    def length(self) -> int:
        return len(self._chain)

    @property
    def head_hash(self) -> str:
        if not self._chain:
            return self.GENESIS_HASH
        return self._chain[-1].entry_hash

    def append(self, event: AuditEvent) -> HashChainEntry:
        """Append an event to the chain.  Returns the new entry."""
        with self._lock:
            prev = self.head_hash
            entry = HashChainEntry(len(self._chain), event, prev)
            self._chain.append(entry)
            return entry

    def verify(self) -> bool:
        """Verify the entire chain.  Returns ``True`` if intact.

        Raises ``TamperDetectedException`` on the first corrupted entry.
        """
        with self._lock:
            prev = self.GENESIS_HASH
            for entry in self._chain:
                if entry.prev_hash != prev:
                    raise TamperDetectedException(
                        f"Chain broken at seq {entry.sequence}: "
                        f"expected prev={prev!r}, got {entry.prev_hash!r}"
                    )
                recomputed = entry._compute_hash()
                if recomputed != entry.entry_hash:
                    raise TamperDetectedException(
                        f"Hash mismatch at seq {entry.sequence}: "
                        f"stored={entry.entry_hash!r}, computed={recomputed!r}"
                    )
                prev = entry.entry_hash
            return True

    def get_entry(self, sequence: int) -> Optional[HashChainEntry]:
        with self._lock:
            if 0 <= sequence < len(self._chain):
                return self._chain[sequence]
            return None

    def get_entries(
        self, start: int = 0, end: Optional[int] = None
    ) -> List[HashChainEntry]:
        with self._lock:
            return list(self._chain[start:end])

    def export_chain(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._chain]

    def import_chain(self, data: List[Dict[str, Any]]) -> None:
        """Import a chain from serialized data and verify."""
        with self._lock:
            self._chain.clear()
            for d in data:
                event = AuditEvent.from_dict(d["event"])
                entry = HashChainEntry(
                    d["sequence"], event, d["prev_hash"]
                )
                if entry.entry_hash != d["entry_hash"]:
                    raise TamperDetectedException(
                        f"Import failed: hash mismatch at seq {d['sequence']}"
                    )
                self._chain.append(entry)
            self.verify()
