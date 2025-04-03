"""
Transaction manager for ensuring ACID compliance in quantum database operations.
"""

import uuid
import time
import logging
from typing import Dict, List, Any, Optional, Set
from enum import Enum
from threading import Lock

logger = logging.getLogger(__name__)

class TransactionStatus(Enum):
    """Possible states of a database transaction."""
    ACTIVE = "active"
    COMMITTED = "committed"
    ABORTED = "aborted"
    PENDING = "pending"

class IsolationLevel(Enum):
    """Transaction isolation levels."""
    READ_UNCOMMITTED = "read_uncommitted"
    READ_COMMITTED = "read_committed"
    REPEATABLE_READ = "repeatable_read"
    SERIALIZABLE = "serializable"
    QUANTUM_CONSISTENT = "quantum_consistent"  # Special quantum-specific isolation

class Transaction:
    """Represents a database transaction with ACID properties."""
    
    def __init__(self, transaction_id: str, isolation_level: IsolationLevel = IsolationLevel.SERIALIZABLE):
        """
        Initialize a new transaction.
        
        Args:
            transaction_id: Unique identifier for the transaction
            isolation_level: The desired isolation level
        """
        self.transaction_id = transaction_id
        self.status = TransactionStatus.ACTIVE
        self.isolation_level = isolation_level
        self.start_time = time.time()
        self.commit_time = None
        self.operations = []
        self.locks = set()
        self.accessed_resources = set()
        self.modified_resources = set()
        
    def add_operation(self, operation: Dict[str, Any]) -> None:
        """Add an operation to the transaction log."""
        self.operations.append(operation)
        
        # Track accessed and modified resources
        resource = operation.get("resource")
        if resource:
            self.accessed_resources.add(resource)
            if operation.get("type") in ["write", "update", "delete"]:
                self.modified_resources.add(resource)
    
    def has_conflicts(self, other_transaction: 'Transaction') -> bool:
        """
        Check if this transaction conflicts with another.
        
        Args:
            other_transaction: Another transaction to check for conflicts
            
        Returns:
            True if there is a conflict, False otherwise
        """
        # If either transaction is already committed or aborted, no conflict
        if (self.status != TransactionStatus.ACTIVE or 
            other_transaction.status != TransactionStatus.ACTIVE):
            return False
        
        # Check for resource conflicts based on isolation level
        if self.isolation_level == IsolationLevel.SERIALIZABLE:
            # Any overlap in accessed resources could cause a conflict
            return bool(self.accessed_resources.intersection(other_transaction.modified_resources) or
                        self.modified_resources.intersection(other_transaction.accessed_resources))
        
        elif self.isolation_level == IsolationLevel.REPEATABLE_READ:
            # Conflicts if another transaction modifies what this transaction reads
            return bool(self.accessed_resources.intersection(other_transaction.modified_resources))
        
        elif self.isolation_level == IsolationLevel.READ_COMMITTED:
            # No conflict if the other transaction has committed its changes
            return False
        
        elif self.isolation_level == IsolationLevel.QUANTUM_CONSISTENT:
            # Special quantum consistency check that considers quantum superposition
            # In a real implementation, this would use quantum-specific logic
            return bool(self.modified_resources.intersection(other_transaction.modified_resources))
        
        # Default to most permissive
        return False

