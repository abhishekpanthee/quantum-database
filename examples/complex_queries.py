# examples/complex_queries.py

"""
Complex queries example for quantum database.
"""

import time
import uuid
import logging
import numpy as np
from qndb.interface.db_client import QuantumDatabaseClient
from qndb.utilities.benchmarking import BenchmarkRunner
from qndb.security.access_control import Permission, ResourceType

def run_complex_queries_example():
    # Reduce logging noise
    logging_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.ERROR)
    
    print("=== Quantum Database Complex Queries Example ===")
    
    config = {
        "host": "localhost",
        "port": 5000,
        "max_connections": 10,
        "timeout": 30,
        "quantum_backend": "simulator"
    }
    
    client = None
    
    try:
        # Initialize client
        print("\nInitializing database client...")
        client = QuantumDatabaseClient(config)
        
        # Create admin user with proper UUID
        admin_id = str(uuid.uuid4())
        print(f"\nCreating system admin user (ID: {admin_id})...")
        client.access_controller.create_user("admin_user", admin_id)
        client.access_controller.assign_role(admin_id, "admin")
        
        # Grant admin permissions
        client.access_controller.grant_permission(admin_id, "system", Permission.ADMIN)
        
        # Connect as admin
        print("\nConnecting to database as admin...")
        if not client.connect(username="admin_user"):
            print("Failed to connect to quantum database")
            return
        
        print("✓ Connected as admin")
        
        # Setup database
        print("\nSetting up database tables...")
        try:
            setup_database(client)
            print("✓ Database setup complete")
        except Exception as setup_error:
            print(f"! Database setup failed: {str(setup_error)}")
            # Continue with example even if setup fails
        
        # Run example queries
        print("\nRunning example queries...")
        run_example_queries(client)
        
    except Exception as e:
        print(f"\n! Error: {str(e)}")
    finally:
        if client:
            client.disconnect()
            print("\nConnection closed")
        # Restore logging level
        logging.getLogger().setLevel(logging_level)
        print("\nExample completed")

def setup_database(client):
    """Initialize database tables with proper permissions."""
    # Get the current user ID from the connection
    user_id = None
    if hasattr(client, 'connection') and hasattr(client.connection, 'user_id'):
        username = client.connection.user_id
        user = client.access_controller.get_user_by_username(username)
        if user:
            user_id = user.user_id
    
    if not user_id:
        # If we can't get the connected user ID, get it from the users dictionary
        users = getattr(client.access_controller, 'users', {})
        if users:
            user_id = list(users.keys())[-1]  # Get most recent user
    
    if not user_id:
        raise ValueError("Could not determine user ID for permissions")
    
    # Define tables
    tables = {
        "customers": """
        CREATE TABLE customers (
            customer_id INT,
            customer_name TEXT,
            email TEXT,
            signup_date TEXT
        )
        """,
        "orders": """
        CREATE TABLE orders (
            order_id INT,
            customer_id INT,
            order_date TEXT,
            amount FLOAT
        )
        """,
        "customer_behaviors": """
        CREATE TABLE customer_behaviors (
            customer_id INT,
            first_purchase_date TEXT,
            purchase_vector TEXT,
            visit_frequency FLOAT
        )
        """
    }
    
    # Create tables and register resources
    for table_name, create_stmt in tables.items():
        print(f"Creating {table_name} table...")
        result = client.execute_query(create_stmt)
        if not result.get("success"):
            print(f"! Warning: Failed to create {table_name}: {result.get('error', 'Unknown error')}")
            continue
        
        # Register resource and grant permissions
        try:
            client.access_controller.create_resource(
                table_name,
                f"{table_name.capitalize()} Table",
                ResourceType.TABLE,
                user_id
            )
        except Exception as e:
            print(f"! Warning: Resource registration failed: {str(e)}")
        
        # Grant permissions
        for perm in [Permission.READ, Permission.WRITE, Permission.CREATE, Permission.EXECUTE]:
            try:
                client.access_controller.grant_permission(user_id, table_name, perm)
            except Exception as e:
                print(f"! Warning: Permission grant failed: {str(e)}")
    
    # Populate sample data
    print("Populating sample data...")
    populate_sample_data(client)

