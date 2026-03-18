"""Write-Ahead Log for crash recovery."""

import json
import time
import logging
from typing import Dict, List, Any, Optional, Set
from threading import Lock

logger = logging.getLogger(__name__)


class WALEntry:
    """A single WAL record."""

    __slots__ = ('lsn', 'txn_id', 'op_type', 'table', 'pk', 'before', 'after', 'ts')

    def __init__(self, lsn: int, txn_id: str, op_type: str,
                 table: str, pk: Any, before: Optional[Dict], after: Optional[Dict],
                 ts: float):
        self.lsn = lsn
        self.txn_id = txn_id
        self.op_type = op_type  # INSERT | UPDATE | DELETE | COMMIT | ROLLBACK | SAVEPOINT
        self.table = table
        self.pk = pk
        self.before = before
        self.after = after
        self.ts = ts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lsn": self.lsn,
            "txn_id": self.txn_id,
            "op_type": self.op_type,
            "table": self.table,
            "pk": self.pk,
            "before": self.before,
            "after": self.after,
            "ts": self.ts,
        }


class WriteAheadLog:
    """Append-only write-ahead log for crash recovery."""

    def __init__(self, path: Optional[str] = None):
        self._entries: List[WALEntry] = []
        self._lock = Lock()
        self._next_lsn = 1
        self._path = path

    @property
    def entries(self) -> List[WALEntry]:
        return list(self._entries)

    def append(self, txn_id: str, op_type: str, table: str = "",
               pk: Any = None, before: Optional[Dict] = None,
               after: Optional[Dict] = None) -> int:
        with self._lock:
            lsn = self._next_lsn
            self._next_lsn += 1
            entry = WALEntry(lsn, txn_id, op_type, table, pk, before, after, time.time())
            self._entries.append(entry)
            if self._path:
                self._flush(entry)
            return lsn

    def _flush(self, entry: WALEntry) -> None:
        try:
            with open(self._path, 'a') as f:
                f.write(json.dumps(entry.to_dict()) + '\n')
        except OSError as e:
            logger.error("WAL flush failed: %s", e)

    def replay(self) -> List[WALEntry]:
        """Return uncommitted entries suitable for redo/undo recovery."""
        committed: Set[str] = set()
        aborted: Set[str] = set()
        for e in self._entries:
            if e.op_type == 'COMMIT':
                committed.add(e.txn_id)
            elif e.op_type == 'ROLLBACK':
                aborted.add(e.txn_id)
        # Entries for transactions that committed but whose effects may
        # not have been applied (simulate crash-recovery redo)
        return [e for e in self._entries
                if e.txn_id in committed and e.op_type not in ('COMMIT', 'ROLLBACK', 'SAVEPOINT')]

    def truncate(self, up_to_lsn: int) -> None:
        with self._lock:
            self._entries = [e for e in self._entries if e.lsn > up_to_lsn]
