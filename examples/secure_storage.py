"""
Security — Quantum Encryption, Access Control, Audit Logging
==============================================================

Demonstrates quantum key distribution, role-based access control,
and audit trail logging.
"""

from qndb.security.quantum_encryption import QuantumEncryption
from qndb.security.access_control import AccessControl
from qndb.security.audit import AuditLogger


def encryption_demo():
    """Quantum key distribution and encryption."""
    print("=== Quantum Encryption ===\n")

    enc = QuantumEncryption(num_qubits=8)

    # Generate a quantum key pair
    key = enc.generate_key(protocol="BB84", key_length=256)
    print(f"Generated key: {key.key_id}, length={key.length} bits")

    # Encrypt data
    plaintext = b"sensitive-database-record"
    ciphertext = enc.encrypt(plaintext, key)
    print(f"Encrypted: {len(ciphertext)} bytes")

    # Decrypt
    decrypted = enc.decrypt(ciphertext, key)
    print(f"Decrypted: {decrypted}")
    assert decrypted == plaintext


def access_control_demo():
    """Role-based access control (RBAC)."""
    print("\n=== Access Control ===\n")

    ac = AccessControl()

    # Define roles
    ac.create_role("admin", permissions=["read", "write", "delete", "manage_users"])
    ac.create_role("analyst", permissions=["read"])
    ac.create_role("engineer", permissions=["read", "write"])

    # Create users
    ac.create_user("alice", role="admin")
    ac.create_user("bob", role="analyst")
    ac.create_user("carol", role="engineer")

    # Check permissions
    for user, action in [("alice", "delete"), ("bob", "write"), ("carol", "read")]:
        allowed = ac.check_permission(user, action)
        print(f"{user} -> {action}: {'allowed' if allowed else 'denied'}")

    # List users and roles
    print(f"\nUsers: {ac.list_users()}")
    print(f"Roles: {ac.list_roles()}")


def audit_demo():
    """Audit trail logging."""
    print("\n=== Audit Logging ===\n")

    logger = AuditLogger()

    # Log operations
    logger.log(user="alice", action="CREATE TABLE", resource="sensors", status="success")
    logger.log(user="bob", action="SELECT", resource="sensors", status="success")
    logger.log(user="bob", action="DELETE", resource="sensors", status="denied")

    # Query audit trail
    entries = logger.query(user="bob")
    print(f"Bob's audit entries: {len(entries)}")
    for entry in entries:
        print(f"  [{entry.timestamp}] {entry.action} on {entry.resource}: {entry.status}")

    # Get denied operations
    denied = logger.query(status="denied")
    print(f"\nDenied operations: {len(denied)}")


def main():
    encryption_demo()
    access_control_demo()
    audit_demo()


if __name__ == "__main__":
    main()
