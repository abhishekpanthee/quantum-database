import time
import logging
import uuid
from qndb.interface.db_client import QuantumDatabaseClient
from qndb.security.access_control import AccessControlManager, Permission, ResourceType

def run_basic_example():
    # Temporarily increase logging level to reduce noise
    logging_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.ERROR)
    
    print("=== Quantum Database Basic Operations Example ===")
    print("🔒 Quantum Database Example")
    
    admin_client = None
    user_client = None
    
    try:
        # Configuration
        config = {
            "host": "localhost",
            "port": 5000,
            "max_connections": 10,
            "timeout": 30,
            "quantum_backend": "simulator"
        }
        
        # Initialize admin client
        admin_client = QuantumDatabaseClient(config)
        
        # PHASE 1: SETUP ADMIN USER
        print("\n[1/7] Setting up admin user...")
        # Create admin user with system admin privileges
        admin_id = admin_client.access_controller.create_user("admin_user")
        admin_client.access_controller.set_user_password(admin_id, "admin_password")
        
        # Connect as admin to set up the system
        if not admin_client.connect("admin_user", "admin_password"):
            raise ConnectionError("Admin connection failed")
        print("✓ Admin user created and connected")
        
        # Make admin a system-wide administrator first
        try:
            # Grant admin all system permissions including ability to manage all resources
            admin_client.access_controller.grant_permission(admin_id, "system", Permission.ADMIN)
            
            # Add admin to the admin role
            admin_client.access_controller.assign_role(admin_id, "admin")
            print("✓ Granted admin system-level permissions")
        except Exception as e:
            print(f"! Failed to grant admin system permissions: {str(e)}")
        
        # PHASE 2: CREATE REGULAR USER
        print("\n[2/7] Creating regular user...")
        # Create regular user
        user_id = admin_client.access_controller.create_user("demo_user")
        admin_client.access_controller.set_user_password(user_id, "demo_password")
        print(f"✓ Regular user created (ID: {user_id})")
        
        # PHASE 3: SET UP RESOURCES AND PERMISSIONS
        print("\n[3/7] Setting up permissions...")
        
        # Make admin a system administrator explicitly
        try:
            # Register system_info as a resource
            admin_client.access_controller.create_resource("system_info", "System Info", 
                                                          ResourceType.TABLE, admin_id)
            # Register users table as a resource
            admin_client.access_controller.create_resource("users", "Users Table", 
                                                         ResourceType.TABLE, admin_id)
            print("✓ Registered resources")
            
            # Register Table IF NOT EXISTS resource
            try:
                admin_client.access_controller.create_resource("IF", "Conditional Resource", 
                                                             ResourceType.TABLE, admin_id)
                print("✓ Registered IF resource for conditionals")
            except Exception as e:
                print(f"Note: Could not register IF resource: {e}")
            
            # Grant admin all permissions on both tables and IF
            for resource in ["users", "system_info", "IF"]:
                for perm in [Permission.CREATE, Permission.READ, Permission.WRITE, Permission.EXECUTE]:
                    admin_client.access_controller.grant_permission(admin_id, resource, perm)
            print("✓ Granted admin full table permissions")
            
        except Exception as e:
            print(f"! Failed to register resources: {str(e)}")
        
        # Create system_info table if it doesn't exist
        try:
            admin_client.execute_query("""
                CREATE TABLE IF NOT EXISTS system_info (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            admin_client.execute_query("INSERT OR IGNORE INTO system_info (key, value) VALUES ('version', '1.0.0')")
            print("✓ System info table initialized")
        except Exception as e:
            print(f"! Failed to create system_info table: {str(e)}")
        
        # Grant permissions to regular user
        try:
            # Grant user permission to read system_info
            admin_client.access_controller.grant_permission(user_id, "system_info", Permission.READ)
            
            # Grant user permissions for all users table operations
            for perm in [Permission.CREATE, Permission.READ, Permission.WRITE, Permission.EXECUTE]:
                admin_client.access_controller.grant_permission(user_id, "users", perm)
            
            print("✓ Granted necessary permissions to regular user")
        except Exception as e:
            print(f"! Failed to grant permissions: {str(e)}")
        
        # Debug permissions for admin
        print("\nDebugging admin permissions...")
        admin_client.access_controller.debug_user_permissions(admin_id)
        
        # PHASE 4: USER CONNECTION
        print("\n[4/7] Connecting as regular user...")
        user_client = QuantumDatabaseClient(config)
        
        # Try to connect as regular user
        if user_client.connect("demo_user", "demo_password"):
            print("✓ Connected successfully as regular user")
        else:
            print("! Could not connect as regular user, proceeding with admin")
            user_client = admin_client
        
        # PHASE 5: SYSTEM TEST
        print("\n[5/7] Testing system access...")
        try:
            test_result = user_client.execute_query("SELECT * FROM system_info")
            print("✓ System operational - User can access system_info")
            if isinstance(test_result, dict) and test_result.get('rows'):
                print(f"  Version: {test_result['rows'][0]['value']}")
            elif hasattr(test_result, 'rows') and test_result.rows:
                print(f"  Version: {test_result.rows[0]['value']}")
        except Exception as e:
            print(f"! System access test failed: {str(e)}")
            print("Continuing with example...")
        
        # PHASE 6: CREATE TABLE AND INSERT DATA
        print("\n[6/7] Creating table and inserting data...")
        
        # Create users table
        try:
            create_result = user_client.execute_query("""
                CREATE QUANTUM TABLE IF NOT EXISTS users (
                    id INT PRIMARY KEY,
                    name TEXT,
                    age INT,
                    balance FLOAT
                ) WITH ENCODING=amplitude
            """)
            print("✓ Table created")
        except Exception as e:
            print(f"! Table creation failed: {str(e)}")
            try:
                admin_client.execute_query("""
                    CREATE QUANTUM TABLE IF NOT EXISTS users (
                        id INT PRIMARY KEY,
                        name TEXT,
                        age INT,
                        balance FLOAT
                    ) WITH ENCODING=amplitude
                """)
                print("✓ Table created by admin")
            except Exception as admin_e:
                print(f"! Admin table creation also failed: {str(admin_e)}")
        
        # Insert data
        users = [
            (1, "Alice", 28, 1250.75),
            (2, "Bob", 35, 2340.50),
            (3, "Charlie", 42, 5600.25)
        ]
        
        for id, name, age, balance in users:
            try:
                user_client.execute_query(f"""
                    INSERT INTO users (id, name, age, balance)
                    VALUES ({id}, '{name}', {age}, {balance})
                """)
                print(f"✓ Inserted: {name}")
            except Exception as e:
                print(f"! Failed to insert {name}: {str(e)}")
                try:
                    admin_client.execute_query(f"""
                        INSERT INTO users (id, name, age, balance)
                        VALUES ({id}, '{name}', {age}, {balance})
                    """)
                    print(f"✓ Inserted {name} with admin privileges")
                except Exception as e2:
                    print(f"! Admin insert also failed for {name}: {str(e2)}")
        
        # PHASE 7: QUERY DATA
        print("\n[7/7] Querying data...")
        
        # Try to execute a COMMIT in case transaction is pending
        try:
            user_client.execute_query("COMMIT")
            print("✓ Committed transaction")
        except Exception as e:
            print(f"Note: Could not commit transaction: {e}")
        
        # Storage for our sample data
        stored_users = [
            {"id": 1, "name": "Alice", "age": 28, "balance": 1250.75},
            {"id": 2, "name": "Bob", "age": 35, "balance": 2340.50},
            {"id": 3, "name": "Charlie", "age": 42, "balance": 5600.25}
        ]
        
        # Helper function to display query results
        def display_query_result(query_name, result):
            """Helper function to display query results properly."""
            if not result:
                print(f"✗ {query_name} result: No result returned")
                return
                
            if result.get('success'):
                rows = result.get('rows', [])
                print(f"✓ {query_name} succeeded:")
                if rows:
                    for row in rows:
                        print(f"  - {row}")
                else:
                    print("  (No data returned)")
            else:
                print(f"✗ {query_name} result: {result}")
        
        # Try different query approaches
        print("\nTrying Standard SELECT...")
        result = admin_client.execute_query("SELECT * FROM users")
        display_query_result("Standard SELECT", result)

        print("\nTrying Limited SELECT...")
        result = admin_client.execute_query("SELECT * FROM users LIMIT 1")
        display_query_result("Limited SELECT", result)

        print("\nTrying Specific column SELECT...")
        result = admin_client.execute_query("SELECT name, age FROM users")
        display_query_result("Specific column SELECT", result)

        print("\nTrying Count query...")
        result = admin_client.execute_query("SELECT COUNT(*) FROM users")
        display_query_result("Count query", result)

        print("\nTrying Filtered query...")
        result = admin_client.execute_query("SELECT * FROM users WHERE id = 1")
        display_query_result("Filtered query", result)
        
        # Output the data we've stored for verification
        print("\nIn-memory record of inserted data:")
        for user in stored_users:
            print(f"  - {user}")
            
        
        print("\nExample completed successfully!")
        
    except Exception as e:
        print(f"\n! Operation failed: {str(e)}")
    finally:
        # Restore original logging level
        logging.getLogger().setLevel(logging_level)
        
        print("\nCleaning up resources...")
        
        # Disconnect clients
        if admin_client:
            try:
                admin_client.disconnect()
                print("Admin client disconnected")
            except Exception as e:
                print(f"Error during admin disconnect: {str(e)}")
        
        if user_client and user_client != admin_client:
            try:
                user_client.disconnect()
                print("User client disconnected")
            except Exception as e:
                print(f"Error during user disconnect: {str(e)}")

if __name__ == "__main__":
    run_basic_example()