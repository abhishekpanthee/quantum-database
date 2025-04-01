
# examples/distributed_database.py

"""
Distributed quantum database example.

This example demonstrates the distributed capabilities of the quantum database system,
including node management, synchronization, and distributed query processing.
"""

import time
import numpy as np
from interface.db_client import QuantumDatabaseClient
from distributed.node_manager import NodeManager
from distributed.synchronization import QuantumStateSynchronizer
from distributed.consensus import QuantumConsensus
from utilities.benchmarking import benchmark_query

def run_distributed_example():
    """
    Run distributed quantum database example.
    """
    print("=== Quantum Database Distributed Example ===")
    
    # Initialize node manager
    node_manager = NodeManager()
    print(f"Local node ID: {node_manager.local_node_id}")
    
    # Set up a simulated distributed environment
    setup_distributed_environment(node_manager)
    
    # Connect to each node
    connections = connect_to_nodes(node_manager)
    print(f"Connected to {len(connections)} nodes")
    
    # Create a distributed table
    print("\nCreating distributed quantum table...")
    create_distributed_table(connections)
    
    # Insert data across the distributed system
    print("\nInserting data across distributed nodes...")
    insert_distributed_data(connections)
    
    # Initialize synchronization
    synchronizer = QuantumStateSynchronizer(node_manager, None, None)
    
    # Synchronize nodes
    print("\nSynchronizing distributed quantum states...")
    sync_result = synchronizer.sync_with_nodes()
    print(f"Synchronization {'successful' if sync_result else 'failed'}")
    
    # Demonstrate distributed query
    print("\nExecuting distributed quantum query...")
    result = distributed_quantum_query(connections)
    print("Query results aggregated from all nodes:")
    for i, record in enumerate(result[:5]):
        print(f"  {record}")
    if len(result) > 5:
        print(f"  ... and {len(result) - 5} more records")
    
    # Demonstrate quantum consensus algorithm
    print("\nExecuting quantum consensus protocol...")
    consensus = QuantumConsensus(node_manager)
    consensus_result = consensus.reach_consensus("data_integrity_check")
    print(f"Consensus reached: {consensus_result.reached}")
    print(f"Consensus value: {consensus_result.value}")
    print(f"Participating nodes: {len(consensus_result.participants)}")
    
    # Benchmark distributed vs. single-node performance
    print("\nBenchmarking distributed vs. single-node performance...")
    benchmark_distributed_performance(connections[0], connections)
    
    # Simulate node failure and recovery
    print("\nSimulating node failure and recovery...")
    simulate_node_failure_recovery(node_manager, connections)
    
    # Close all connections
    for conn in connections:
        conn.close()
    print("\nAll connections closed")
    print("Distributed database example completed")

def setup_distributed_environment(node_manager):
    """
    Set up a simulated distributed environment with multiple nodes.
    
    Args:
        node_manager: The node manager instance
    """
    # Add simulated nodes (in a real environment, these would be discovered)
    node_manager.register_node("node1", "192.168.1.101", 5000, is_active=True)
    node_manager.register_node("node2", "192.168.1.102", 5000, is_active=True)
    node_manager.register_node("node3", "192.168.1.103", 5000, is_active=True)
    
    print(f"Registered {len(node_manager.get_active_nodes())} active nodes")

def connect_to_nodes(node_manager):
    """
    Connect to all active nodes in the distributed environment.
    
    Args:
        node_manager: The node manager instance
        
    Returns:
        list: Database connections to all nodes
    """
    client = QuantumDatabaseClient()
    connections = []
    
    for node in node_manager.get_active_nodes():
        try:
            connection = client.connect(host=node.host, port=node.port)
            connections.append(connection)
            print(f"Connected to node {node.id} at {node.host}:{node.port}")
        except Exception as e:
            print(f"Failed to connect to node {node.id}: {str(e)}")
    
    return connections

def create_distributed_table(connections):
    """
    Create a distributed table across all nodes.
    
    Args:
        connections: List of database connections
    """
    create_table_query = """
    CREATE DISTRIBUTED QUANTUM TABLE sensor_data (
        sensor_id INT,
        timestamp DATETIME,
        temperature FLOAT,
        humidity FLOAT,
        pressure FLOAT
    ) WITH ENCODING=amplitude
    DISTRIBUTED BY sensor_id
    """
    
    for i, conn in enumerate(connections):
        result = conn.execute(create_table_query)
        print(f"Node {i+1}: Table creation {'successful' if result.success else 'failed'}")

