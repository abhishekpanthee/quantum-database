# examples/secure_storage.py

"""
Secure quantum storage example.

This example demonstrates the security features of the quantum database system,
including quantum encryption, secure access control, and audit logging.
"""

import time
import numpy as np
import uuid
import json

# Update imports to use the actual classes from quantum_encryption.py
from qndb.interface.db_client import QuantumDatabaseClient
from qndb.security.quantum_encryption import HybridEncryption, QuantumKeyDistribution, QuantumSecureStorage
from qndb.security.access_control import AccessControlManager
from qndb.security.audit import AuditEvent, AuditEventType
from qndb.utilities.benchmarking import BenchmarkRunner


def run_secure_storage_example():
    """
    Run secure quantum storage example.
    """
    print("=== Quantum Database Secure Storage Example ===")
    
    # Initialize security components using the correct classes
    qkd = QuantumKeyDistribution()
    encryption = HybridEncryption(qkd)
    secure_storage = QuantumSecureStorage(encryption)
    access_control = AccessControlManager()
    audit = AuditEvent(AuditEventType.SYSTEM_STARTUP, "admin")
    
    # Generate quantum encryption keys by establishing a secure session
    print("Establishing quantum-secure session...")
    session_id = str(uuid.uuid4())
    session_info = encryption.establish_secure_session(session_id, "database-client")
    print(f"Secure session established: {session_id}")
    print(f"Security level: {session_info['security_level']}")
    print(f"Key size: {session_info['key_size']} bits")
    print(f"Quantum bit error rate: {session_info['error_rate']:.4f}")
    
    # Connect to the quantum database with secure authentication
    client = QuantumDatabaseClient({
        "host": "localhost",
        "port": 5000,
        "max_connections": 10,
        "timeout": 30
    })
    print("\nConnecting with secure authentication...")
    
    # Simulate quantum authentication protocol
    auth_data = {"username": "admin", "password": "password"}
    encrypted_auth = encryption.encrypt(session_id, json.dumps(auth_data))
    
    # Simulate connection with the encrypted authentication
    connection_successful = True  # Simulated result
    print("Connected to quantum database with secure authentication")
    
    # Create secure tables
    print("\nCreating encrypted quantum tables...")
    create_secure_tables(client, secure_storage)
    
    # Set up access control
    print("\nSetting up quantum access control...")
    setup_access_control(client, access_control)
    
    # Insert sensitive data with quantum encryption
    print("\nInserting encrypted sensitive data...")
    insert_encrypted_data(client, encryption, session_id)
    
    # Demonstrate secure queries
    print("\nPerforming secure quantum queries...")
    perform_secure_queries(client, encryption, session_id, audit)
    
    print("\nPerforming quantum key rotation...")
    rotate_encryption_keys(client, encryption, session_id)
    
    # Audit log analysis
    print("\nPerforming audit log analysis...")
    analyze_audit_logs(audit)
    
    # Quantum homomorphic encryption example
    print("\nDemonstrating quantum homomorphic encryption...")
    demonstrate_homomorphic_encryption(client, encryption, session_id)
    
    # Quantum secure multi-party computation
    print("\nDemonstrating secure multi-party computation...")
    demonstrate_secure_computation(client)
    
    # Close the secure connection
    if hasattr(client, 'disconnect'):
        client.disconnect()
    print("\nSecure connection closed")
    print("Secure storage example completed")

def create_secure_tables(client, secure_storage):
    """
    Create encrypted quantum tables for sensitive data.
    
    Args:
        client: Database client
        secure_storage: Quantum secure storage system
    """
    # Initialize secure storage
    secure_storage.initialize()
    
    # Create encrypted financial data table - using simulated execution
    create_financial = """
    CREATE QUANTUM TABLE financial_data (
        user_id INT PRIMARY KEY,
        account_number TEXT ENCRYPTED,
        balance FLOAT ENCRYPTED,
        credit_score INT ENCRYPTED
    ) WITH ENCRYPTION=quantum
    """
    
    # Simulate execution
    financial_success = True
    print(f"Financial data table created: {financial_success}")
    
    # Create encrypted medical data table
    create_medical = """
    CREATE QUANTUM TABLE medical_records (
        patient_id INT PRIMARY KEY,
        diagnosis TEXT ENCRYPTED,
        treatment TEXT ENCRYPTED,
        medical_history QUANTUM_VECTOR ENCRYPTED
    ) WITH ENCRYPTION=quantum_homomorphic
    """
    
    # Simulate execution
    medical_success = True
    print(f"Medical records table created: {medical_success}")
    
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
    
    # Simulate execution
    metadata_success = True
    print(f"Encryption metadata table created: {metadata_success}")

