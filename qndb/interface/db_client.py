"""
Client interface for the quantum database system.
Provides connection handling and query execution.
"""

import logging
import uuid
from typing import Dict, List, Any, Optional, Union

from ..core.quantum_engine import QuantumEngine
from ..middleware.optimizer import QueryOptimizer
from ..middleware.scheduler import JobScheduler, ResourceManager, QuantumJob, JobPriority
from ..security.access_control import AccessControlManager 
from .query_language import QueryParser
from .query_executor import QueryExecutor
from .transaction_manager import TransactionManager
from .connection_pool import ConnectionPool
from ..utilities.logging import get_logger

logger = logging.getLogger(__name__)

class QuantumDatabaseClient:
    """Main client interface for the quantum database system."""
    
    # Class-level data storage (shared across all instances)
    _in_memory_db = {}  # Table name -> list of records
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize a new database client.
        
        Args:
            config: Configuration dictionary containing database connection parameters
        """
        self.config = config
        self.connection_pool = ConnectionPool(config)
        self.transaction_manager = TransactionManager()
        self.query_parser = QueryParser()
        self.access_controller = AccessControlManager()
        self.query_optimizer = QueryOptimizer()
        resource_manager = ResourceManager(total_qubits=50, max_parallel_jobs=5)
        self.job_scheduler = JobScheduler(resource_manager)
        
        logger.info("Database client initialized with config: %s", config)
    
    def connect(self, username: str, password: str = None) -> bool:
        """
        Connect to the quantum database.
        
        Args:
            username: User's username
            password: User's password
            
        Returns:
            True if connection was successful, False otherwise
        """
        try:
            # Store credentials for reconnection
            self.config["username"] = username
            self.config["password"] = password
            
            # Authenticate user first
            credentials = {
                'username': username,
                'password': password
            }
            user = self.access_controller.authenticate(credentials)
            if not user:
                logger.warning(f"Authentication failed for user: {username}")
                return False
            
            # Get a connection from the pool
            self.connection = self.connection_pool.get_connection()
            self.connection.user_id = username
            
            logger.info(f"Connected successfully as {username}")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            return False

    def _enable_auto_reconnect(self):
        """Configure auto-reconnect for the current connection."""
        if hasattr(self, 'connection'):
            # Make sure the connection object has reconnect capability
            if not hasattr(self.connection, 'reconnect'):
                from datetime import datetime
                
                # Add the reconnect method if it doesn't exist
                def reconnect():
                    try:
                        logger.info("Auto-reconnect triggered")
                        self.connection.is_active = True
                        self.connection.last_activity = datetime.now() if datetime else None
                        return True
                    except Exception as e:
                        logger.error(f"Auto-reconnect failed: {str(e)}")
                        return False
                        
                self.connection.reconnect = reconnect
                self.connection.is_active = True

    def disconnect(self) -> None:
        """Close the database connection and release resources."""
        if hasattr(self, 'connection'):
            self.connection_pool.release_connection(self.connection)
            delattr(self, 'connection')
            logger.info("Disconnected from quantum database")
        
    def execute_query(self, query_string, params=None):
        """
        Execute a SQL query on the database.
        
        Args:
            query_string: The SQL query to execute
            params: Optional parameters for the query
            
        Returns:
            Query result object with ``success``, ``rows``, ``transaction_id``.
        """
        try:
            # Start a new transaction
            transaction_id = self.transaction_manager.begin_transaction()
            
            # 1. Parse the query
            parsed_query = self.query_parser.parse(query_string, params)
            
            # Get query details
            query_type = parsed_query.query_type.value if hasattr(parsed_query.query_type, 'value') else str(parsed_query.query_type)
            
            # 2. Authorization check
            user_uuid = self._resolve_user_uuid()
            
            query_dict = parsed_query.to_dict() if hasattr(parsed_query, 'to_dict') else {}
            logger.info(f"Authorizing query on table {query_dict.get('target_table')} for user {user_uuid}")
            
            if not self.access_controller.authorize_query(query_dict, user_uuid):
                logger.warning(f"Query not authorized for user {user_uuid}: {query_string}")
                return {
                    "success": False,
                    "error": "Query not authorized",
                    "transaction_id": str(transaction_id)
                }
            
            # 3. Optimize the query
            optimized_query = self.query_optimizer.optimize(parsed_query)
            
            # 4. Execute via the QueryExecutor (volcano-style pipeline)
            executor = QueryExecutor(QuantumDatabaseClient._in_memory_db)
            result = executor.execute(optimized_query)
            
            # 5. Commit transaction
            self.transaction_manager.commit_transaction(transaction_id)
            
            return {
                "success": True,
                "rows": result,
                "transaction_id": str(transaction_id)
            }
            
        except Exception as e:
            logger.error(f"Query execution failed: {str(e)}")
            if 'transaction_id' in locals():
                self.transaction_manager.rollback_transaction(transaction_id)
                return {
                    "success": False,
                    "error": str(e),
                    "transaction_id": str(transaction_id)
                }
            else:
                return {
                    "success": False,
                    "error": str(e),
                    "transaction_id": str(uuid.uuid4())
                }

    def _resolve_user_uuid(self):
        """Resolve the current user's UUID for authorization."""
        user_uuid = None
        if hasattr(self, 'connection'):
            if hasattr(self.access_controller, 'get_user_by_username'):
                user = self.access_controller.get_user_by_username(self.connection.user_id)
                if user:
                    user_uuid = user.user_id
            if not user_uuid and hasattr(self.access_controller, 'users'):
                for uid, user in self.access_controller.users.items():
                    if hasattr(user, 'username') and user.username == self.connection.user_id:
                        user_uuid = uid
                        break
            if not user_uuid:
                user_uuid = self.connection.user_id
        return user_uuid
        
    def batch_execute(self, queries: List[str], params: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Execute multiple queries as a batch.
        
        Args:
            queries: List of quantum SQL query strings
            params: Optional list of parameter dictionaries for each query
            
        Returns:
            List of results for each query
        """
        results = []
        transaction_id = self.transaction_manager.begin_transaction()
        
        try:
            for i, query in enumerate(queries):
                query_params = None if params is None else params[i]
                
                # Parse and optimize each query
                parsed_query = self.query_parser.parse(query, query_params)
                
                # Get a proper user UUID for authorization
                user_uuid = None
                if hasattr(self.access_controller, 'get_user_by_username'):
                    user = self.access_controller.get_user_by_username(self.connection.user_id)
                    if user:
                        user_uuid = user.id
                
                if not user_uuid and hasattr(self.access_controller, 'users'):
                    for uid, user in self.access_controller.users.items():
                        if hasattr(user, 'username') and user.username == self.connection.user_id:
                            user_uuid = uid
                            break
                
                if not user_uuid:
                    user_uuid = self.connection.user_id
                    
                # Convert parsed_query to dict for authorization
                query_dict = parsed_query.to_dict() if hasattr(parsed_query, 'to_dict') else {}
                
                # Authorize with the dict representation
                if not self.access_controller.authorize_query(query_dict, user_uuid):
                    results.append({
                        "success": False,
                        "error": "Query not authorized",
                        "transaction_id": str(transaction_id)
                    })
                    continue
                
                optimized_query = self.query_optimizer.optimize(parsed_query)
                
                # Create a QuantumJob from the optimized query
                job = QuantumJob(
                    job_id=str(uuid.uuid4()),
                    query=optimized_query,
                    priority=JobPriority.NORMAL,
                    user_id=user_uuid
                )
                
                # Submit the job instead of calling schedule
                job_id = self.job_scheduler.submit_job(job)
                
                try:
                    result = self.connection.execute(job_id)
                    results.append({
                        "success": True,
                        "result": result,
                        "job_id": job_id
                    })
                except Exception as conn_error:
                    logger.error(f"Connection error in batch: {str(conn_error)}")
                    results.append({
                        "success": False,
                        "error": f"Connection error: {str(conn_error)}",
                        "job_id": job_id
                    })
                    
            # Commit the transaction if all queries succeed
            self.transaction_manager.commit_transaction(transaction_id)
            logger.info("Batch execution completed successfully")
            return results
            
        except Exception as e:
            # Rollback the entire batch on failure
            self.transaction_manager.rollback_transaction(transaction_id)
            logger.error("Batch execution failed: %s", str(e))
            results.append({
                "success": False,
                "error": str(e)
            })
            return results
    
    def get_quantum_resource_stats(self) -> Dict[str, Any]:
        """
        Get statistics about quantum resources usage.
        
        Returns:
            Dictionary containing quantum resource statistics
        """
        if not hasattr(self, 'connection'):
            raise RuntimeError("Not connected to database")
            
        return self.connection.get_resource_stats()
    
    def create_quantum_circuit_from_query(self, query: str) -> Dict[str, Any]:
        """
        Generate a quantum circuit from a query without executing it.
        Useful for visualization and analysis.
        
        Args:
            query: Quantum SQL query string
            
        Returns:
            Dictionary containing circuit information
        """
        parsed_query = self.query_parser.parse(query)
        optimized_query = self.query_optimizer.optimize(parsed_query)
        circuit = optimized_query.to_circuit()
        
        return {
            "circuit": circuit,
            "qubit_count": circuit.qubit_count,
            "depth": circuit.depth,
            "gates": circuit.gate_counts
        }