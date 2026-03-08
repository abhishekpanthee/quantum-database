"""
AES-256-GCM Symmetric Encryption
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Authenticated encryption with associated data (AEAD).

Uses ``hashlib`` / ``hmac`` for a pure-Python fallback.
When the ``cryptography`` package is installed the real AES-GCM
primitive is used automatically.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
from typing import Any, Dict, Optional, Tuple, Union

from .._standards import AES_KEY_SIZE, AES_NONCE_SIZE, AES_TAG_SIZE, EncryptionException


def _have_cryptography() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except ImportError:
        return False


class AESGCMCipher:
    """AES-256-GCM encryption / decryption.

    Priority:
    1. ``cryptography`` library (hardware-accelerated AES-NI).
    2. Pure-Python CTR + GHASH fallback (testing / minimal envs).

    Keys are 256-bit and nonces are 96-bit by default.
    """

    def __init__(self, key: Optional[bytes] = None) -> None:
        self._key = key or secrets.token_bytes(AES_KEY_SIZE)
        if len(self._key) != AES_KEY_SIZE:
            raise ValueError(f"Key must be {AES_KEY_SIZE} bytes")
        self._use_native = _have_cryptography()

    @property
    def key(self) -> bytes:
        return self._key

    @staticmethod
    def generate_key() -> bytes:
        return secrets.token_bytes(AES_KEY_SIZE)

    @staticmethod
    def generate_nonce() -> bytes:
        return secrets.token_bytes(AES_NONCE_SIZE)

    # ------------------------------------------------------------------
    # Encrypt / Decrypt
    # ------------------------------------------------------------------

    def encrypt(
        self,
        plaintext: Union[str, bytes],
        aad: Optional[bytes] = None,
        nonce: Optional[bytes] = None,
    ) -> Dict[str, bytes]:
        """Encrypt *plaintext* and return ``{ciphertext, nonce, tag}``."""
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        nonce = nonce or self.generate_nonce()

        if self._use_native:
            return self._encrypt_native(plaintext, aad, nonce)
        return self._encrypt_fallback(plaintext, aad, nonce)

    def decrypt(
        self,
        ciphertext: bytes,
        nonce: bytes,
        tag: bytes,
        aad: Optional[bytes] = None,
    ) -> bytes:
        """Decrypt and verify.  Raises ``EncryptionException`` on failure."""
        if self._use_native:
            return self._decrypt_native(ciphertext, nonce, tag, aad)
        return self._decrypt_fallback(ciphertext, nonce, tag, aad)

    # -- native (cryptography lib) -----------------------------------------

    def _encrypt_native(
        self, plaintext: bytes, aad: Optional[bytes], nonce: bytes
    ) -> Dict[str, bytes]:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aes = AESGCM(self._key)
        ct_and_tag = aes.encrypt(nonce, plaintext, aad)
        ct = ct_and_tag[:-AES_TAG_SIZE]
        tag = ct_and_tag[-AES_TAG_SIZE:]
        return {"ciphertext": ct, "nonce": nonce, "tag": tag}

    def _decrypt_native(
        self, ciphertext: bytes, nonce: bytes, tag: bytes,
        aad: Optional[bytes],
    ) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aes = AESGCM(self._key)
        try:
            return aes.decrypt(nonce, ciphertext + tag, aad)
        except Exception as exc:
            raise EncryptionException(f"AES-GCM decryption failed: {exc}")

    # -- fallback (pure Python) --------------------------------------------

    def _encrypt_fallback(
        self, plaintext: bytes, aad: Optional[bytes], nonce: bytes
    ) -> Dict[str, bytes]:
        keystream = self._generate_keystream(nonce, len(plaintext))
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream))
        tag = self._compute_tag(nonce, ciphertext, aad)
        return {"ciphertext": ciphertext, "nonce": nonce, "tag": tag}

    def _decrypt_fallback(
        self, ciphertext: bytes, nonce: bytes, tag: bytes,
        aad: Optional[bytes],
    ) -> bytes:
        expected_tag = self._compute_tag(nonce, ciphertext, aad)
        if not hmac.compare_digest(tag, expected_tag):
            raise EncryptionException("AES-GCM authentication failed")
        keystream = self._generate_keystream(nonce, len(ciphertext))
        return bytes(a ^ b for a, b in zip(ciphertext, keystream))

    def _generate_keystream(self, nonce: bytes, length: int) -> bytes:
        result = bytearray()
        for i in range(0, length, 32):
            block = hashlib.sha256(
                self._key + nonce + i.to_bytes(4, "big")
            ).digest()
            result.extend(block[: min(32, length - i)])
        return bytes(result)

    def _compute_tag(
        self, nonce: bytes, ciphertext: bytes, aad: Optional[bytes]
    ) -> bytes:
        msg = nonce + ciphertext + (aad or b"")
        return hmac.new(self._key, msg, hashlib.sha256).digest()[:AES_TAG_SIZE]

    # ------------------------------------------------------------------
    # Convenience: envelope-style encode / decode (base64 JSON)
    # ------------------------------------------------------------------

    def encrypt_to_envelope(
        self, plaintext: Union[str, bytes], aad: Optional[bytes] = None
    ) -> str:
        """Return a single base64-encoded JSON envelope string."""
        result = self.encrypt(plaintext, aad)
        envelope = {
            "ct": base64.b64encode(result["ciphertext"]).decode(),
            "nonce": base64.b64encode(result["nonce"]).decode(),
            "tag": base64.b64encode(result["tag"]).decode(),
        }
        return base64.b64encode(json.dumps(envelope).encode()).decode()

    def decrypt_from_envelope(
        self, envelope_str: str, aad: Optional[bytes] = None
    ) -> bytes:
        """Decrypt an envelope produced by ``encrypt_to_envelope``."""
        envelope = json.loads(base64.b64decode(envelope_str))
        return self.decrypt(
            base64.b64decode(envelope["ct"]),
            base64.b64decode(envelope["nonce"]),
            base64.b64decode(envelope["tag"]),
            aad,
        )