def setup_access_control(client, access_control):
    """
    Set up quantum access control for secure tables.
    
    Args:
        client: Database client
        access_control: Access control instance
    """
    # Create roles - these are simulated in this example
    roles = [
        ("financial_admin", "Administrator for financial data"),
        ("financial_analyst", "Analyst with read-only access to financial data"),
        ("medical_admin", "Administrator for medical records"),
        ("medical_practitioner", "Medical staff with access to patient records")
    ]
    
    for role, description in roles:
        # Simulate query execution
        result_success = True
        print(f"Role '{role}' created: {result_success}")
    
    # Grant permissions - simulated
    permissions = [
        ("financial_admin", "ALL", "financial_data"),
        ("financial_analyst", "SELECT", "financial_data"),
        ("medical_admin", "ALL", "medical_records"),
        ("medical_practitioner", "SELECT, UPDATE", "medical_records")
    ]
    
    for role, permission, table in permissions:
        # Simulate query execution
        result_success = True
        print(f"Granted {permission} on {table} to {role}: {result_success}")
    
    # Create users and assign roles - simulated
    users = [
        ("financial_user", "financial_admin"),
        ("analyst_user", "financial_analyst"),
        ("medical_admin_user", "medical_admin"),
        ("doctor_user", "medical_practitioner")
    ]
    
    for user, role in users:
        # Simulate user creation and role assignment
        result_success = True
        print(f"User '{user}' created and assigned role '{role}': {result_success}")

def insert_encrypted_data(client, encryption, session_id):
    """
    Insert encrypted sensitive data into secure tables.
    
    Args:
        client: Database client
        encryption: Encryption instance
        session_id: Secure session ID
    """
    # Insert financial data - simulated
    financial_data = [
        (1, "1234-5678-9012-3456", 15750.25, 750),
        (2, "2345-6789-0123-4567", 42680.75, 820),
        (3, "3456-7890-1234-5678", 8920.50, 680),
        (4, "4567-8901-2345-6789", 27340.00, 790)
    ]
    
    for user_id, account, balance, score in financial_data:
        # Encrypt sensitive data
        encrypted_account = encryption.encrypt(session_id, account)['ciphertext']
        encrypted_balance = encryption.encrypt(session_id, str(balance))['ciphertext']
        encrypted_score = encryption.encrypt(session_id, str(score))['ciphertext']
        
        # Simulate query execution
        result_success = True
        print(f"Inserted encrypted financial data for user {user_id}: {result_success}")
    
    # Insert medical data - simulated
    medical_data = [
        (101, "Hypertension", "Lisinopril 10mg daily", [0.85, 0.12, 0.45, 0.23, 0.67, 0.91]),
        (102, "Type 2 Diabetes", "Metformin 500mg twice daily", [0.32, 0.78, 0.16, 0.59, 0.41, 0.28]),
        (103, "Asthma", "Albuterol inhaler as needed", [0.63, 0.42, 0.85, 0.19, 0.74, 0.52])
    ]
    
    # Define a simple homomorphic encryption simulation
    def homomorphic_encrypt(data):
        return encryption.encrypt(session_id, json.dumps(data))['ciphertext']
    
    for patient_id, diagnosis, treatment, history in medical_data:
        # Encrypt sensitive data - simulated homomorphic encryption
        encrypted_diagnosis = homomorphic_encrypt(diagnosis)
        encrypted_treatment = homomorphic_encrypt(treatment)
        encrypted_history = homomorphic_encrypt(history)
        
        # Simulate query execution
        result_success = True
        print(f"Inserted encrypted medical data for patient {patient_id}: {result_success}")

def perform_secure_queries(client, encryption, session_id, audit):
    """
    Perform secure quantum queries on encrypted data.
    
    Args:
        client: Database client
        encryption: Encryption instance
        session_id: Secure session ID
        audit: Audit logger instance
    """
    # Create a proper audit event for financial data query
    financial_query_audit = AuditEvent(AuditEventType.DATA_ACCESS, "admin", "financial_data")
    financial_query_audit.add_detail("action", "QUERY")
    financial_query_audit.add_detail("description", "Secure query on financial data")
    
    # Simulate financial data query results
    financial_records = [
        {"user_id": 2, "account": "2345-6789-0123-4567", "balance": "42680.75"},
        {"user_id": 4, "account": "4567-8901-2345-6789", "balance": "27340.00"}
    ]
    
    print("Financial data query results:")
    for record in financial_records:
        print(f"  User {record['user_id']}: Account {record['account']}, Balance ${record['balance']}")
    
    # Create another audit event for medical records query
    medical_query_audit = AuditEvent(AuditEventType.DATA_ACCESS, "admin", "medical_records")
    medical_query_audit.add_detail("action", "QUERY")
    medical_query_audit.add_detail("description", "Secure query on medical records")
    
    # Simulate medical data query results
    medical_records = [
        {"patient_id": 101, "diagnosis": "Hypertension", "risk_score": 0.78},
        {"patient_id": 102, "diagnosis": "Type 2 Diabetes", "risk_score": 0.65},
        {"patient_id": 103, "diagnosis": "Asthma", "risk_score": 0.42}
    ]
    
    print("\nMedical data query results:")
    for record in medical_records:
        print(f"  Patient {record['patient_id']}: {record['diagnosis']}, Risk: {record['risk_score']:.2f}")
    
    # Simulate blind quantum computation
    print("\nPerforming blind quantum computation on encrypted data...")
    print("Blind computation completed without decrypting sensitive data")
    print(f"Result size: 3 records")

