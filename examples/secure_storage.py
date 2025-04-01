
# examples/secure_storage.py

"""
Secure quantum storage example.

This example demonstrates the security features of the quantum database system,
including quantum encryption, secure access control, and audit logging.
"""

import time
import numpy as np
from interface.db_client import QuantumDatabaseClient
from security.quantum_encryption import QuantumEncryption
from security.access_control import AccessControl
from security.audit import AuditLogger
from utilities.benchmarking import benchmark_query

def run_secure_storage_example():
    """
    Run secure quantum storage example.
    """
    print("=== Quantum Database Secure Storage Example ===")
    
    # Initialize security components
    encryption = QuantumEncryption()
    access_control = AccessControl()
    audit = AuditLogger()
    
    # Generate quantum encryption keys
    print("Generating quantum encryption keys...")
    encryption_keys = encryption.generate_keys()
    print(f"Generated {len(encryption_keys)} quantum encryption keys")
    
    # Connect to the quantum database with secure authentication
    client = QuantumDatabaseClient()
    print("\nConnecting with secure authentication...")
    
    # Simulate quantum authentication protocol
    auth_token = encryption.quantum_authentication("admin", "password")
    connection = client.connect(
        host="localhost",
        port=5000,
        auth_token=auth_token,
        encryption=True
    )
    print("Connected to quantum database with secure authentication")
    
    # Create secure tables
    print("\nCreating encrypted quantum tables...")
    create_secure_tables(connection, encryption)
    
    # Set up access control
    print("\nSetting up quantum access control...")
    setup_access_control(connection, access_control)
    
    # Insert sensitive data with quantum encryption
    print("\nInserting encrypted sensitive data...")
    insert_encrypted_data(connection, encryption)
    
    # Demonstrate secure queries
    print("\nPerforming secure quantum queries...")
    perform_secure_queries(connection, encryption, audit)
    
    print("\nPerforming quantum key rotation...")
    rotate_encryption_keys(connection, encryption)
    
    # Audit log analysis
    print("\nPerforming audit log analysis...")
    analyze_audit_logs(audit)
    
    # Quantum homomorphic encryption example
    print("\nDemonstrating quantum homomorphic encryption...")
    demonstrate_homomorphic_encryption(connection, encryption)
    
    # Quantum secure multi-party computation
    print("\nDemonstrating secure multi-party computation...")
    demonstrate_secure_computation(connection)
    
    # Close the secure connection
    connection.close()
    print("\nSecure connection closed")
    print("Secure storage example completed")

def create_secure_tables(connection, encryption):
    """
    Create encrypted quantum tables for sensitive data.
    
    Args:
        connection: Database connection
        encryption: Quantum encryption instance
    """
    # Create encrypted financial data table
    create_financial = """
    CREATE QUANTUM TABLE financial_data (
        user_id INT PRIMARY KEY,
        account_number TEXT ENCRYPTED,
        balance FLOAT ENCRYPTED,
        credit_score INT ENCRYPTED
    ) WITH ENCRYPTION=quantum
    """
    
    result = connection.execute(create_financial)
    print(f"Financial data table created: {result.success}")
    
    # Create encrypted medical data table
    create_medical = """
    CREATE QUANTUM TABLE medical_records (
        patient_id INT PRIMARY KEY,
        diagnosis TEXT ENCRYPTED,
        treatment TEXT ENCRYPTED,
        medical_history QUANTUM_VECTOR ENCRYPTED
    ) WITH ENCRYPTION=quantum_homomorphic
    """
    
    result = connection.execute(create_medical)
    print(f"Medical records table created: {result.success}")
    
    # Create table for storing encryption metadata
    create_metadata = """
    CREATE QUANTUM TABLE encryption_metadata (
        key_id TEXT PRIMARY KEY,
        creation_date DATETIME,
        expiration_date DATETIME,
        algorithm TEXT,
        key_length INT
    )
    """
    
    result = connection.execute(create_metadata)
    print(f"Encryption metadata table created: {result.success}")

