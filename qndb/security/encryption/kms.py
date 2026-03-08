"""
Key Management System (KMS) Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Abstract KMS interface with concrete adapters for:

* **LocalKeyStore** — file-based key store (dev / testing)
* **VaultKMSProvider** — HashiCorp Vault (production)
* **AWSKMSProvider** — AWS KMS (cloud)

Keys are identified by a string *key_id* and versioned with monotonic
integers.  The active version is always the highest.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import threading
from typing import Any, Dict, List, Optional, Tuple

from .._standards import AES_KEY_SIZE, EncryptionException


# ---------------------------------------------------------------------------
# Abstract KMS interface
# ---------------------------------------------------------------------------

class KMSProvider:
    """Base class for key management system providers."""

    def create_key(self, key_id: str, *, purpose: str = "encrypt") -> Dict[str, Any]:
        raise NotImplementedError

    def get_key(self, key_id: str, *, version: Optional[int] = None) -> bytes:
        raise NotImplementedError

    def rotate_key(self, key_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def list_keys(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def destroy_key(self, key_id: str, version: int) -> None:
        raise NotImplementedError

    def encrypt_data_key(self, key_id: str, plaintext_key: bytes) -> bytes:
        """Envelope encryption: encrypt a data-key with the master key."""
        raise NotImplementedError

    def decrypt_data_key(self, key_id: str, encrypted_key: bytes) -> bytes:
        """Envelope decryption: decrypt a wrapped data-key."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# LocalKeyStore (file-based, for dev/test)
# ---------------------------------------------------------------------------

class LocalKeyStore(KMSProvider):
    """In-memory + optional file-backed key store."""

    def __init__(self, storage_path: Optional[str] = None) -> None:
        self._keys: Dict[str, Dict[int, bytes]] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._storage_path = storage_path

        if storage_path and os.path.isfile(storage_path):
            self._load()

    def create_key(
        self, key_id: str, *, purpose: str = "encrypt"
    ) -> Dict[str, Any]:
        with self._lock:
            if key_id in self._keys:
                raise ValueError(f"Key {key_id} already exists")
            key_material = secrets.token_bytes(AES_KEY_SIZE)
            self._keys[key_id] = {1: key_material}
            self._metadata[key_id] = {
                "purpose": purpose,
                "created_at": time.time(),
                "current_version": 1,
            }
            self._persist()
            return {"key_id": key_id, "version": 1, "purpose": purpose}

    def get_key(
        self, key_id: str, *, version: Optional[int] = None
    ) -> bytes:
        with self._lock:
            if key_id not in self._keys:
                raise KeyError(f"Key {key_id} not found")
            versions = self._keys[key_id]
            v = version or max(versions)
            if v not in versions:
                raise KeyError(f"Key {key_id} version {v} not found")
            return versions[v]

    def rotate_key(self, key_id: str) -> Dict[str, Any]:
        with self._lock:
            if key_id not in self._keys:
                raise KeyError(f"Key {key_id} not found")
            new_version = max(self._keys[key_id]) + 1
            self._keys[key_id][new_version] = secrets.token_bytes(AES_KEY_SIZE)
            self._metadata[key_id]["current_version"] = new_version
            self._persist()
            return {"key_id": key_id, "version": new_version}

    def list_keys(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"key_id": kid, **meta}
                for kid, meta in self._metadata.items()
            ]

    def destroy_key(self, key_id: str, version: int) -> None:
        with self._lock:
            if key_id in self._keys and version in self._keys[key_id]:
                del self._keys[key_id][version]
                if not self._keys[key_id]:
                    del self._keys[key_id]
                    del self._metadata[key_id]
                self._persist()

    def encrypt_data_key(self, key_id: str, plaintext_key: bytes) -> bytes:
        master = self.get_key(key_id)
        nonce = secrets.token_bytes(12)
        keystream = hashlib.sha256(master + nonce).digest()
        ct = bytes(a ^ b for a, b in zip(plaintext_key, keystream[: len(plaintext_key)]))
        tag = hmac.new(master, nonce + ct, hashlib.sha256).digest()[:16]
        return nonce + ct + tag

    def decrypt_data_key(self, key_id: str, encrypted_key: bytes) -> bytes:
        master = self.get_key(key_id)
        nonce = encrypted_key[:12]
        tag = encrypted_key[-16:]
        ct = encrypted_key[12:-16]
        expected_tag = hmac.new(master, nonce + ct, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expected_tag):
            raise EncryptionException("Data-key integrity check failed")
        keystream = hashlib.sha256(master + nonce).digest()
        return bytes(a ^ b for a, b in zip(ct, keystream[: len(ct)]))

    # -- persistence -------------------------------------------------------

    def _persist(self) -> None:
        if not self._storage_path:
            return
        data = {
            "keys": {
                kid: {str(v): base64.b64encode(k).decode() for v, k in vers.items()}
                for kid, vers in self._keys.items()
            },
            "metadata": self._metadata,
        }
        tmp = self._storage_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self._storage_path)

    def _load(self) -> None:
        with open(self._storage_path) as f:
            data = json.load(f)
        self._keys = {
            kid: {int(v): base64.b64decode(k) for v, k in vers.items()}
            for kid, vers in data.get("keys", {}).items()
        }
        self._metadata = data.get("metadata", {})


