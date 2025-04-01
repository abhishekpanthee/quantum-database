
# examples/complex_queries.py

"""
Complex queries example for quantum database.

This example demonstrates advanced quantum database operations including:
- Quantum joins
- Quantum aggregations
- Superposition queries
- Quantum indexing
"""

import time
import numpy as np
from interface.db_client import QuantumDatabaseClient
from interface.query_language import QueryBuilder
from utilities.benchmarking import benchmark_query
from utilities.visualization import VisualizeCircuit

def run_complex_queries_example():
    """
    Run complex queries example for the quantum database.
    """
    print("=== Quantum Database Complex Queries Example ===")
    
    # Connect to the quantum database
    client = QuantumDatabaseClient()
    connection = client.connect(host="localhost", port=5000)
    print("Connected to quantum database")
    
    # Create and populate sample tables if they don't exist
    setup_database(connection)
    
    # Example 1: Quantum Join with Grover's Algorithm
    print("\n--- Example 1: Quantum Join with Grover's Algorithm ---")
    quantum_join_query = """
    SELECT c.customer_name, o.order_date, o.amount
    FROM customers c
    QUANTUM JOIN orders o ON c.customer_id = o.customer_id
    WHERE o.amount > 1000
    USING quantum_algorithm='grover'
    """
    
    # Benchmark the quantum join
    print("Benchmarking quantum join...")
    benchmark_result = benchmark_query(connection, quantum_join_query)
    print(f"Quantum join completed in {benchmark_result.execution_time:.6f} seconds")
    print(f"Classical equivalent would take approximately {benchmark_result.classical_estimate:.6f} seconds")
    print(f"Quantum speedup: {benchmark_result.speedup_factor:.2f}x")
    
    # Execute the join and display results
    result = connection.execute(quantum_join_query)
    print("\nJoin results:")
    for i, record in enumerate(result.records[:5]):
        print(f"  {record}")
    if len(result.records) > 5:
        print(f"  ... and {len(result.records) - 5} more records")
    
    # Example 2: Quantum Aggregation in Superposition
    print("\n--- Example 2: Quantum Aggregation in Superposition ---")
    agg_query = """
    SELECT 
        QUANTUM_AGGREGATE(amount, 'sum') AS total_amount,
        QUANTUM_AGGREGATE(amount, 'average') AS avg_amount,
        QUANTUM_AGGREGATE(amount, 'max') AS max_amount
    FROM orders
    IN SUPERPOSITION WHERE order_date BETWEEN '2023-01-01' AND '2023-12-31'
    """
    
    result = connection.execute(agg_query)
    print("Aggregation results:")
    for key, value in result.records[0].items():
        print(f"  {key}: {value}")
    
    # Visualize the circuit for the aggregation
    print("\nVisualizing quantum aggregation circuit...")
    agg_circuit = result.metadata.get("circuit")
    visualizer = VisualizeCircuit()
    visualizer.show_circuit(agg_circuit)
    
    # Example 3: Complex Query with Quantum Indexing
    print("\n--- Example 3: Complex Query with Quantum Indexing ---")
    print("Creating quantum index on orders.amount...")
    
    create_index_query = """
    CREATE QUANTUM INDEX amount_idx ON orders(amount)
    USING quantum_method='amplitude_encoding'
    """
    connection.execute(create_index_query)
    
    # Complex query using quantum index
    indexed_query = """
    SELECT o.order_id, o.amount, c.customer_name
    FROM orders o
    QUANTUM JOIN customers c ON o.customer_id = c.customer_id
    WHERE o.amount BETWEEN 500 AND 1500
    ORDER BY o.amount DESC
    USING quantum_index='amount_idx'
    LIMIT 5
    """
    
    print("Executing query with quantum index...")
    result = connection.execute(indexed_query)
    print("\nResults (using quantum index):")
    for record in result.records:
        print(f"  {record}")
    
    # Example 4: Quantum Pattern Recognition
    print("\n--- Example 4: Quantum Pattern Recognition ---")
    pattern_query = """
    SELECT customer_id, 
           QUANTUM_PATTERN_DETECT(
               purchase_history, 
               pattern='repeat_purchase', 
               confidence=0.75
           ) AS repeat_customer_probability
    FROM customer_behaviors
    WHERE first_purchase_date > '2023-01-01'
    """
    
    print("Detecting purchase patterns using quantum algorithm...")
    result = connection.execute(pattern_query)
    print("\nPattern detection results:")
    for i, record in enumerate(result.records[:5]):
        print(f"  Customer {record['customer_id']}: {record['repeat_customer_probability']:.2f} probability")
    if len(result.records) > 5:
        print(f"  ... and {len(result.records) - 5} more records")
    
    # Close the connection
    connection.close()
    print("\nConnection closed")
    print("Complex queries example completed")