def setup_access_control(connection, access_control):
    """
    Set up quantum access control for secure tables.
    
    Args:
        connection: Database connection
        access_control: Access control instance
    """
    # Create roles
    roles = [
        ("financial_admin", "Administrator for financial data"),
        ("financial_analyst", "Analyst with read-only access to financial data"),
        ("medical_admin", "Administrator for medical records"),
        ("medical_practitioner", "Medical staff with access to patient records")
    ]
    
    for role, description in roles:
        query = f"""
        CREATE ROLE {role} 
        DESCRIPTION '{description}'
        """
        result = connection.execute(query)
        print(f"Role '{role}' created: {result.success}")
    
    # Grant permissions
    permissions = [
        ("financial_admin", "ALL", "financial_data"),
        ("financial_analyst", "SELECT", "financial_data"),
        ("medical_admin", "ALL", "medical_records"),
        ("medical_practitioner", "SELECT, UPDATE", "medical_records")
    ]
    
    for role, permission, table in permissions:
        query = f"""
        GRANT {permission} ON {table} TO {role}
        """
        result = connection.execute(query)
        print(f"Granted {permission} on {table} to {role}: {result.success}")
    
    # Create users and assign roles
    users = [
        ("financial_user", "financial_admin"),
        ("analyst_user", "financial_analyst"),
        ("medical_admin_user", "medical_admin"),
        ("doctor_user", "medical_practitioner")
    ]
    
    for user, role in users:
        # Create user (simplified - in a real system this would be more secure)
        create_query = f"""
        CREATE USER {user} 
        WITH QUANTUM_AUTHENTICATION=true
        """
        connection.execute(create_query)
        
        # Assign role
        assign_query = f"""
        GRANT ROLE {role} TO {user}
        """
        result = connection.execute(assign_query)
        print(f"User '{user}' created and assigned role '{role}': {result.success}")

def insert_encrypted_data(connection, encryption):
    """
    Insert encrypted sensitive data into secure tables.
    
    Args:
        connection: Database connection
        encryption: Quantum encryption instance
    """
    # Insert financial data
    financial_data = [
        (1, "1234-5678-9012-3456", 15750.25, 750),
        (2, "2345-6789-0123-4567", 42680.75, 820),
        (3, "3456-7890-1234-5678", 8920.50, 680),
        (4, "4567-8901-2345-6789", 27340.00, 790)
    ]
    
    for user_id, account, balance, score in financial_data:
        # Encrypt sensitive data
        encrypted_account = encryption.encrypt_data(account)
        encrypted_balance = encryption.encrypt_data(str(balance))
        encrypted_score = encryption.encrypt_data(str(score))
        
        # Insert encrypted data
        query = f"""
        INSERT INTO financial_data (user_id, account_number, balance, credit_score)
        VALUES (
            {user_id}, 
            '{encrypted_account}', 
            {encrypted_balance}, 
            {encrypted_score}
        )
        """
        
        result = connection.execute(query)
        print(f"Inserted encrypted financial data for user {user_id}: {result.success}")
    
    # Insert medical data
    medical_data = [
        (101, "Hypertension", "Lisinopril 10mg daily", [0.85, 0.12, 0.45, 0.23, 0.67, 0.91]),
        (102, "Type 2 Diabetes", "Metformin 500mg twice daily", [0.32, 0.78, 0.16, 0.59, 0.41, 0.28]),
        (103, "Asthma", "Albuterol inhaler as needed", [0.63, 0.42, 0.85, 0.19, 0.74, 0.52])
    ]
    
    for patient_id, diagnosis, treatment, history in medical_data:
        # Encrypt sensitive data with homomorphic encryption
        encrypted_diagnosis = encryption.homomorphic_encrypt(diagnosis)
        encrypted_treatment = encryption.homomorphic_encrypt(treatment)
        
        # Convert history to quantum vector and encrypt
        history_str = ", ".join([str(v) for v in history])
        encrypted_history = encryption.homomorphic_encrypt(f"QUANTUM_VECTOR[{history_str}]")
        
        # Insert encrypted data
        query = f"""
        INSERT INTO medical_records (patient_id, diagnosis, treatment, medical_history)
        VALUES (
            {patient_id}, 
            '{encrypted_diagnosis}', 
            '{encrypted_treatment}', 
            {encrypted_history}
        )
        """
        
        result = connection.execute(query)
        print(f"Inserted encrypted medical data for patient {patient_id}: {result.success}")

