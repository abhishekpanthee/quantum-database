"""Multi-Version Concurrency Control store."""

from typing import Dict, List, Any, Optional
from threading import Lock


class VersionedRecord:
    """A single record version created by a specific transaction."""

    __slots__ = ('data', 'txn_id', 'created_ts', 'expired_ts', 'deleted')

    def __init__(self, data: Dict[str, Any], txn_id: str, created_ts: float):
        self.data = data
        self.txn_id = txn_id
        self.created_ts = created_ts
        self.expired_ts: Optional[float] = None
        self.deleted = False


class MVCCStore:
    """Multi-Version Concurrency Control store.

    Each table maps a primary key to a list of ``VersionedRecord``s ordered
    by ``created_ts``.  A snapshot at time *T* sees the latest version whose
    ``created_ts <= T`` and ``expired_ts is None or expired_ts > T``.
    """

    def __init__(self):
        # table -> pk -> [VersionedRecord, ...]
        self._versions: Dict[str, Dict[Any, List[VersionedRecord]]] = {}
        self._lock = Lock()

    def write(self, table: str, pk: Any, data: Dict[str, Any],
              txn_id: str, ts: float) -> None:
        with self._lock:
            chain = self._versions.setdefault(table, {}).setdefault(pk, [])
            # Expire previous head
            if chain:
                chain[-1].expired_ts = ts
            chain.append(VersionedRecord(data, txn_id, ts))

    def delete(self, table: str, pk: Any, txn_id: str, ts: float) -> None:
        with self._lock:
            chain = self._versions.setdefault(table, {}).setdefault(pk, [])
            if chain:
                chain[-1].expired_ts = ts
            tombstone = VersionedRecord({}, txn_id, ts)
            tombstone.deleted = True
            chain.append(tombstone)

    def read_snapshot(self, table: str, snapshot_ts: float) -> List[Dict[str, Any]]:
        """Return all visible rows for *table* at *snapshot_ts*."""
        with self._lock:
            rows: List[Dict[str, Any]] = []
            for pk, chain in self._versions.get(table, {}).items():
                visible = None
                for ver in chain:
                    if ver.created_ts <= snapshot_ts:
                        if ver.expired_ts is None or ver.expired_ts > snapshot_ts:
                            visible = ver
                    elif ver.created_ts > snapshot_ts:
                        break
                if visible and not visible.deleted:
                    rows.append(visible.data)
            return rows

    def gc(self, oldest_active_ts: float) -> int:
        """Garbage-collect versions no longer visible to any transaction."""
        removed = 0
        with self._lock:
            for table in self._versions:
                for pk in list(self._versions[table]):
                    chain = self._versions[table][pk]
                    # Keep at least the latest version
                    new_chain = [v for v in chain
                                 if v.expired_ts is None or v.expired_ts >= oldest_active_ts]
                    removed += len(chain) - len(new_chain)
                    self._versions[table][pk] = new_chain if new_chain else chain[-1:]
        return removed
