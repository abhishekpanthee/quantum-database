"""
Entanglement-Based Authentication Protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Uses Bell-pair generation and measurement correlation to authenticate
two parties without classical secret exchange.  If an eavesdropper
intercepts the entangled particles, correlation degrades below the
CHSH threshold and the protocol aborts.
"""

import hashlib
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AuthSession:
    """Tracks one entanglement-based authentication attempt."""

    __slots__ = (
        "session_id", "initiator_id", "responder_id",
        "created_at", "state", "correlation",
        "shared_key", "n_pairs",
    )

    def __init__(
        self,
        initiator_id: str,
        responder_id: str,
        n_pairs: int = 128,
    ) -> None:
        self.session_id = uuid.uuid4().hex
        self.initiator_id = initiator_id
        self.responder_id = responder_id
        self.created_at = time.time()
        self.state = "pending"  # pending → measuring → verified | failed
        self.correlation: Optional[float] = None
        self.shared_key: Optional[bytes] = None
        self.n_pairs = n_pairs


class EntanglementAuthProtocol:
    """
    Simulated entanglement-based mutual authentication.

    Flow
    ----
    1.  ``initiate(alice, bob)`` → creates a session and generates
        simulated Bell pairs.
    2.  ``measure(session_id)`` → both parties "measure" in random
        bases.  Matching bases yield a raw shared key; CHSH correlation
        is computed from the rest.
    3.  If correlation > ``chsh_threshold`` (classical max ≈ 2.0,
        quantum max ≈ 2√2 ≈ 2.83), authentication succeeds and
        the shared key is derived via HKDF-like extraction.
    """

    CHSH_THRESHOLD = 2.0  # classical bound; we target ≈2.5 simulated

    def __init__(self, *, session_ttl: float = 60.0) -> None:
        self._sessions: Dict[str, AuthSession] = {}
        self._session_ttl = session_ttl

    def initiate(
        self,
        initiator_id: str,
        responder_id: str,
        *,
        n_pairs: int = 128,
    ) -> str:
        """Start a new authentication session; return session_id."""
        session = AuthSession(initiator_id, responder_id, n_pairs=n_pairs)
        self._sessions[session.session_id] = session
        logger.info(
            "Entanglement auth session %s: %s ↔ %s (%d pairs)",
            session.session_id, initiator_id, responder_id, n_pairs,
        )
        return session.session_id

    def measure(self, session_id: str) -> Dict[str, Any]:
        """
        Simulate Bell-pair measurements and return the result.

        Returns
        -------
        dict with keys: ``session_id``, ``authenticated`` (bool),
        ``correlation`` (float), ``shared_key_hex`` (str | None),
        ``reason`` (str).
        """
        session = self._sessions.get(session_id)
        if session is None:
            return {
                "session_id": session_id,
                "authenticated": False,
                "correlation": 0.0,
                "shared_key_hex": None,
                "reason": "unknown_session",
            }

        if time.time() - session.created_at > self._session_ttl:
            session.state = "failed"
            return {
                "session_id": session_id,
                "authenticated": False,
                "correlation": 0.0,
                "shared_key_hex": None,
                "reason": "session_expired",
            }

        session.state = "measuring"

        # --- simulate measurement outcomes --------------------------------
        n = session.n_pairs
        alice_bases = [int(b) & 1 for b in os.urandom(n)]
        bob_bases = [int(b) & 1 for b in os.urandom(n)]

        matching: List[int] = []
        chsh_vals: List[float] = []

        for i in range(n):
            outcome_byte = os.urandom(1)[0]
            if alice_bases[i] == bob_bases[i]:
                matching.append(outcome_byte & 1)
            else:
                # Non-matching bases contribute to CHSH estimate.
                # Simulate quantum correlation ≈ cos²(π/8) ≈ 0.854
                corr = 1.0 if (outcome_byte % 100) < 85 else -1.0
                chsh_vals.append(corr)

        # Estimate CHSH S value
        if chsh_vals:
            s_estimate = abs(sum(chsh_vals) / len(chsh_vals)) * 2 * 2  # scale
        else:
            s_estimate = 0.0

        session.correlation = round(s_estimate, 4)

        if s_estimate > self.CHSH_THRESHOLD and len(matching) >= 16:
            # Derive shared key from matching bits
            raw = bytes(matching[:32]) if len(matching) >= 32 else bytes(matching)
            session.shared_key = hashlib.sha256(raw).digest()
            session.state = "verified"
            logger.info(
                "Entanglement auth %s succeeded (S=%.3f)",
                session_id, s_estimate,
            )
            return {
                "session_id": session_id,
                "authenticated": True,
                "correlation": session.correlation,
                "shared_key_hex": session.shared_key.hex(),
                "reason": "chsh_exceeded",
            }
        else:
            session.state = "failed"
            logger.warning(
                "Entanglement auth %s failed (S=%.3f, matching=%d)",
                session_id, s_estimate, len(matching),
            )
            return {
                "session_id": session_id,
                "authenticated": False,
                "correlation": session.correlation,
                "shared_key_hex": None,
                "reason": "correlation_too_low",
            }

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        s = self._sessions.get(session_id)
        if s is None:
            return None
        return {
            "session_id": s.session_id,
            "initiator": s.initiator_id,
            "responder": s.responder_id,
            "state": s.state,
            "correlation": s.correlation,
            "created_at": s.created_at,
        }

    def cleanup_expired(self) -> int:
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.created_at > self._session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)