def populate_sample_data(client):
    """Insert sample data into tables."""
    # Insert customers
    for i in range(1, 6):  # Reduced to 5 customers for quicker execution
        query = f"""
        INSERT INTO customers (customer_id, customer_name, email, signup_date)
        VALUES ({i}, 'Customer {i}', 'customer{i}@example.com', 
               '2023-0{i}-01')
        """
        result = client.execute_query(query)
        if not result.get("success"):
            print(f"! Warning: Failed to insert customer {i}: {result.get('error', 'Unknown error')}")
    
    # Insert orders
    for i in range(1, 11):  # Reduced to 10 orders
        customer_id = (i % 5) + 1  # Distribute among 5 customers
        query = f"""
        INSERT INTO orders (order_id, customer_id, order_date, amount)
        VALUES ({i}, {customer_id}, 
               '2023-0{i % 9 + 1}-15',
               {(i * 250) + 100}.50)
        """
        result = client.execute_query(query)
        if not result.get("success"):
            print(f"! Warning: Failed to insert order {i}: {result.get('error', 'Unknown error')}")
    
    # Insert behaviors - simplified
    for i in range(1, 6):  # 5 customer behaviors
        vector_str = ",".join([f"{(i * 0.1 + j * 0.05):.2f}" for j in range(4)])
        query = f"""
        INSERT INTO customer_behaviors (customer_id, first_purchase_date, 
                                      purchase_vector, visit_frequency)
        VALUES ({i}, '2023-0{i}-01',
               '{vector_str}', 
               {i * 1.5})
        """
        result = client.execute_query(query)
        if not result.get("success"):
            print(f"! Warning: Failed to insert behavior {i}: {result.get('error', 'Unknown error')}")

def run_example_queries(client):
    """Execute and demonstrate example queries."""
    # Example 1: Basic JOIN query (instead of Quantum Join)
    print("\n--- Example 1: Join Query ---")
    query = """
    SELECT * FROM customers
    WHERE customer_id = 1
    """
    execute_and_display_query(client, query, "Basic Customer Query")
    
    # Example 2: Basic aggregation
    print("\n--- Example 2: Order Query ---")
    query = """
    SELECT * FROM orders
    WHERE customer_id = 1
    """
    execute_and_display_query(client, query, "Customer Orders Query")
    
    # Example 3: Retrieving customer behavior data
    print("\n--- Example 3: Customer Behavior Data ---")
    query = """
    SELECT * FROM customer_behaviors
    """
    execute_and_display_query(client, query, "Customer Behavior Query")
    
    # Example 4: Simple count query 
    print("\n--- Example 4: Count Query ---")
    query = """
    SELECT COUNT(*) FROM orders
    """
    execute_and_display_query(client, query, "Count Query")
    
    # Additional example with more filtering
    print("\n--- Example 5: Filtered Orders ---")
    query = """
    SELECT * FROM orders
    WHERE amount > 500
    """
    execute_and_display_query(client, query, "High-Value Orders")

def execute_and_display_query(client, query, description):
    """Execute query and display results."""
    print(f"Executing: {description}")
    print(f"Query: {query.strip()}")
    
    result = client.execute_query(query)
    
    if result.get("success"):
        rows = result.get("rows", [])
        if rows:
            print("\nResults:")
            for i, row in enumerate(rows[:10]):  # Show up to 10 rows
                print(f"  {row}")
            if len(rows) > 10:
                print(f"  ... and {len(rows) - 10} more records")
        else:
            print("✓ Operation completed successfully (no data returned)")
    else:
        print(f"✗ Query failed: {result.get('error', 'Unknown error')}")
    
    # Display transaction ID for tracking
    if 'transaction_id' in result:
        print(f"Transaction ID: {result['transaction_id']}")
    
    print("-" * 50)

if __name__ == "__main__":
    run_complex_queries_example()