class TransactionManager:
    """Manages database transactions to ensure ACID properties."""
    
    def __init__(self):
        """Initialize the transaction manager."""
        self.transactions = {}  # Dictionary of active transactions
        self.lock = Lock()  # For thread safety
        self.default_isolation_level = IsolationLevel.SERIALIZABLE
        self.deadlock_detection_enabled = True
        logger.info("Transaction manager initialized")
    
    def begin_transaction(self, isolation_level: Optional[IsolationLevel] = None) -> str:
        """
        Begin a new transaction.
        
        Args:
            isolation_level: Optional isolation level for the transaction
            
        Returns:
            Transaction ID
        """
        with self.lock:
            # Generate a unique transaction ID
            transaction_id = str(uuid.uuid4())
            
            # Use default isolation level if none specified
            if isolation_level is None:
                isolation_level = self.default_isolation_level
            
            # Create and store the transaction
            transaction = Transaction(transaction_id, isolation_level)
            self.transactions[transaction_id] = transaction
            
            logger.info("Started transaction %s with isolation level %s", 
                       transaction_id, isolation_level.value)
            
            return transaction_id
    
    def commit_transaction(self, transaction_id: str) -> bool:
        """
        Commit a transaction.
        
        Args:
            transaction_id: ID of the transaction to commit
            
        Returns:
            True if commit successful, False otherwise
        """
        with self.lock:
            if transaction_id not in self.transactions:
                logger.error("Attempted to commit unknown transaction: %s", transaction_id)
                return False
            
            transaction = self.transactions[transaction_id]
            
            # Check if the transaction can be committed
            if transaction.status != TransactionStatus.ACTIVE:
                logger.error("Cannot commit transaction %s with status %s", 
                           transaction_id, transaction.status.value)
                return False
            
            # Check for conflicts with other active transactions
            for other_id, other_tx in self.transactions.items():
                if other_id != transaction_id and transaction.has_conflicts(other_tx):
                    logger.warning("Transaction %s has conflicts, cannot commit", transaction_id)
                    return False
            
            # Update transaction status
            transaction.status = TransactionStatus.COMMITTED
            transaction.commit_time = time.time()
            
            # Apply the transaction's operations to the database
            self._apply_transaction(transaction)
            
            # Release locks
            self._release_locks(transaction)
            
            logger.info("Committed transaction %s", transaction_id)
            
            # Keep transaction record for a while, then clean up
            # In a real implementation, this would be handled by a cleanup process
            
            return True
    
    def rollback_transaction(self, transaction_id: str) -> bool:
        """
        Rollback (abort) a transaction.
        
        Args:
            transaction_id: ID of the transaction to rollback
            
        Returns:
            True if rollback successful, False otherwise
        """
        with self.lock:
            if transaction_id not in self.transactions:
                logger.error("Attempted to rollback unknown transaction: %s", transaction_id)
                return False
            
            transaction = self.transactions[transaction_id]
            
            # Only active transactions can be rolled back
            if transaction.status != TransactionStatus.ACTIVE:
                logger.error("Cannot rollback transaction %s with status %s", 
                           transaction_id, transaction.status.value)
                return False
            
            # Update transaction status
            transaction.status = TransactionStatus.ABORTED
            
            # Release locks
            self._release_locks(transaction)
            
            logger.info("Rolled back transaction %s", transaction_id)
            
            return True
    
    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """
        Get a transaction by ID.
        
        Args:
            transaction_id: ID of the transaction to retrieve
            
        Returns:
            Transaction object or None if not found
        """
        with self.lock:
            return self.transactions.get(transaction_id)
    
    def get_active_transactions(self) -> List[Transaction]:
        """
        Get a list of all active transactions.
        
        Returns:
            List of active Transaction objects
        """
        with self.lock:
            return [tx for tx in self.transactions.values() 
                   if tx.status == TransactionStatus.ACTIVE]
    
    def acquire_lock(self, transaction_id: str, resource_id: str, lock_type: str) -> bool:
        """
        Acquire a lock on a resource for a transaction.
        
        Args:
            transaction_id: ID of the transaction
            resource_id: ID of the resource to lock
            lock_type: Type of lock (READ or WRITE)
            
        Returns:
            True if lock acquired, False otherwise
        """
        with self.lock:
            if transaction_id not in self.transactions:
                logger.error("Unknown transaction: %s", transaction_id)
                return False
            
            transaction = self.transactions[transaction_id]
            
            # Check if lock can be acquired
            if not self._can_acquire_lock(transaction, resource_id, lock_type):
                if self.deadlock_detection_enabled:
                    # Check for deadlocks
                    if self._would_cause_deadlock(transaction, resource_id, lock_type):
                        logger.warning("Deadlock detected, aborting transaction %s", transaction_id)
                        self.rollback_transaction(transaction_id)
                        return False
                
                logger.warning("Cannot acquire %s lock on %s for transaction %s", 
                             lock_type, resource_id, transaction_id)
                return False
            
            # Add lock to transaction
            lock_info = (resource_id, lock_type)
            transaction.locks.add(lock_info)
            
            logger.debug("Acquired %s lock on %s for transaction %s", 
                       lock_type, resource_id, transaction_id)
            
            return True
    
    def release_lock(self, transaction_id: str, resource_id: str, lock_type: str) -> bool:
        """
        Release a lock on a resource for a transaction.
        
        Args:
            transaction_id: ID of the transaction
            resource_id: ID of the resource
            lock_type: Type of lock (READ or WRITE)
            
        Returns:
            True if lock released, False otherwise
        """
        with self.lock:
            if transaction_id not in self.transactions:
                logger.error("Unknown transaction: %s", transaction_id)
                return False
            
            transaction = self.transactions[transaction_id]
            
            # Check if transaction has the lock
            lock_info = (resource_id, lock_type)
            if lock_info not in transaction.locks:
                logger.warning("Transaction %s does not have %s lock on %s", 
                             transaction_id, lock_type, resource_id)
                return False
            
            # Remove lock from transaction
            transaction.locks.remove(lock_info)
            
            logger.debug("Released %s lock on %s for transaction %s", 
                       lock_type, resource_id, transaction_id)
            
            return True
    
    def _apply_transaction(self, transaction: Transaction) -> None:
        """
        Apply a committed transaction's operations to the database.
        
        Args:
            transaction: The committed transaction to apply
        """
        # In a real implementation, this would apply the changes to the actual database
        # Here we just log the operations
        logger.info("Applying %d operations for transaction %s", 
                   len(transaction.operations), transaction.transaction_id)
        
        for op in transaction.operations:
            logger.debug("Applying operation: %s", op)
    
    def _release_locks(self, transaction: Transaction) -> None:
        """
        Release all locks held by a transaction.
        
        Args:
            transaction: The transaction whose locks should be released
        """
        logger.debug("Releasing all locks for transaction %s", transaction.transaction_id)
        transaction.locks.clear()
    
    def _can_acquire_lock(self, transaction: Transaction, resource_id: str, lock_type: str) -> bool:
        """
        Check if a lock can be acquired.
        
        Args:
            transaction: The transaction requesting the lock
            resource_id: ID of the resource to lock
            lock_type: Type of lock (READ or WRITE)
            
        Returns:
            True if lock can be acquired, False otherwise
        """
        # Check all active transactions
        for other_tx in self.get_active_transactions():
            # Skip the current transaction
            if other_tx.transaction_id == transaction.transaction_id:
                continue
            
            # Check for conflicting locks
            for other_resource, other_lock_type in other_tx.locks:
                if other_resource == resource_id:
                    # Write locks conflict with any other lock
                    if lock_type == "WRITE" or other_lock_type == "WRITE":
                        return False
        
        return True
    
    def _would_cause_deadlock(self, transaction: Transaction, resource_id: str, lock_type: str) -> bool:
        """
        Check if acquiring a lock would cause a deadlock.
        
        Args:
            transaction: The transaction requesting the lock
            resource_id: ID of the resource to lock
            lock_type: Type of lock (READ or WRITE)
            
        Returns:
            True if a deadlock would be created, False otherwise
        """
        # This is a simplified deadlock detection algorithm
        # In a real implementation, this would be more sophisticated
        
        # Create a wait-for graph
        wait_for = {}
        
        # Add edges for the current transaction waiting for resources
        wait_for[transaction.transaction_id] = set()
        
        for other_tx in self.get_active_transactions():
            if other_tx.transaction_id == transaction.transaction_id:
                continue
            
            for other_resource, other_lock_type in other_tx.locks:
                if other_resource == resource_id:
                    if lock_type == "WRITE" or other_lock_type == "WRITE":
                        wait_for[transaction.transaction_id].add(other_tx.transaction_id)
        
        # Add edges for other transactions waiting for resources
        for tx in self.get_active_transactions():
            if tx.transaction_id not in wait_for:
                wait_for[tx.transaction_id] = set()
            
            for other_tx in self.get_active_transactions():
                if tx.transaction_id == other_tx.transaction_id:
                    continue
                
                for resource, tx_lock_type in tx.locks:
                    for other_resource, other_lock_type in other_tx.locks:
                        if resource == other_resource:
                            if tx_lock_type == "WRITE" or other_lock_type == "WRITE":
                                wait_for[tx.transaction_id].add(other_tx.transaction_id)
        
        # Check for cycles in the wait-for graph using DFS
        visited = set()
        
        def has_cycle(node, path):
            if node in path:
                return True
            
            path.add(node)
            visited.add(node)
            
            for neighbor in wait_for.get(node, set()):
                if neighbor not in visited:
                    if has_cycle(neighbor, path.copy()):
                        return True
            
            return False
        
        # Start DFS from the current transaction
        return has_cycle(transaction.transaction_id, set())