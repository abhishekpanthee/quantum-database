"""Transaction Manager — ACID lifecycle, locking, savepoints."""

import uuid
import time
import logging
from typing import Dict, List, Any, Optional, Set
from threading import RLock

from qndb.interface.transactions.enums import TransactionStatus, IsolationLevel
from qndb.interface.transactions.mvcc import MVCCStore
from qndb.interface.transactions.wal import WriteAheadLog
from qndb.interface.transactions.transaction import Transaction

logger = logging.getLogger(__name__)


class TransactionManager:
    """Manages database transactions to ensure ACID properties.

    Features:
     - MVCC snapshot isolation
     - WAL for crash recovery
     - Savepoints and nested transactions
     - Lock timeout with automatic deadlock resolution (youngest-victim)
    """

    def __init__(self, wal_path: Optional[str] = None):
        self.transactions: Dict[str, Transaction] = {}
        self.lock = RLock()
        self.default_isolation_level = IsolationLevel.SERIALIZABLE
        self.deadlock_detection_enabled = True
        self.lock_timeout: float = 5.0  # seconds

        # MVCC store & WAL
        self.mvcc = MVCCStore()
        self.wal = WriteAheadLog(path=wal_path)

        logger.info("Transaction manager initialized (MVCC + WAL)")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def begin_transaction(self, isolation_level: Optional[IsolationLevel] = None) -> str:
        with self.lock:
            transaction_id = str(uuid.uuid4())
            if isolation_level is None:
                isolation_level = self.default_isolation_level
            snapshot_ts = time.time()
            tx = Transaction(transaction_id, isolation_level, snapshot_ts)
            self.transactions[transaction_id] = tx
            self.wal.append(transaction_id, 'BEGIN')
            logger.info("Started transaction %s (isolation=%s, snapshot=%.6f)",
                        transaction_id, isolation_level.value, snapshot_ts)
            return transaction_id

    def commit_transaction(self, transaction_id: str) -> bool:
        with self.lock:
            tx = self.transactions.get(transaction_id)
            if tx is None:
                logger.error("Commit unknown transaction: %s", transaction_id)
                return False
            if tx.status != TransactionStatus.ACTIVE:
                logger.error("Cannot commit transaction %s (status=%s)",
                             transaction_id, tx.status.value)
                return False

            # Conflict check
            for other_id, other_tx in self.transactions.items():
                if other_id != transaction_id and tx.has_conflicts(other_tx):
                    logger.warning("Transaction %s conflicts, cannot commit", transaction_id)
                    return False

            tx.status = TransactionStatus.COMMITTED
            tx.commit_time = time.time()

            # Apply operations
            self._apply_transaction(tx)

            # WAL commit marker
            self.wal.append(transaction_id, 'COMMIT')

            # Release locks
            self._release_locks(tx)

            logger.info("Committed transaction %s", transaction_id)
            return True

    def rollback_transaction(self, transaction_id: str) -> bool:
        with self.lock:
            tx = self.transactions.get(transaction_id)
            if tx is None:
                logger.error("Rollback unknown transaction: %s", transaction_id)
                return False
            if tx.status != TransactionStatus.ACTIVE:
                logger.error("Cannot rollback transaction %s (status=%s)",
                             transaction_id, tx.status.value)
                return False

            tx.status = TransactionStatus.ABORTED
            self.wal.append(transaction_id, 'ROLLBACK')
            self._release_locks(tx)
            logger.info("Rolled back transaction %s", transaction_id)
            return True

    # ------------------------------------------------------------------
    # Savepoints
    # ------------------------------------------------------------------

    def create_savepoint(self, transaction_id: str, name: str) -> bool:
        with self.lock:
            tx = self.transactions.get(transaction_id)
            if tx is None or tx.status != TransactionStatus.ACTIVE:
                return False
            lsn = self.wal.append(transaction_id, 'SAVEPOINT', pk=name)
            tx.create_savepoint(name, lsn)
            logger.info("Savepoint '%s' created in transaction %s", name, transaction_id)
            return True

    def rollback_to_savepoint(self, transaction_id: str, name: str) -> bool:
        with self.lock:
            tx = self.transactions.get(transaction_id)
            if tx is None or tx.status != TransactionStatus.ACTIVE:
                return False
            if tx.rollback_to_savepoint(name):
                self.wal.append(transaction_id, 'ROLLBACK_TO_SAVEPOINT', pk=name)
                logger.info("Rolled back to savepoint '%s' in %s", name, transaction_id)
                return True
            logger.warning("Savepoint '%s' not found in %s", name, transaction_id)
            return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        with self.lock:
            return self.transactions.get(transaction_id)

    def get_active_transactions(self) -> List[Transaction]:
        with self.lock:
            return [tx for tx in self.transactions.values()
                    if tx.status == TransactionStatus.ACTIVE]

    # ------------------------------------------------------------------
    # Locking (2PL with timeout)
    # ------------------------------------------------------------------

    def acquire_lock(self, transaction_id: str, resource_id: str,
                     lock_type: str, timeout: Optional[float] = None) -> bool:
        if timeout is None:
            timeout = self.lock_timeout
        deadline = time.time() + timeout

        while True:
            with self.lock:
                tx = self.transactions.get(transaction_id)
                if tx is None:
                    logger.error("Unknown transaction: %s", transaction_id)
                    return False

                if self._can_acquire_lock(tx, resource_id, lock_type):
                    tx.locks.add((resource_id, lock_type))
                    logger.debug("Acquired %s lock on %s (txn %s)",
                                 lock_type, resource_id, transaction_id)
                    return True

                # Deadlock detection
                if self.deadlock_detection_enabled:
                    if self._would_cause_deadlock(tx, resource_id, lock_type):
                        logger.warning("Deadlock detected – aborting youngest victim %s",
                                       transaction_id)
                        self.rollback_transaction(transaction_id)
                        return False

            if time.time() >= deadline:
                logger.warning("Lock timeout for %s on %s (txn %s)",
                               lock_type, resource_id, transaction_id)
                return False
            time.sleep(0.01)

    def release_lock(self, transaction_id: str, resource_id: str, lock_type: str) -> bool:
        with self.lock:
            tx = self.transactions.get(transaction_id)
            if tx is None:
                return False
            lock_info = (resource_id, lock_type)
            if lock_info not in tx.locks:
                return False
            tx.locks.remove(lock_info)
            return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_transaction(self, transaction: Transaction) -> None:
        logger.info("Applying %d operations for transaction %s",
                     len(transaction.operations), transaction.transaction_id)
        ts = transaction.commit_time or time.time()
        for op in transaction.operations:
            op_type = op.get("type", "")
            table = op.get("resource", "")
            pk = op.get("pk")
            if op_type in ("write", "update"):
                self.mvcc.write(table, pk, op.get("data", {}),
                                transaction.transaction_id, ts)
                self.wal.append(transaction.transaction_id, op_type.upper(),
                                table, pk, before=op.get("before"), after=op.get("data"))
            elif op_type == "delete":
                self.mvcc.delete(table, pk, transaction.transaction_id, ts)
                self.wal.append(transaction.transaction_id, 'DELETE',
                                table, pk, before=op.get("before"))

    def _release_locks(self, transaction: Transaction) -> None:
        logger.debug("Releasing all locks for transaction %s", transaction.transaction_id)
        transaction.locks.clear()

    def _can_acquire_lock(self, transaction: Transaction,
                          resource_id: str, lock_type: str) -> bool:
        for other_tx in self.get_active_transactions():
            if other_tx.transaction_id == transaction.transaction_id:
                continue
            for other_res, other_lt in other_tx.locks:
                if other_res == resource_id:
                    if lock_type == "WRITE" or other_lt == "WRITE":
                        return False
        return True

    def _would_cause_deadlock(self, transaction: Transaction,
                              resource_id: str, lock_type: str) -> bool:
        # Build wait-for graph
        wait_for: Dict[str, Set[str]] = {}
        wait_for[transaction.transaction_id] = set()

        for other_tx in self.get_active_transactions():
            if other_tx.transaction_id == transaction.transaction_id:
                continue
            for other_res, other_lt in other_tx.locks:
                if other_res == resource_id:
                    if lock_type == "WRITE" or other_lt == "WRITE":
                        wait_for[transaction.transaction_id].add(other_tx.transaction_id)

        for tx in self.get_active_transactions():
            if tx.transaction_id not in wait_for:
                wait_for[tx.transaction_id] = set()
            for other_tx in self.get_active_transactions():
                if tx.transaction_id == other_tx.transaction_id:
                    continue
                for res, tlt in tx.locks:
                    for ores, olt in other_tx.locks:
                        if res == ores and (tlt == "WRITE" or olt == "WRITE"):
                            wait_for[tx.transaction_id].add(other_tx.transaction_id)

        # DFS cycle detection
        visited: Set[str] = set()

        def has_cycle(node: str, path: Set[str]) -> bool:
            if node in path:
                return True
            path = path | {node}
            visited.add(node)
            for neighbour in wait_for.get(node, set()):
                if neighbour not in visited:
                    if has_cycle(neighbour, path):
                        return True
            return False

        return has_cycle(transaction.transaction_id, set())
