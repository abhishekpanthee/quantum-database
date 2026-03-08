"""
OAuth2 / OpenID Connect Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Configuration holders and flow helpers for enterprise SSO.

This module manages provider registration, authorization URL generation,
and callback handling.  Actual HTTP token-exchange calls are delegated to
the application layer (or ``httpx`` / ``requests`` at integration time).
"""

import secrets
import time
from typing import Any, Dict, List, Optional

from .._standards import AuthenticationException


class OAuth2Provider:
    """Configuration for an OAuth2 / OIDC identity provider."""

    def __init__(
        self,
        provider_id: str,
        name: str,
        *,
        client_id: str = "",
        client_secret: str = "",
        authorization_url: str = "",
        token_url: str = "",
        userinfo_url: str = "",
        jwks_uri: str = "",
        scopes: Optional[List[str]] = None,
        issuer: str = "",
    ):
        self.provider_id = provider_id
        self.name = name
        self.client_id = client_id
        self.client_secret = client_secret
        self.authorization_url = authorization_url
        self.token_url = token_url
        self.userinfo_url = userinfo_url
        self.jwks_uri = jwks_uri
        self.scopes = scopes or ["openid", "profile", "email"]
        self.issuer = issuer

    def build_authorize_url(self, redirect_uri: str, state: str) -> str:
        """Build the authorization redirect URL (RFC 6749 §4.1.1)."""
        params = (
            f"response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
            f"&scope={'+'.join(self.scopes)}"
        )
        return f"{self.authorization_url}?{params}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "client_id": self.client_id,
            "authorization_url": self.authorization_url,
            "token_url": self.token_url,
            "userinfo_url": self.userinfo_url,
            "jwks_uri": self.jwks_uri,
            "scopes": self.scopes,
            "issuer": self.issuer,
        }


class OIDCManager:
    """Manages multiple OAuth2 / OIDC providers for enterprise SSO."""

    STATE_TTL = 600  # 10 minutes

    def __init__(self) -> None:
        self.providers: Dict[str, OAuth2Provider] = {}
        self._pending_states: Dict[str, Dict[str, Any]] = {}

    def register_provider(self, provider: OAuth2Provider) -> None:
        """Register (or replace) an identity provider."""
        self.providers[provider.provider_id] = provider

    def remove_provider(self, provider_id: str) -> None:
        """Unregister an identity provider."""
        self.providers.pop(provider_id, None)

    def initiate_login(
        self, provider_id: str, redirect_uri: str
    ) -> Dict[str, str]:
        """Start an authorization-code flow.

        Returns a dict with ``authorize_url`` and ``state``.
        """
        if provider_id not in self.providers:
            raise ValueError(f"Unknown OAuth2 provider: {provider_id}")

        state = secrets.token_urlsafe(32)
        self._pending_states[state] = {
            "provider_id": provider_id,
            "redirect_uri": redirect_uri,
            "created_at": time.time(),
        }
        url = self.providers[provider_id].build_authorize_url(
            redirect_uri, state
        )
        return {"authorize_url": url, "state": state}

    def handle_callback(
        self, state: str, code: str
    ) -> Dict[str, Any]:
        """Validate the OAuth2 callback and return exchange metadata.

        The caller is responsible for performing the token exchange
        using the returned ``code`` and ``redirect_uri``.

        Raises:
            AuthenticationException: if the state is invalid or expired.
        """
        meta = self._pending_states.pop(state, None)
        if meta is None:
            raise AuthenticationException("Invalid or expired OAuth2 state")

        if time.time() - meta["created_at"] > self.STATE_TTL:
            raise AuthenticationException("OAuth2 state has expired")

        return {
            "provider_id": meta["provider_id"],
            "code": code,
            "redirect_uri": meta["redirect_uri"],
            "status": "token_exchange_required",
        }

    def cleanup_expired_states(self) -> int:
        """Remove expired pending states.  Returns count of purged entries."""
        now = time.time()
        expired = [
            s
            for s, m in self._pending_states.items()
            if now - m["created_at"] > self.STATE_TTL
        ]
        for s in expired:
            del self._pending_states[s]
        return len(expired)
