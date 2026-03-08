"""
JWT Session Management
~~~~~~~~~~~~~~~~~~~~~~
Minimal HS256 JWT implementation with no external dependencies.

For production, swap in ``PyJWT`` or ``python-jose`` via
``set_signing_key()`` and override ``create_token`` / ``verify_token``.

Features:
- Access + refresh token lifecycle
- JTI-based revocation list (replay defence)
- Constant-time signature comparison
"""

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
import uuid
from typing import Any, Dict, Optional, Set, Tuple

from .._standards import (
    JWT_ALGORITHM,
    JWT_DEFAULT_TTL,
    JWT_REFRESH_TTL,
    AuthenticationException,
    SessionExpiredException,
)


class JWTManager:
    """Issue, verify, refresh, and revoke HS256 JSON Web Tokens."""

    def __init__(
        self,
        signing_key: Optional[bytes] = None,
        token_ttl_seconds: int = JWT_DEFAULT_TTL,
        refresh_ttl_seconds: int = JWT_REFRESH_TTL,
    ):
        self._key = signing_key or secrets.token_bytes(32)
        self.token_ttl = token_ttl_seconds
        self.refresh_ttl = refresh_ttl_seconds
        self._revoked: Set[str] = set()
        self._lock = threading.Lock()

    def set_signing_key(self, key: bytes) -> None:
        """Replace the HMAC signing key."""
        self._key = key

    # ------------------------------------------------------------------
    # Encoding helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _b64url_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    @staticmethod
    def _b64url_decode(s: str) -> bytes:
        s += "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s)

    # ------------------------------------------------------------------
    # Token lifecycle
    # ------------------------------------------------------------------

    def create_token(
        self,
        claims: Dict[str, Any],
        *,
        ttl: Optional[int] = None,
    ) -> str:
        """Create a signed JWT with the given claims."""
        header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
        now = time.time()
        payload = {
            "iat": now,
            "exp": now + (ttl or self.token_ttl),
            "jti": uuid.uuid4().hex,
            **claims,
        }
        segments = [
            self._b64url_encode(json.dumps(header).encode()),
            self._b64url_encode(json.dumps(payload).encode()),
        ]
        signing_input = f"{segments[0]}.{segments[1]}".encode()
        sig = hmac.new(self._key, signing_input, hashlib.sha256).digest()
        segments.append(self._b64url_encode(sig))
        return ".".join(segments)

    def create_refresh_token(self, claims: Dict[str, Any]) -> str:
        """Create a refresh token (longer TTL, ``type=refresh``)."""
        return self.create_token(
            {**claims, "type": "refresh"}, ttl=self.refresh_ttl
        )

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify signature, expiry, and revocation status.

        Raises:
            AuthenticationException: on bad signature or revocation.
            SessionExpiredException: on expiry.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthenticationException("Malformed JWT")

        signing_input = f"{parts[0]}.{parts[1]}".encode()
        expected_sig = hmac.new(
            self._key, signing_input, hashlib.sha256
        ).digest()
        actual_sig = self._b64url_decode(parts[2])

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise AuthenticationException("Invalid JWT signature")

        payload = json.loads(self._b64url_decode(parts[1]))

        if payload.get("exp", 0) < time.time():
            raise SessionExpiredException("JWT has expired")

        with self._lock:
            if payload.get("jti") in self._revoked:
                raise AuthenticationException("Token has been revoked")

        return payload

    def revoke_token(self, token: str) -> None:
        """Add the token's JTI to the revocation set."""
        try:
            payload = self.verify_token(token)
            jti = payload.get("jti")
            if jti:
                with self._lock:
                    self._revoked.add(jti)
        except (AuthenticationException, SessionExpiredException):
            pass

    def refresh(self, refresh_token: str) -> Tuple[str, str]:
        """Exchange a refresh token for a new access + refresh pair.

        The old refresh token is revoked atomically.

        Returns:
            Tuple of ``(access_token, new_refresh_token)``.
        """
        payload = self.verify_token(refresh_token)
        if payload.get("type") != "refresh":
            raise AuthenticationException("Not a refresh token")

        self.revoke_token(refresh_token)

        claims = {
            k: v
            for k, v in payload.items()
            if k not in ("iat", "exp", "jti", "type")
        }
        return self.create_token(claims), self.create_refresh_token(claims)