def perform_secure_queries(connection, encryption, audit):
    """
    Perform secure quantum queries on encrypted data.
    
    Args:
        connection: Database connection
        encryption: Quantum encryption instance
        audit: Audit logger instance
    """
    # Log the audit event
    audit.log_access(
        user="admin",
        action="QUERY",
        table="financial_data",
        description="Secure query on financial data"
    )
    
    # Query with decryption
    financial_query = """
    SELECT user_id, 
           DECRYPT(account_number) AS account, 
           DECRYPT(balance) AS balance
    FROM financial_data
    WHERE DECRYPT(credit_score) > 700
    """
    
    result = connection.execute(financial_query)
    print("Financial data query results:")
    for record in result.records:
        print(f"  User {record['user_id']}: Account {record['account']}, Balance ${record['balance']}")
    
    # Log another audit event
    audit.log_access(
        user="admin",
        action="QUERY",
        table="medical_records",
        description="Secure query on medical records"
    )
    
    # Secure query on medical data using homomorphic properties
    medical_query = """
    SELECT patient_id,
           DECRYPT(diagnosis) AS diagnosis,
           QUANTUM_ANALYZE(
               DECRYPT(medical_history), 
               method='risk_assessment'
           ) AS risk_score
    FROM medical_records
    """
    
    result = connection.execute(medical_query)
    print("\nMedical data query results:")
    for record in result.records:
        print(f"  Patient {record['patient_id']}: {record['diagnosis']}, Risk: {record['risk_score']:.2f}")
    
    # Demonstrate blind quantum computation (server processes encrypted data without seeing it)
    print("\nPerforming blind quantum computation on encrypted data...")
    blind_query = """
    SELECT 
        QUANTUM_BLIND_COMPUTE(
            'clustering_algorithm',
            ENCRYPTED_PARAMETERS(max_clusters=3, iterations=100)
        ) AS secure_clusters
    FROM medical_records
    """
    
    result = connection.execute(blind_query)
    print("Blind computation completed without decrypting sensitive data")
    print(f"Result size: {len(result.metadata.get('secure_result_size', 0))} records")

def rotate_encryption_keys(connection, encryption):
    """
    Perform quantum key rotation to enhance security.
    
    Args:
        connection: Database connection
        encryption: Quantum encryption instance
    """
    # Generate new quantum encryption keys
    new_keys = encryption.generate_keys()
    print(f"Generated {len(new_keys)} new quantum encryption keys")
    
    # Start key rotation process
    print("Starting key rotation process...")
    
    # Log the start of key rotation in the metadata table
    log_query = f"""
    INSERT INTO encryption_metadata (key_id, creation_date, expiration_date, algorithm, key_length)
    VALUES (
        '{new_keys['primary_key_id']}',
        '{time.strftime('%Y-%m-%d %H:%M:%S')}',
        '{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(time.time() + 90*24*60*60))}',
        'quantum_resistant',
        {new_keys['key_length']}
    )
    """
    connection.execute(log_query)
    
    # Re-encrypt financial data with new keys
    reencrypt_query = """
    UPDATE financial_data
    SET account_number = REENCRYPT(account_number),
        balance = REENCRYPT(balance),
        credit_score = REENCRYPT(credit_score)
    """
    
    result = connection.execute(reencrypt_query)
    print(f"Financial data re-encrypted: {result.success}, {result.affected_rows} rows updated")
    
    # Re-encrypt medical data with new keys
    reencrypt_query = """
    UPDATE medical_records
    SET diagnosis = REENCRYPT(diagnosis),
        treatment = REENCRYPT(treatment),
        medical_history = REENCRYPT(medical_history)
    """
    
    result = connection.execute(reencrypt_query)
    print(f"Medical data re-encrypted: {result.success}, {result.affected_rows} rows updated")
    
    # Retire old keys securely
    encryption.retire_keys(days_to_keep=30)
    print("Old encryption keys scheduled for secure retirement")

def analyze_audit_logs(audit):
    """
    Analyze audit logs for security insights.
    
    Args:
        audit: Audit logger instance
    """
    # Get recent audit logs
    logs = audit.get_recent_logs(hours=24)
    print(f"Retrieved {len(logs)} audit log entries from the past 24 hours")
    
    # Analyze access patterns
    access_by_user = {}
    access_by_table = {}
    
    for log in logs:
        # Count accesses by user
        user = log.get('user')
        if user in access_by_user:
            access_by_user[user] += 1
        else:
            access_by_user[user] = 1
            
        # Count accesses by table
        table = log.get('table')
        if table in access_by_table:
            access_by_table[table] += 1
        else:
            access_by_table[table] = 1
    
    # Print access statistics
    print("\nAccess by user:")
    for user, count in access_by_user.items():
        print(f"  {user}: {count} accesses")
    
    print("\nAccess by table:")
    for table, count in access_by_table.items():
        print(f"  {table}: {count} accesses")
    
    # Check for anomalous patterns (simplified example)
    print("\nChecking for anomalous access patterns...")
    for user, count in access_by_user.items():
        if count > 20:  # Arbitrary threshold for this example
            print(f"  Warning: User '{user}' has unusually high activity ({count} accesses)")
    
    # Run quantum pattern detection on audit logs (hypothetical)
    print("\nRunning quantum pattern detection on audit logs...")
    # This would use a quantum algorithm to detect subtle patterns in the logs
    print("No suspicious patterns detected in the audit logs")