# ---------------------------------------------------------------------------
# HashiCorp Vault adapter (requires ``hvac`` at runtime)
# ---------------------------------------------------------------------------

class VaultKMSProvider(KMSProvider):
    """HashiCorp Vault Transit secrets engine adapter.

    Requires the ``hvac`` Python package and a running Vault instance.
    """

    def __init__(
        self,
        vault_url: str = "http://127.0.0.1:8200",
        token: str = "",
        mount_point: str = "transit",
        namespace: Optional[str] = None,
    ) -> None:
        self.vault_url = vault_url
        self.mount_point = mount_point
        self.namespace = namespace
        self._token = token
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import hvac
            except ImportError:
                raise ImportError(
                    "HashiCorp Vault KMS requires `hvac`: pip install hvac"
                )
            self._client = hvac.Client(
                url=self.vault_url,
                token=self._token,
                namespace=self.namespace,
            )
        return self._client

    def create_key(
        self, key_id: str, *, purpose: str = "encrypt"
    ) -> Dict[str, Any]:
        client = self._get_client()
        client.secrets.transit.create_key(
            name=key_id, mount_point=self.mount_point
        )
        return {"key_id": key_id, "version": 1, "purpose": purpose}

    def get_key(
        self, key_id: str, *, version: Optional[int] = None
    ) -> bytes:
        raise EncryptionException(
            "Vault transit keys are not exportable by default"
        )

    def rotate_key(self, key_id: str) -> Dict[str, Any]:
        client = self._get_client()
        client.secrets.transit.rotate_key(
            name=key_id, mount_point=self.mount_point
        )
        info = client.secrets.transit.read_key(
            name=key_id, mount_point=self.mount_point
        )
        ver = info["data"]["latest_version"]
        return {"key_id": key_id, "version": ver}

    def list_keys(self) -> List[Dict[str, Any]]:
        client = self._get_client()
        result = client.secrets.transit.list_keys(
            mount_point=self.mount_point
        )
        return [{"key_id": k} for k in result["data"]["keys"]]

    def destroy_key(self, key_id: str, version: int) -> None:
        client = self._get_client()
        client.secrets.transit.delete_key(
            name=key_id, mount_point=self.mount_point
        )

    def encrypt_data_key(self, key_id: str, plaintext_key: bytes) -> bytes:
        client = self._get_client()
        b64 = base64.b64encode(plaintext_key).decode()
        result = client.secrets.transit.encrypt_data(
            name=key_id,
            plaintext=b64,
            mount_point=self.mount_point,
        )
        return result["data"]["ciphertext"].encode()

    def decrypt_data_key(self, key_id: str, encrypted_key: bytes) -> bytes:
        client = self._get_client()
        result = client.secrets.transit.decrypt_data(
            name=key_id,
            ciphertext=encrypted_key.decode(),
            mount_point=self.mount_point,
        )
        return base64.b64decode(result["data"]["plaintext"])


# ---------------------------------------------------------------------------
# AWS KMS adapter (requires ``boto3`` at runtime)
# ---------------------------------------------------------------------------

class AWSKMSProvider(KMSProvider):
    """AWS KMS adapter.  Requires ``boto3``."""

    def __init__(
        self,
        region: str = "us-east-1",
        profile: Optional[str] = None,
    ) -> None:
        self.region = region
        self.profile = profile
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "AWS KMS requires `boto3`: pip install boto3"
                )
            session = boto3.Session(
                region_name=self.region, profile_name=self.profile
            )
            self._client = session.client("kms")
        return self._client

    def create_key(
        self, key_id: str, *, purpose: str = "encrypt"
    ) -> Dict[str, Any]:
        client = self._get_client()
        resp = client.create_key(
            Description=key_id,
            KeyUsage="ENCRYPT_DECRYPT",
            Origin="AWS_KMS",
        )
        return {
            "key_id": resp["KeyMetadata"]["KeyId"],
            "arn": resp["KeyMetadata"]["Arn"],
            "purpose": purpose,
        }

    def get_key(
        self, key_id: str, *, version: Optional[int] = None
    ) -> bytes:
        raise EncryptionException("AWS KMS keys are non-exportable")

    def rotate_key(self, key_id: str) -> Dict[str, Any]:
        client = self._get_client()
        client.enable_key_rotation(KeyId=key_id)
        return {"key_id": key_id, "auto_rotation": True}

    def list_keys(self) -> List[Dict[str, Any]]:
        client = self._get_client()
        resp = client.list_keys()
        return [
            {"key_id": k["KeyId"], "arn": k["KeyArn"]}
            for k in resp["Keys"]
        ]

    def destroy_key(self, key_id: str, version: int) -> None:
        client = self._get_client()
        client.schedule_key_deletion(KeyId=key_id, PendingWindowInDays=7)

    def encrypt_data_key(self, key_id: str, plaintext_key: bytes) -> bytes:
        client = self._get_client()
        resp = client.encrypt(KeyId=key_id, Plaintext=plaintext_key)
        return resp["CiphertextBlob"]

    def decrypt_data_key(self, key_id: str, encrypted_key: bytes) -> bytes:
        client = self._get_client()
        resp = client.decrypt(KeyId=key_id, CiphertextBlob=encrypted_key)
        return resp["Plaintext"]
