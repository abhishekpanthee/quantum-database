"""
Transparent Data Encryption (TDE)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Encrypts / decrypts data pages transparently at the storage layer using
envelope encryption.

Architecture::

    ┌─────────────┐
    │   Storage    │─── page write ──▶ TDE.encrypt_page()
    │   Layer      │◀── page read ─── TDE.decrypt_page()
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  Data-Key   │  unique per page / tablespace
    │  (AES-GCM)  │
    └──────┬──────┘
           │ encrypted by
    ┌──────▼──────┐
    │  Master Key │  stored in KMS
    └─────────────┘
"""

import hashlib
import json
import secrets
import threading
import time
from typing import Any, Dict, Optional, Union

from .aes_gcm import AESGCMCipher
from .kms import KMSProvider, LocalKeyStore
from .._standards import AES_KEY_SIZE, EncryptionException


class TransparentDataEncryption:
    """TDE layer with envelope encryption and key rotation."""

    def __init__(
        self,
        kms: Optional[KMSProvider] = None,
        master_key_id: str = "qndb-master",
    ) -> None:
        self._kms = kms or LocalKeyStore()
        self._master_key_id = master_key_id
        self._data_keys: Dict[str, AESGCMCipher] = {}
        self._encrypted_data_keys: Dict[str, bytes] = {}
        self._lock = threading.Lock()

        # Ensure master key exists
        try:
            self._kms.create_key(master_key_id, purpose="master")
        except (ValueError, Exception):
            pass  # already exists

    # -- data-key lifecycle ------------------------------------------------

    def _get_or_create_data_key(self, scope: str) -> AESGCMCipher:
        """Return a per-scope data key, creating one if needed."""
        with self._lock:
            if scope in self._data_keys:
                return self._data_keys[scope]

            # Generate a fresh data key and wrap with master
            raw_key = secrets.token_bytes(AES_KEY_SIZE)
            encrypted_dk = self._kms.encrypt_data_key(
                self._master_key_id, raw_key
            )
            cipher = AESGCMCipher(raw_key)
            self._data_keys[scope] = cipher
            self._encrypted_data_keys[scope] = encrypted_dk
            return cipher

    def rotate_data_key(self, scope: str) -> None:
        """Rotate the data key for *scope*."""
        with self._lock:
            raw_key = secrets.token_bytes(AES_KEY_SIZE)
            encrypted_dk = self._kms.encrypt_data_key(
                self._master_key_id, raw_key
            )
            self._data_keys[scope] = AESGCMCipher(raw_key)
            self._encrypted_data_keys[scope] = encrypted_dk

    # -- page-level encrypt / decrypt -------------------------------------

    def encrypt_page(
        self,
        scope: str,
        page_id: str,
        data: Union[str, bytes],
    ) -> Dict[str, bytes]:
        """Encrypt a data page.

        Returns a dict with ``ciphertext``, ``nonce``, ``tag``, and
        ``encrypted_data_key`` (the wrapped DEK).
        """
        cipher = self._get_or_create_data_key(scope)
        aad = f"{scope}:{page_id}".encode()
        result = cipher.encrypt(data, aad=aad)
        result["encrypted_data_key"] = self._encrypted_data_keys[scope]
        result["scope"] = scope.encode()
        result["page_id"] = page_id.encode()
        return result

    def decrypt_page(
        self,
        scope: str,
        page_id: str,
        ciphertext: bytes,
        nonce: bytes,
        tag: bytes,
        encrypted_data_key: Optional[bytes] = None,
    ) -> bytes:
        """Decrypt a data page."""
        with self._lock:
            cipher = self._data_keys.get(scope)

        if cipher is None:
            if encrypted_data_key is None:
                raise EncryptionException(
                    f"No data key for scope {scope!r} and no wrapped key provided"
                )
            raw_key = self._kms.decrypt_data_key(
                self._master_key_id, encrypted_data_key
            )
            cipher = AESGCMCipher(raw_key)
            with self._lock:
                self._data_keys[scope] = cipher

        aad = f"{scope}:{page_id}".encode()
        return cipher.decrypt(ciphertext, nonce, tag, aad=aad)

    # -- bulk re-encryption ------------------------------------------------

    def reencrypt_scope(
        self,
        scope: str,
        pages: Dict[str, Dict[str, bytes]],
    ) -> Dict[str, Dict[str, bytes]]:
        """Re-encrypt all pages in *scope* with a fresh data key.

        *pages* maps ``page_id`` → ``{ciphertext, nonce, tag, encrypted_data_key}``.
        Returns the same structure encrypted with the new key.
        """
        decrypted: Dict[str, bytes] = {}
        for page_id, enc in pages.items():
            decrypted[page_id] = self.decrypt_page(
                scope,
                page_id,
                enc["ciphertext"],
                enc["nonce"],
                enc["tag"],
                enc.get("encrypted_data_key"),
            )

        self.rotate_data_key(scope)

        result: Dict[str, Dict[str, bytes]] = {}
        for page_id, plaintext in decrypted.items():
            result[page_id] = self.encrypt_page(scope, page_id, plaintext)
        return result