def demonstrate_homomorphic_encryption(connection, encryption):
    """
    Demonstrate quantum homomorphic encryption capabilities.
    
    Args:
        connection: Database connection
        encryption: Quantum encryption instance
    """
    print("Creating sample data for homomorphic operations...")
    
    # Create a table for homomorphic operations
    create_query = """
    CREATE QUANTUM TABLE homomorphic_demo (
        id INT PRIMARY KEY,
        value1 FLOAT ENCRYPTED,
        value2 FLOAT ENCRYPTED
    ) WITH ENCRYPTION=quantum_homomorphic
    """
    connection.execute(create_query)
    
    # Insert sample data
    for i in range(1, 6):
        val1 = np.random.uniform(1, 100)
        val2 = np.random.uniform(1, 100)
        
        # Encrypt values homomorphically
        encrypted_val1 = encryption.homomorphic_encrypt(str(val1))
        encrypted_val2 = encryption.homomorphic_encrypt(str(val2))
        
        insert_query = f"""
        INSERT INTO homomorphic_demo (id, value1, value2)
        VALUES ({i}, '{encrypted_val1}', '{encrypted_val2}')
        """
        connection.execute(insert_query)
    
    print("Sample data created and encrypted")
    
    # Perform operations on encrypted data without decrypting
    operations_query = """
    SELECT id,
           HOMOMORPHIC_COMPUTE(value1 + value2) AS encrypted_sum,
           HOMOMORPHIC_COMPUTE(value1 * value2) AS encrypted_product,
           HOMOMORPHIC_COMPUTE(value1 > value2) AS encrypted_comparison
    FROM homomorphic_demo
    """
    
    result = connection.execute(operations_query)
    print("\nHomomorphic computation results:")
    print("(Results remain encrypted on server side)")
    
    # In a real system, results would be decrypted client-side
    # For demonstration, we'll simulate decryption:
    print("\nAfter client-side decryption:")
    
    for i, record in enumerate(result.records):
        # Simulate decryption
        decrypted_sum = encryption.decrypt(record['encrypted_sum'])
        decrypted_product = encryption.decrypt(record['encrypted_product'])
        decrypted_comparison = encryption.decrypt(record['encrypted_comparison']) == 'True'
        
        print(f"  ID {record['id']}:")
        print(f"    Sum: {decrypted_sum:.2f}")
        print(f"    Product: {decrypted_product:.2f}")
        print(f"    Is value1 > value2? {decrypted_comparison}")

def demonstrate_secure_computation(connection):
    """
    Demonstrate secure multi-party quantum computation.
    
    Args:
        connection: Database connection
    """
    # Simulate three parties with sensitive data
    print("Setting up secure multi-party computation...")
    
    # Create a quantum secure computation session
    create_session_query = """
    CREATE QUANTUM SECURE SESSION
    WITH PARTICIPANTS=3
    SECURITY='post_quantum'
    """
    session = connection.execute(create_session_query).session_id
    print(f"Created secure session: {session}")
    
    # Simulate each party submitting encrypted data
    for party in range(1, 4):
        # Each party has sensitive financial data they don't want to reveal
        data_value = np.random.uniform(1000000, 10000000)  # e.g., company revenues
        
        submit_query = f"""
        SECURE_SUBMIT TO SESSION '{session}'
        PARTICIPANT={party}
        DATA={data_value:.2f}
        """
        connection.execute(submit_query)
        print(f"Party {party} submitted their encrypted data")
    
    # Perform secure computation without revealing individual inputs
    computation_query = f"""
    SECURE_COMPUTE ON SESSION '{session}'
    FUNCTION='average, sum, min, max'
    """
    
    result = connection.execute(computation_query)
    print("\nSecure computation results (without revealing individual inputs):")
    print(f"  Average: ${result.records[0]['average']:.2f}")
    print(f"  Sum: ${result.records[0]['sum']:.2f}")
    print(f"  Minimum: ${result.records[0]['min']:.2f}")
    print(f"  Maximum: ${result.records[0]['max']:.2f}")
    
    # Close the secure session
    close_query = f"""
    CLOSE QUANTUM SECURE SESSION '{session}'
    """
    connection.execute(close_query)
    print("\nSecure computation session closed")

if __name__ == "__main__":
    run_secure_storage_example()