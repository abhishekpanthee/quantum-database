"""
Security Standards & Shared Constants
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Single source of truth for enums, cryptographic parameters, and security
configuration defaults used across the ``qndb.security`` package.
"""

from enum import Enum, auto
from typing import Dict, Set

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

class Permission(Enum):
    """Permissions available in the system."""
    READ = auto()
    WRITE = auto()
    DELETE = auto()
    ADMIN = auto()
    EXECUTE = auto()
    CREATE = auto()
    ALTER = auto()
    DROP = auto()
    GRANT = auto()
    REVOKE = auto()

    @classmethod
    def from_string(cls, perm_str: str) -> "Permission":
        return cls[perm_str.upper()]


# ---------------------------------------------------------------------------
# Resource Types
# ---------------------------------------------------------------------------

class ResourceType(Enum):
    """Types of protectable resources."""
    TABLE = auto()
    VIEW = auto()
    INDEX = auto()
    FUNCTION = auto()
    PROCEDURE = auto()
    SCHEMA = auto()
    SYSTEM = auto()
    QUERY = auto()
    USER = auto()
    ROLE = auto()
    DATABASE = auto()
    COLUMN = auto()

    @classmethod
    def from_string(cls, type_str: str) -> "ResourceType":
        return cls[type_str.upper()]


# ---------------------------------------------------------------------------
# Account Status
# ---------------------------------------------------------------------------

class LockoutStatus(Enum):
    """Account lockout states."""
    ACTIVE = auto()
    LOCKED = auto()
    DISABLED = auto()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AccessDeniedException(Exception):
    """Raised when a permission check fails."""
    pass


class AccountLockedException(Exception):
    """Raised when authentication is attempted on a locked account."""
    pass


class AuthenticationException(Exception):
    """Raised on invalid credentials or token."""
    pass


class SessionExpiredException(Exception):
    """Raised when a JWT has expired."""
    pass


class EncryptionException(Exception):
    """Raised on encryption / decryption failure."""
    pass


class TamperDetectedException(Exception):
    """Raised when audit-log tampering is detected."""
    pass


# ---------------------------------------------------------------------------
# Cryptographic Defaults
# ---------------------------------------------------------------------------

# Password hashing — scrypt parameters (RFC 7914)
SCRYPT_N = 2 ** 14         # CPU/memory cost
SCRYPT_R = 8               # Block size
SCRYPT_P = 1               # Parallelism
SCRYPT_DKLEN = 32          # Derived-key length (bytes)
SCRYPT_SALT_LEN = 16       # Salt length (bytes)

# JWT
JWT_DEFAULT_TTL = 3600          # Access-token lifetime (seconds)
JWT_REFRESH_TTL = 86400         # Refresh-token lifetime (seconds)
JWT_ALGORITHM = "HS256"

# AES-256-GCM
AES_KEY_SIZE = 32               # 256 bits
AES_NONCE_SIZE = 12             # 96 bits (GCM standard)
AES_TAG_SIZE = 16               # 128 bits

# Account lockout
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes

# Audit retention tiers (seconds)
RETENTION_HOT = 30 * 86400          # 30 days
RETENTION_WARM = 365 * 86400        # 1 year
RETENTION_COLD = 7 * 365 * 86400    # 7 years

# Post-quantum parameters (sizes per FIPS 203/204)
PQC_KYBER_SECURITY_LEVEL = 3        # ML-KEM-768
PQC_DILITHIUM_SECURITY_LEVEL = 3    # ML-DSA-65

# TLS
TLS_MIN_VERSION = "1.3"
TLS_CIPHERS = [
    "TLS_AES_256_GCM_SHA384",
    "TLS_CHACHA20_POLY1305_SHA256",
]

# ---------------------------------------------------------------------------
# Query-type → Permission mapping
# ---------------------------------------------------------------------------

QUERY_PERMISSION_MAP: Dict[str, Permission] = {
    "SELECT": Permission.READ,
    "READ": Permission.READ,
    "INSERT": Permission.WRITE,
    "UPDATE": Permission.WRITE,
    "WRITE": Permission.WRITE,
    "DELETE": Permission.DELETE,
    "CREATE": Permission.CREATE,
    "ALTER": Permission.ALTER,
    "DROP": Permission.DROP,
}
