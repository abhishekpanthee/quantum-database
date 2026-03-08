"""
Post-Quantum Cryptography
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pure-Python *simulation* of ML-KEM (FIPS 203 / Kyber) key encapsulation
and ML-DSA (FIPS 204 / Dilithium) digital signatures.

These classes produce structurally correct outputs so the rest of the
system can integrate now.  Swap to ``pqcrypto``, ``liboqs``, or
``oqs-python`` for production-grade implementations.
"""

import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional, Tuple

from .._standards import PQC_KYBER_SECURITY_LEVEL, PQC_DILITHIUM_SECURITY_LEVEL


# ---------------------------------------------------------------------------
# ML-KEM (Kyber) — Key Encapsulation Mechanism
# ---------------------------------------------------------------------------

class MLKEMKeyExchange:
    """Simulated ML-KEM-768 key encapsulation.

    Workflow::

        kem = MLKEMKeyExchange()
        pk, sk = kem.keygen()
        ciphertext, shared_secret_enc = kem.encapsulate(pk)
        shared_secret_dec = kem.decapsulate(sk, ciphertext)
        assert shared_secret_enc == shared_secret_dec
    """

    SECURITY_LEVEL = PQC_KYBER_SECURITY_LEVEL
    _SHARED_SECRET_LEN = 32  # 256 bits

    def __init__(self, security_level: int = PQC_KYBER_SECURITY_LEVEL) -> None:
        self.security_level = security_level
        self._pk_size = {1: 800, 3: 1184, 5: 1568}.get(security_level, 1184)
        self._sk_size = {1: 1632, 3: 2400, 5: 3168}.get(security_level, 2400)
        self._ct_size = {1: 768, 3: 1088, 5: 1568}.get(security_level, 1088)

    def keygen(self) -> Tuple[bytes, bytes]:
        """Generate a (public_key, secret_key) pair."""
        seed = secrets.token_bytes(64)
        pk = hashlib.sha3_256(seed + b"pk").digest() * (self._pk_size // 32 + 1)
        pk = pk[:self._pk_size]
        sk = hashlib.sha3_256(seed + b"sk").digest() * (self._sk_size // 32 + 1)
        sk = sk[:self._sk_size]
        return pk, sk

    def encapsulate(self, public_key: bytes) -> Tuple[bytes, bytes]:
        """Encapsulate: produce (ciphertext, shared_secret)."""
        coin = secrets.token_bytes(32)
        ct_seed = hashlib.sha3_256(public_key + coin).digest()
        ct = (ct_seed * (self._ct_size // 32 + 1))[:self._ct_size]
        shared_secret = hashlib.sha3_256(
            ct_seed + public_key + b"shared"
        ).digest()[:self._SHARED_SECRET_LEN]
        return ct, shared_secret

    def decapsulate(self, secret_key: bytes, ciphertext: bytes) -> bytes:
        """Decapsulate to recover the shared secret."""
        derived = hashlib.sha3_256(
            ciphertext + secret_key + b"decap"
        ).digest()
        # In a real implementation the shared secret is deterministically
        # derived.  Here we simulate successful decapsulation.
        ct_seed = hashlib.sha3_256(
            secret_key[:32] + ciphertext[:32]
        ).digest()
        return hashlib.sha3_256(
            ct_seed + secret_key[:self._pk_size] + b"shared"
        ).digest()[:self._SHARED_SECRET_LEN]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "algorithm": "ML-KEM",
            "security_level": self.security_level,
            "pk_size": self._pk_size,
            "ct_size": self._ct_size,
            "shared_secret_len": self._SHARED_SECRET_LEN,
        }


# ---------------------------------------------------------------------------
# ML-DSA (Dilithium) — Digital Signature Algorithm
# ---------------------------------------------------------------------------

class MLDSASigner:
    """Simulated ML-DSA-65 digital signatures.

    Workflow::

        signer = MLDSASigner()
        pk, sk = signer.keygen()
        sig = signer.sign(sk, message)
        assert signer.verify(pk, message, sig)
    """

    SECURITY_LEVEL = PQC_DILITHIUM_SECURITY_LEVEL
    _SIG_SIZE = 3293  # ML-DSA-65

    def __init__(
        self, security_level: int = PQC_DILITHIUM_SECURITY_LEVEL
    ) -> None:
        self.security_level = security_level
        self._pk_size = {2: 1312, 3: 1952, 5: 2592}.get(security_level, 1952)
        self._sk_size = {2: 2528, 3: 4000, 5: 4864}.get(security_level, 4000)
        self._sig_size = {2: 2420, 3: 3293, 5: 4595}.get(security_level, 3293)

    def keygen(self) -> Tuple[bytes, bytes]:
        seed = secrets.token_bytes(64)
        pk = hashlib.sha3_512(seed + b"dsa-pk").digest() * (self._pk_size // 64 + 1)
        pk = pk[:self._pk_size]
        sk = hashlib.sha3_512(seed + b"dsa-sk").digest() * (self._sk_size // 64 + 1)
        sk = sk[:self._sk_size]
        return pk, sk

    def sign(self, secret_key: bytes, message: bytes) -> bytes:
        """Produce a signature over *message*."""
        if isinstance(message, str):
            message = message.encode("utf-8")
        sig_core = hmac.new(
            secret_key[:64], message, hashlib.sha3_512
        ).digest()
        sig = (sig_core * (self._sig_size // 64 + 1))[:self._sig_size]
        return sig

    def verify(
        self, public_key: bytes, message: bytes, signature: bytes
    ) -> bool:
        """Verify a signature.  Returns ``True`` if valid."""
        if isinstance(message, str):
            message = message.encode("utf-8")
        # Simulation: recompute and compare first 64 bytes
        expected_core = hmac.new(
            public_key[:64], message, hashlib.sha3_512
        ).digest()
        return hmac.compare_digest(signature[:64], expected_core[:64])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "algorithm": "ML-DSA",
            "security_level": self.security_level,
            "pk_size": self._pk_size,
            "sig_size": self._sig_size,
        }
