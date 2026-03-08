"""
Password Hashing
~~~~~~~~~~~~~~~~
Secure password hashing using hashlib.scrypt (RFC 7914).

When ``argon2-cffi`` or ``bcrypt`` are installed they are preferred
automatically; otherwise scrypt provides equivalent security.

Storage format (scrypt fallback)::

    $scrypt$n=<N>,r=<r>,p=<p>$<salt_b64>$<hash_b64>
"""

import base64
import hashlib
import hmac
import secrets
from typing import Optional

from .._standards import SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN, SCRYPT_SALT_LEN


class PasswordHasher:
    """Adaptive password hashing with automatic backend selection."""

    def __init__(
        self,
        *,
        n: int = SCRYPT_N,
        r: int = SCRYPT_R,
        p: int = SCRYPT_P,
        dklen: int = SCRYPT_DKLEN,
    ):
        self._n = n
        self._r = r
        self._p = p
        self._dklen = dklen
        self._backend = self._select_backend()

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------

    @staticmethod
    def _select_backend() -> str:
        try:
            import argon2  # noqa: F401
            return "argon2"
        except ImportError:
            pass
        try:
            import bcrypt  # noqa: F401
            return "bcrypt"
        except ImportError:
            pass
        return "scrypt"

    @property
    def backend(self) -> str:
        """Return the name of the active hashing backend."""
        return self._backend

    # ------------------------------------------------------------------
    # Hash / Verify
    # ------------------------------------------------------------------

    def hash(self, password: str) -> str:
        """Hash a plaintext password.

        Returns an opaque string that encodes algorithm, parameters,
        salt, and derived key.
        """
        if self._backend == "argon2":
            import argon2
            return argon2.PasswordHasher().hash(password)

        if self._backend == "bcrypt":
            import bcrypt as _bc
            return _bc.hashpw(password.encode(), _bc.gensalt()).decode()

        # scrypt fallback
        salt = secrets.token_bytes(SCRYPT_SALT_LEN)
        dk = hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=self._n,
            r=self._r,
            p=self._p,
            dklen=self._dklen,
        )
        salt_b64 = base64.b64encode(salt).decode()
        dk_b64 = base64.b64encode(dk).decode()
        return f"$scrypt$n={self._n},r={self._r},p={self._p}${salt_b64}${dk_b64}"

    def verify(self, password: str, hashed: str) -> bool:
        """Verify a plaintext password against a stored hash.

        Uses constant-time comparison to prevent timing attacks.
        """
        if self._backend == "argon2":
            import argon2
            try:
                return argon2.PasswordHasher().verify(hashed, password)
            except argon2.exceptions.VerifyMismatchError:
                return False

        if self._backend == "bcrypt":
            import bcrypt as _bc
            return _bc.checkpw(password.encode(), hashed.encode())

        # scrypt
        parts = hashed.split("$")
        if len(parts) != 5 or parts[1] != "scrypt":
            return False
        params = dict(kv.split("=") for kv in parts[2].split(","))
        salt = base64.b64decode(parts[3])
        expected = base64.b64decode(parts[4])
        dk = hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=int(params["n"]),
            r=int(params["r"]),
            p=int(params["p"]),
            dklen=len(expected),
        )
        return hmac.compare_digest(dk, expected)

    def needs_rehash(self, hashed: str) -> bool:
        """Return True if the hash uses outdated parameters."""
        if self._backend == "argon2":
            import argon2
            return argon2.PasswordHasher().check_needs_rehash(hashed)
        if self._backend == "bcrypt":
            return False  # bcrypt rounds are embedded in the hash
        parts = hashed.split("$")
        if len(parts) != 5 or parts[1] != "scrypt":
            return True
        params = dict(kv.split("=") for kv in parts[2].split(","))
        return int(params.get("n", 0)) < self._n
