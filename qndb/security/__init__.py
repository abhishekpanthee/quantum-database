"""
qndb.security — Enterprise Security Package
=============================================

Public API re-exports.  Import from this package for the latest
enterprise-grade implementations.

Legacy import paths (``qndb.security.access_control``,
``qndb.security.quantum_encryption``, ``qndb.security.audit``)
remain functional for backward compatibility.
"""

# ── Standards & shared types ─────────────────────────────────────────
from qndb.security._standards import (          # noqa: F401
    Permission,
    ResourceType,
    LockoutStatus,
    AccessDeniedException,
    AccountLockedException,
    AuthenticationException,
    SessionExpiredException,
    EncryptionException,
    TamperDetectedException,
)

# ── Authentication ───────────────────────────────────────────────────
from qndb.security.auth.password import PasswordHasher       # noqa: F401
from qndb.security.auth.jwt_manager import JWTManager        # noqa: F401
from qndb.security.auth.oauth import OAuth2Provider, OIDCManager  # noqa: F401

# ── Authorisation ────────────────────────────────────────────────────
from qndb.security.authorization.models import (             # noqa: F401
    User,
    Role,
    Resource,
    AccessControlList,
)
from qndb.security.authorization.rbac import AccessControlManager  # noqa: F401
from qndb.security.authorization.abac import (               # noqa: F401
    ABACCondition,
    ABACPolicy,
    ABACEngine,
)
from qndb.security.authorization.rls import (                # noqa: F401
    RLSPolicy,
    ColumnMask,
    filter_rows,
    apply_column_masks,
)

# ── Encryption ───────────────────────────────────────────────────────
from qndb.security.encryption.aes_gcm import AESGCMCipher    # noqa: F401
from qndb.security.encryption.pqc import (                   # noqa: F401
    MLKEMKeyExchange,
    MLDSASigner,
)
from qndb.security.encryption.qkd import (                   # noqa: F401
    QuantumKeyDistribution as QKD,
)
from qndb.security.encryption.kms import (                   # noqa: F401
    KMSProvider,
    LocalKeyStore,
    VaultKMSProvider,
    AWSKMSProvider,
)
from qndb.security.encryption.tde import TransparentDataEncryption  # noqa: F401

# ── Audit ────────────────────────────────────────────────────────────
from qndb.security.audit.events import AuditEventType, AuditEvent  # noqa: F401
from qndb.security.audit.sinks import (                      # noqa: F401
    AuditEventSink,
    FileAuditEventSink,
    StreamAuditEventSink,
)
from qndb.security.audit.logger import AuditLogger           # noqa: F401
from qndb.security.audit.hash_chain import HashChainAuditLog  # noqa: F401
from qndb.security.audit.compliance import SOC2Mapper, GDPRManager  # noqa: F401
from qndb.security.audit.retention import RetentionManager   # noqa: F401

# ── Quantum Security ────────────────────────────────────────────────
from qndb.security.quantum.no_cloning import NoCloningEnforcer  # noqa: F401
from qndb.security.quantum.state_access import QuantumStateAccessLogger  # noqa: F401
from qndb.security.quantum.entanglement_auth import EntanglementAuthProtocol  # noqa: F401
from qndb.security.quantum.qrng import QuantumRNG            # noqa: F401
from qndb.security.quantum.side_channel import SideChannelMitigator  # noqa: F401

__all__ = [
    # Standards
    "Permission", "ResourceType", "LockoutStatus",
    "AccessDeniedException", "AccountLockedException",
    "AuthenticationException", "SessionExpiredException",
    "EncryptionException", "TamperDetectedException",
    # Auth
    "PasswordHasher", "JWTManager", "OAuth2Provider", "OIDCManager",
    # Authorization
    "User", "Role", "Resource", "AccessControlList",
    "AccessControlManager",
    "ABACCondition", "ABACPolicy", "ABACEngine",
    "RLSPolicy", "ColumnMask", "filter_rows", "apply_column_masks",
    # Encryption
    "AESGCMCipher", "MLKEMKeyExchange", "MLDSASigner",
    "QKD", "KMSProvider", "LocalKeyStore",
    "VaultKMSProvider", "AWSKMSProvider",
    "TransparentDataEncryption",
    # Audit
    "AuditEventType", "AuditEvent",
    "AuditEventSink", "FileAuditEventSink", "StreamAuditEventSink",
    "AuditLogger", "HashChainAuditLog",
    "SOC2Mapper", "GDPRManager", "RetentionManager",
    # Quantum
    "NoCloningEnforcer", "QuantumStateAccessLogger",
    "EntanglementAuthProtocol", "QuantumRNG", "SideChannelMitigator",
]