def setup_database(connection):
    """
    Set up sample database tables for the example.
    """
    # Create customers table
    create_customers = """
    CREATE QUANTUM TABLE IF NOT EXISTS customers (
        customer_id INT PRIMARY KEY,
        customer_name TEXT,
        email TEXT,
        signup_date DATE
    ) WITH ENCODING=basis
    """
    connection.execute(create_customers)
    
    # Create orders table
    create_orders = """
    CREATE QUANTUM TABLE IF NOT EXISTS orders (
        order_id INT PRIMARY KEY,
        customer_id INT,
        order_date DATE,
        amount FLOAT
    ) WITH ENCODING=amplitude
    """
    connection.execute(create_orders)
    
    # Create customer behaviors table
    create_behaviors = """
    CREATE QUANTUM TABLE IF NOT EXISTS customer_behaviors (
        customer_id INT PRIMARY KEY,
        first_purchase_date DATE,
        purchase_history QUANTUM_VECTOR,
        visit_frequency FLOAT
    ) WITH ENCODING=amplitude
    """
    connection.execute(create_behaviors)
    
    # Check if data needs to be populated
    count_query = "SELECT COUNT(*) FROM customers"
    result = connection.execute(count_query)
    
    if result.records[0]["COUNT(*)"] == 0:
        # Populate with sample data
        print("Populating database with sample data...")
        
        # Insert sample customers
        for i in range(1, 21):
            name = f"Customer {i}"
            email = f"customer{i}@example.com"
            date = f"2023-{np.random.randint(1, 13):02d}-{np.random.randint(1, 29):02d}"
            
            insert_query = f"""
            INSERT INTO customers (customer_id, customer_name, email, signup_date)
            VALUES ({i}, '{name}', '{email}', '{date}')
            """
            connection.execute(insert_query)
        
        # Insert sample orders
        for i in range(1, 101):
            customer_id = np.random.randint(1, 21)
            month = np.random.randint(1, 13)
            day = np.random.randint(1, 29)
            amount = np.random.uniform(100, 2000)
            date = f"2023-{month:02d}-{day:02d}"
            
            insert_query = f"""
            INSERT INTO orders (order_id, customer_id, order_date, amount)
            VALUES ({i}, {customer_id}, '{date}', {amount:.2f})
            """
            connection.execute(insert_query)
        
        # Insert sample customer behaviors
        for i in range(1, 21):
            month = np.random.randint(1, 13)
            day = np.random.randint(1, 29)
            first_date = f"2023-{month:02d}-{day:02d}"
            
            # Generate quantum vector for purchase history (simplified for example)
            vector_data = np.random.random(8).tolist()
            vector_str = ", ".join([str(v) for v in vector_data])
            
            frequency = np.random.uniform(1, 10)
            
            insert_query = f"""
            INSERT INTO customer_behaviors (customer_id, first_purchase_date, purchase_history, visit_frequency)
            VALUES ({i}, '{first_date}', QUANTUM_VECTOR[{vector_str}], {frequency:.2f})
            """
            connection.execute(insert_query)
            
        print("Sample data populated successfully")

if __name__ == "__main__":
    run_complex_queries_example()