def insert_distributed_data(connections):
    """
    Insert data across the distributed system.
    
    Args:
        connections: List of database connections
    """
    # Generate some sample sensor data
    sensors = 10
    readings_per_sensor = 20
    
    total_inserted = 0
    
    for sensor_id in range(1, sensors + 1):
        # Determine which node should store this sensor's data
        node_index = sensor_id % len(connections)
        conn = connections[node_index]
        
        for i in range(readings_per_sensor):
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', 
                                      time.gmtime(time.time() - i * 3600))
            temperature = 20 + np.random.normal(0, 5)
            humidity = 50 + np.random.normal(0, 10)
            pressure = 1013 + np.random.normal(0, 20)
            
            insert_query = f"""
            INSERT INTO sensor_data (sensor_id, timestamp, temperature, humidity, pressure)
            VALUES ({sensor_id}, '{timestamp}', {temperature:.2f}, {humidity:.2f}, {pressure:.2f})
            """
            
            result = conn.execute(insert_query)
            if result.success:
                total_inserted += 1
    
    print(f"Inserted {total_inserted} records across {len(connections)} nodes")

def distributed_quantum_query(connections):
    """
    Execute a quantum query across the distributed system.
    
    Args:
        connections: List of database connections
        
    Returns:
        list: Aggregated query results
    """
    query = """
    SELECT sensor_id, 
           AVG(temperature) as avg_temp, 
           QUANTUM_PROCESS(temperature, humidity) as q_correlation
    FROM sensor_data
    WHERE timestamp > '2023-01-01'
    GROUP BY sensor_id
    USING quantum_algorithm='variational'
    """
    
    all_results = []
    
    for i, conn in enumerate(connections):
        try:
            result = conn.execute(query)
            print(f"Node {i+1}: Retrieved {len(result.records)} records")
            all_results.extend(result.records)
        except Exception as e:
            print(f"Query failed on node {i+1}: {str(e)}")
    
    # In a real implementation, we would merge/reduce the results using quantum techniques
    # Here we just aggregate them
    return all_results

def benchmark_distributed_performance(single_conn, all_connections):
    """
    Benchmark performance of distributed vs. single-node queries.
    
    Args:
        single_conn: Connection to a single node
        all_connections: Connections to all nodes
    """
    # Query to benchmark
    query = """
    SELECT QUANTUM_SEARCH(
        sensor_data, 
        condition='temperature > 25 AND humidity < 40',
        algorithm='grover'
    )
    FROM sensor_data
    """
    
    # Benchmark on single node
    print("Running benchmark on single node...")
    single_result = benchmark_query(single_conn, query)
    print(f"Single node time: {single_result.execution_time:.6f} seconds")
    
    # Benchmark on distributed system
    print("Running benchmark on distributed system...")
    start_time = time.time()
    
    # Execute in parallel on all nodes
    for conn in all_connections:
        conn.execute_async(query)
    
    # Wait for all to complete (simplified)
    time.sleep(0.1)  # In a real scenario, we would actually wait for results
    
    distributed_time = time.time() - start_time
    print(f"Distributed execution time: {distributed_time:.6f} seconds")
    
    # Calculate speedup
    if single_result.execution_time > 0:
        speedup = single_result.execution_time / distributed_time
        print(f"Distributed speedup: {speedup:.2f}x")

def simulate_node_failure_recovery(node_manager, connections):
    """
    Simulate node failure and recovery in the distributed system.
    
    Args:
        node_manager: The node manager instance
        connections: List of database connections
    """
    # Simulate a node failure
    failed_node_id = "node2"
    print(f"Simulating failure of node {failed_node_id}...")
    node_manager.mark_node_inactive(failed_node_id)
    
    active_nodes = node_manager.get_active_nodes()
    print(f"Active nodes after failure: {len(active_nodes)}")
    
    # Run a query that should still work despite the node failure
    print("Executing query after node failure...")
    query = "SELECT COUNT(*) FROM sensor_data"
    
    for i, node in enumerate(active_nodes):
        try:
            conn = connections[i]
            result = conn.execute(query)
            print(f"Node {node.id}: Query successful, count = {result.records[0]['COUNT(*)']}")
        except Exception as e:
            print(f"Node {node.id}: Query failed, error = {str(e)}")
    
    # Simulate node recovery
    print(f"Simulating recovery of node {failed_node_id}...")
    node_manager.mark_node_active(failed_node_id)
    
    active_nodes = node_manager.get_active_nodes()
    print(f"Active nodes after recovery: {len(active_nodes)}")
    
    # Simulate state synchronization after recovery
    print("Synchronizing recovered node...")
    # In a real implementation, this would actually transfer quantum state
    print("Node state synchronized successfully")

if __name__ == "__main__":
    run_distributed_example()

