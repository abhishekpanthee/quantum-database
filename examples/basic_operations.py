# examples/basic_operations.py

"""
Basic operations example for quantum database.

This example demonstrates the fundamental operations of the quantum database system,
including connection, data insertion, querying, and basic transformations.
"""

import time
import numpy as np
from interface.db_client import QuantumDatabaseClient
from interface.query_language import QueryBuilder
from utilities.visualization import VisualizeCircuit

def run_basic_example():
    """
    Run basic operations example for the quantum database.
    """
    print("=== Quantum Database Basic Operations Example ===")
    
    # Connect to the quantum database
    client = QuantumDatabaseClient()
    connection = client.connect(host="localhost", port=5000)
    print("Connected to quantum database")
    
    # Create a new quantum table
    print("\nCreating quantum table 'users'...")
    create_table_query = """
    CREATE QUANTUM TABLE users (
        id INT PRIMARY KEY,
        name TEXT,
        age INT,
        balance FLOAT
    ) WITH ENCODING=amplitude
    """
    result = connection.execute(create_table_query)
    print(f"Table created: {result.success}")
    
    # Insert data using amplitude encoding
    print("\nInserting sample data...")
    users_data = [
        (1, "Alice", 28, 1250.75),
        (2, "Bob", 35, 2340.50),
        (3, "Charlie", 42, 5600.25),
        (4, "Diana", 31, 1800.00)
    ]
    
    # Insert each record
    for user in users_data:
        insert_query = f"""
        INSERT INTO users (id, name, age, balance)
        VALUES ({user[0]}, '{user[1]}', {user[2]}, {user[3]})
        """
        result = connection.execute(insert_query)
        print(f"Inserted user {user[1]}: {result.success}")
    
    # Demonstrate quantum search operation
    print("\nPerforming quantum search...")
    search_query = """
    SELECT * FROM users
    WHERE balance > 2000.0
    USING quantum_search
    """
    result = connection.execute(search_query)
    print("Search results:")
    for record in result.records:
        print(f"  {record}")
    
    # Visualize the quantum circuit for the search operation
    print("\nVisualizing quantum search circuit...")
    search_circuit = result.metadata.get("circuit")
    visualizer = VisualizeCircuit()
    visualizer.show_circuit(search_circuit)
    print("Circuit depth:", search_circuit.depth())
    print("Qubits used:", search_circuit.num_qubits())
    
    # Demonstrate quantum transformation
    print("\nPerforming quantum transformation...")
    transform_query = """
    SELECT id, name, age, QUANTUM_TRANSFORM(balance, 'fourier') AS transformed_balance
    FROM users
    """
    result = connection.execute(transform_query)
    print("Transformation results:")
    for record in result.records:
        print(f"  {record}")
    
    # Close the connection
    connection.close()
    print("\nConnection closed")
    print("Basic operations example completed")

if __name__ == "__main__":
    run_basic_example()