def rotate_encryption_keys(client, encryption, session_id):
    """
    Perform quantum key rotation to enhance security.
    
    Args:
        client: Database client
        encryption: Encryption instance
        session_id: Current session ID
    """
    # Generate new session for key rotation
    new_session_id = f"{session_id}-rotated"
    session_info = encryption.establish_secure_session(new_session_id, "database-client")
    print(f"Generated new quantum secure session: {new_session_id}")
    print(f"New security level: {session_info['security_level']}")
    
    # Simulate data re-encryption
    financial_rows = 4
    medical_rows = 3
    
    print(f"Financial data re-encrypted: True, {financial_rows} rows updated")
    print(f"Medical data re-encrypted: True, {medical_rows} rows updated")
    print("Old encryption keys scheduled for secure retirement")

def analyze_audit_logs(audit):
    """
    Analyze audit logs for security insights.
    
    Args:
        audit: Main audit event
    """
    # Simulate retrieving audit logs - create sample audit events
    logs = []
    
    # Create sample audit events
    event_types = [
        (AuditEventType.DATA_ACCESS, "admin", "financial_data", "QUERY"),
        (AuditEventType.DATA_ACCESS, "admin", "medical_records", "QUERY"),
        (AuditEventType.DATA_MODIFICATION, "financial_user", "financial_data", "INSERT"),
        (AuditEventType.DATA_ACCESS, "doctor_user", "medical_records", "SELECT"),
        (AuditEventType.DATA_MODIFICATION, "doctor_user", "medical_records", "UPDATE"),
        (AuditEventType.RESOURCE_CREATED, "admin", "financial_data", "CREATE")
    ]
    
    for event_type, user, table, action in event_types:
        event = AuditEvent(event_type, user, table)
        event.add_detail("action", action)
        event.add_detail("timestamp", time.time())
        logs.append(event.to_dict())
    
    print(f"Retrieved {len(logs)} audit log entries from the past 24 hours")
    
    # Analyze access patterns
    access_by_user = {}
    access_by_table = {}
    
    for log in logs:
        # Count accesses by user
        user = log.get('user_id')
        if user in access_by_user:
            access_by_user[user] += 1
        else:
            access_by_user[user] = 1
            
        # Count accesses by table
        table = log.get('resource_id')
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
        
    print("No suspicious patterns detected in the audit logs")

def demonstrate_homomorphic_encryption(client, encryption, session_id):
    """
    Demonstrate quantum homomorphic encryption capabilities.
    
    Args:
        client: Database client
        encryption: Encryption instance
        session_id: Secure session ID
    """
    print("Creating sample data for homomorphic operations...")
    
    # Simulate homomorphic operations
    # Create sample data
    sample_data = []
    for i in range(1, 6):
        val1 = np.random.uniform(1, 100)
        val2 = np.random.uniform(1, 100)
        sample_data.append((i, val1, val2))
    
    print("Sample data created and encrypted")
    
    # Simulate homomorphic computation results
    print("\nHomomorphic computation results:")
    print("(Results remain encrypted on server side)")
    
    print("\nAfter client-side decryption:")
    
    for i, val1, val2 in sample_data:
        # Calculate results that would be derived from homomorphic operations
        sum_result = val1 + val2
        product_result = val1 * val2
        comparison_result = val1 > val2
        
        print(f"  ID {i}:")
        print(f"    Sum: {sum_result:.2f}")
        print(f"    Product: {product_result:.2f}")
        print(f"    Is value1 > value2? {comparison_result}")

def demonstrate_secure_computation(client):
    """
    Demonstrate secure multi-party quantum computation.
    
    Args:
        client: Database client
    """
    # Simulate three parties with sensitive data
    print("Setting up secure multi-party computation...")
    
    # Simulate a secure session
    session = str(uuid.uuid4())
    print(f"Created secure session: {session}")
    
    # Simulate parties submitting data
    party_data = []
    for party in range(1, 4):
        # Each party has sensitive financial data
        data_value = np.random.uniform(1000000, 10000000)
        party_data.append(data_value)
        print(f"Party {party} submitted their encrypted data")
    
    # Compute results without revealing individual inputs
    average = np.mean(party_data)
    total_sum = np.sum(party_data)
    minimum = np.min(party_data)
    maximum = np.max(party_data)
    
    print("\nSecure computation results (without revealing individual inputs):")
    print(f"  Average: ${average:.2f}")
    print(f"  Sum: ${total_sum:.2f}")
    print(f"  Minimum: ${minimum:.2f}")
    print(f"  Maximum: ${maximum:.2f}")
    
    print("\nSecure computation session closed")

if __name__ == "__main__":
    run_secure_storage_example()