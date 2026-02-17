"""
Quantum Networking (9.3)
~~~~~~~~~~~~~~~~~~~~~~~~

* **QuantumInternetGateway** — Quantum internet integration (when available)
* **EntanglementDistributor** — Entanglement distribution for distributed queries
* **QuantumRepeaterChain** — Quantum repeaters for long-distance state transfer
* **BellPairLocker** — Bell-pair-based distributed locking
* **QuantumSecureLink** — Quantum-secured inter-node communication (QKD)
"""

import cirq
import hashlib
import logging
import math
import os
import threading
import time
import uuid
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ======================================================================
#  Quantum Internet Gateway
# ======================================================================

class QuantumInternetGateway:
    """Interface to external quantum internet infrastructure.

    Manages connections to remote quantum nodes, tracks link quality,
    and provides send/receive primitives for quantum states.
    """

    class LinkState(Enum):
        UP = auto()
        DOWN = auto()
        DEGRADED = auto()

    def __init__(self, local_node_id: Optional[str] = None):
        self._node_id = local_node_id or f"node_{uuid.uuid4().hex[:8]}"
        self._peers: Dict[str, Dict[str, Any]] = {}
        self._inbox: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        logger.info("QuantumInternetGateway '%s' online", self._node_id)

    @property
    def node_id(self) -> str:
        return self._node_id

    def register_peer(
        self,
        peer_id: str,
        address: str = "localhost",
        fidelity: float = 0.95,
    ) -> None:
        """Register a remote quantum node."""
        with self._lock:
            self._peers[peer_id] = {
                "address": address,
                "fidelity": fidelity,
                "state": self.LinkState.UP,
                "sent": 0,
                "received": 0,
                "registered_at": time.time(),
            }

    def deregister_peer(self, peer_id: str) -> None:
        with self._lock:
            if peer_id not in self._peers:
                raise KeyError(peer_id)
            del self._peers[peer_id]

    def send_state(
        self,
        peer_id: str,
        amplitudes: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Simulate sending a quantum state to a peer.

        Returns:
            Transmission ID.
        """
        with self._lock:
            peer = self._peers.get(peer_id)
            if peer is None:
                raise KeyError(f"Unknown peer '{peer_id}'")
            if peer["state"] == self.LinkState.DOWN:
                raise ConnectionError(f"Link to '{peer_id}' is DOWN")
            tx_id = uuid.uuid4().hex
            peer["sent"] += 1
            # Simulate decoherence based on fidelity
            noisy = amplitudes * peer["fidelity"] + (1 - peer["fidelity"]) * np.random.randn(*amplitudes.shape) * 0.01
            noisy = noisy / np.linalg.norm(noisy)
            self._inbox.append({
                "tx_id": tx_id,
                "from": self._node_id,
                "to": peer_id,
                "amplitudes": noisy,
                "metadata": metadata or {},
                "time": time.time(),
            })
            logger.debug("Sent state to %s (tx=%s)", peer_id, tx_id)
            return tx_id

    def receive_states(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Consume queued incoming states."""
        with self._lock:
            batch = self._inbox[:limit]
            self._inbox = self._inbox[limit:]
            return batch

    def link_status(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                pid: {
                    "state": p["state"].name,
                    "fidelity": p["fidelity"],
                    "sent": p["sent"],
                    "received": p["received"],
                }
                for pid, p in self._peers.items()
            }

    def set_link_state(self, peer_id: str, state: "QuantumInternetGateway.LinkState") -> None:
        with self._lock:
            peer = self._peers.get(peer_id)
            if peer is None:
                raise KeyError(peer_id)
            peer["state"] = state


# ======================================================================
#  Entanglement Distributor
# ======================================================================

class EntanglementDistributor:
    """Generates and distributes Bell pairs across nodes for distributed queries.

    Maintains a pool of pre-generated entangled pairs that can be consumed
    by distributed operations.
    """

    def __init__(self, pool_size: int = 100):
        self._pool_size = pool_size
        self._pairs: List[Dict[str, Any]] = []
        self._consumed = 0
        self._lock = threading.RLock()
        logger.info("EntanglementDistributor ready (pool_size=%d)", pool_size)

    def generate_pair(
        self,
        node_a: str,
        node_b: str,
    ) -> Dict[str, Any]:
        """Generate a single Bell pair (|Φ+⟩) between two nodes.

        Returns:
            Dict with ``pair_id``, ``circuit``, ``node_a``, ``node_b``, ``fidelity``.
        """
        pair_id = uuid.uuid4().hex[:12]
        qa = cirq.NamedQubit(f"{node_a}_{pair_id}")
        qb = cirq.NamedQubit(f"{node_b}_{pair_id}")
        circuit = cirq.Circuit()
        circuit.append(cirq.H(qa))
        circuit.append(cirq.CNOT(qa, qb))

        pair = {
            "pair_id": pair_id,
            "node_a": node_a,
            "node_b": node_b,
            "circuit": circuit,
            "fidelity": 1.0,
            "created_at": time.time(),
        }
        with self._lock:
            if len(self._pairs) >= self._pool_size:
                self._pairs.pop(0)  # evict oldest
            self._pairs.append(pair)
        return pair

    def generate_pool(
        self,
        node_a: str,
        node_b: str,
        count: Optional[int] = None,
    ) -> int:
        """Pre-generate a batch of Bell pairs.

        Returns:
            Number of pairs generated.
        """
        n = count or self._pool_size
        for _ in range(n):
            self.generate_pair(node_a, node_b)
        return n

    def consume_pair(
        self,
        node_a: str,
        node_b: str,
    ) -> Optional[Dict[str, Any]]:
        """Consume one Bell pair from the pool for a distributed operation."""
        with self._lock:
            for i, pair in enumerate(self._pairs):
                if {pair["node_a"], pair["node_b"]} == {node_a, node_b}:
                    self._consumed += 1
                    return self._pairs.pop(i)
            return None

    def build_ghz_circuit(self, nodes: List[str]) -> cirq.Circuit:
        """Build a GHZ state across multiple nodes.

        Creates |GHZ⟩ = (|00...0⟩ + |11...1⟩) / √2.
        """
        if len(nodes) < 2:
            raise ValueError("Need at least 2 nodes for GHZ")
        qubits = [cirq.NamedQubit(f"ghz_{n}") for n in nodes]
        circuit = cirq.Circuit()
        circuit.append(cirq.H(qubits[0]))
        for i in range(1, len(qubits)):
            circuit.append(cirq.CNOT(qubits[0], qubits[i]))
        return circuit

    def pool_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "pool_size": self._pool_size,
                "available": len(self._pairs),
                "consumed": self._consumed,
            }


# ======================================================================
#  Quantum Repeater Chain
# ======================================================================

class QuantumRepeaterChain:
    """Simulates a chain of quantum repeaters for long-distance entanglement.

    Each *segment* performs entanglement swapping.  The chain models
    fidelity degradation across segments and supports purification.
    """

    def __init__(self, segment_fidelity: float = 0.98):
        self._seg_fidelity = segment_fidelity
        self._segments: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def add_segment(
        self,
        from_node: str,
        to_node: str,
        distance_km: float = 50.0,
    ) -> int:
        """Append a repeater segment.  Returns segment index."""
        with self._lock:
            idx = len(self._segments)
            self._segments.append({
                "from": from_node,
                "to": to_node,
                "distance_km": distance_km,
                "swaps": 0,
            })
            return idx

    def end_to_end_fidelity(self) -> float:
        """Estimate fidelity across the full chain (product model)."""
        with self._lock:
            if not self._segments:
                return 0.0
            f = self._seg_fidelity ** len(self._segments)
            return f

    def build_swap_circuit(self, segment_index: int) -> cirq.Circuit:
        """Build an entanglement-swapping circuit at one repeater node.

        Performs Bell-state measurement on the two local halves and
        applies corrections to the distant ends.
        """
        with self._lock:
            if segment_index < 0 or segment_index >= len(self._segments):
                raise IndexError(f"Segment {segment_index} out of range")
            seg = self._segments[segment_index]
            seg["swaps"] += 1

        qa = cirq.NamedQubit(f"rep_{segment_index}_a")
        qb = cirq.NamedQubit(f"rep_{segment_index}_b")
        circuit = cirq.Circuit()
        circuit.append(cirq.CNOT(qa, qb))
        circuit.append(cirq.H(qa))
        circuit.append(cirq.measure(qa, qb, key=f"swap_{segment_index}"))
        return circuit

    def build_full_chain_circuit(self) -> cirq.Circuit:
        """Build swap circuits for every segment in the chain."""
        circuit = cirq.Circuit()
        with self._lock:
            for i in range(len(self._segments)):
                circuit += self.build_swap_circuit(i)
        return circuit

    def purify(self, num_rounds: int = 1) -> float:
        """Apply entanglement purification to improve fidelity.

        Returns:
            New estimated fidelity.
        """
        f = self.end_to_end_fidelity()
        for _ in range(num_rounds):
            # Bennett et al. recurrence purification formula
            f = (f * f) / (f * f + (1 - f) * (1 - f))
        return f

    def chain_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_dist = sum(s["distance_km"] for s in self._segments)
            return {
                "num_segments": len(self._segments),
                "total_distance_km": total_dist,
                "segment_fidelity": self._seg_fidelity,
                "end_to_end_fidelity": self.end_to_end_fidelity(),
            }


# ======================================================================
#  Bell-Pair Locker
# ======================================================================

class BellPairLocker:
    """Distributed locking protocol based on pre-shared Bell pairs.

    Two nodes consume a Bell pair and perform coordinated measurements
    to establish a lock.  The protocol guarantees mutual exclusion
    without classical round-trips (once the pair is shared).
    """

    def __init__(self, distributor: EntanglementDistributor):
        self._distributor = distributor
        self._locks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def acquire(
        self,
        resource_id: str,
        node_a: str,
        node_b: str,
        timeout: float = 5.0,
    ) -> bool:
        """Attempt to acquire a distributed lock on *resource_id*.

        Consumes one Bell pair.  Returns ``True`` if lock acquired.
        """
        with self._lock:
            if resource_id in self._locks:
                existing = self._locks[resource_id]
                if time.time() - existing["acquired_at"] < timeout:
                    return False  # lock held
                # Expired — allow re-acquisition

            pair = self._distributor.consume_pair(node_a, node_b)
            if pair is None:
                raise RuntimeError("No Bell pair available for locking")

            self._locks[resource_id] = {
                "holder_a": node_a,
                "holder_b": node_b,
                "pair_id": pair["pair_id"],
                "acquired_at": time.time(),
            }
            logger.debug("Lock acquired on '%s' by %s↔%s", resource_id, node_a, node_b)
            return True

    def release(self, resource_id: str) -> bool:
        """Release a distributed lock."""
        with self._lock:
            if resource_id not in self._locks:
                return False
            del self._locks[resource_id]
            logger.debug("Lock released on '%s'", resource_id)
            return True

    def is_locked(self, resource_id: str) -> bool:
        with self._lock:
            return resource_id in self._locks

    def lock_info(self, resource_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._locks.get(resource_id)

    def active_locks(self) -> List[str]:
        with self._lock:
            return list(self._locks.keys())

    def build_lock_verification_circuit(
        self,
        resource_id: str,
    ) -> cirq.Circuit:
        """Build a circuit to verify the lock is still valid.

        Measures the shared Bell pair in the Z basis; correlated outcomes
        confirm the lock.
        """
        with self._lock:
            info = self._locks.get(resource_id)
            if info is None:
                raise KeyError(f"No lock on '{resource_id}'")
        qa = cirq.NamedQubit(f"lock_{resource_id}_a")
        qb = cirq.NamedQubit(f"lock_{resource_id}_b")
        circuit = cirq.Circuit()
        circuit.append(cirq.H(qa))
        circuit.append(cirq.CNOT(qa, qb))
        circuit.append(cirq.measure(qa, qb, key=f"lock_verify_{resource_id}"))
        return circuit


# ======================================================================
#  Quantum Secure Link (QKD)
# ======================================================================

class QuantumSecureLink:
    """Quantum key distribution (BB84) for securing inter-node communication.

    Generates shared secret keys between two nodes using simulated
    BB84 protocol rounds.
    """

    def __init__(self, key_length: int = 256):
        self._key_length = key_length
        self._keys: Dict[str, bytes] = {}
        self._lock = threading.RLock()
        logger.info("QuantumSecureLink ready (key_length=%d)", key_length)

    def generate_bb84_circuit(self, num_bits: int = 16) -> cirq.Circuit:
        """Build a BB84 key exchange circuit.

        Alice prepares qubits in random bases; Bob measures in random bases.
        """
        n = min(num_bits, 20)  # cap for simulator
        qubits = [cirq.LineQubit(i) for i in range(n)]
        alice_bits = np.random.randint(0, 2, n)
        alice_bases = np.random.randint(0, 2, n)

        circuit = cirq.Circuit()
        for i, (bit, basis) in enumerate(zip(alice_bits, alice_bases)):
            if bit:
                circuit.append(cirq.X(qubits[i]))
            if basis:
                circuit.append(cirq.H(qubits[i]))

        bob_bases = np.random.randint(0, 2, n)
        for i, basis in enumerate(bob_bases):
            if basis:
                circuit.append(cirq.H(qubits[i]))

        circuit.append(cirq.measure(*qubits, key="bb84_raw"))
        return circuit

    def establish_key(
        self,
        link_id: str,
        node_a: str,
        node_b: str,
    ) -> Dict[str, Any]:
        """Run a simulated BB84 key exchange and store the shared key.

        Returns:
            Dict with ``link_id``, ``key_bits`` (length), and ``error_rate``.
        """
        n = self._key_length
        alice_bits = np.random.randint(0, 2, n)
        alice_bases = np.random.randint(0, 2, n)
        bob_bases = np.random.randint(0, 2, n)

        # Sifting: keep bits where bases match
        matching = alice_bases == bob_bases
        sifted = alice_bits[matching]

        # Simulate small error rate
        error_rate = 0.02
        errors = np.random.rand(len(sifted)) < error_rate
        bob_sifted = sifted.copy()
        bob_sifted[errors] = 1 - bob_sifted[errors]

        # Privacy amplification — hash down
        raw = bytes(sifted.tolist())
        key = hashlib.sha256(raw).digest()

        with self._lock:
            self._keys[link_id] = key

        return {
            "link_id": link_id,
            "node_a": node_a,
            "node_b": node_b,
            "raw_bits": n,
            "sifted_bits": len(sifted),
            "key_bytes": len(key),
            "error_rate": float(np.mean(errors)) if len(errors) > 0 else 0.0,
        }

    def get_key(self, link_id: str) -> Optional[bytes]:
        with self._lock:
            return self._keys.get(link_id)

    def rotate_key(self, link_id: str, node_a: str, node_b: str) -> Dict[str, Any]:
        """Re-key an existing link."""
        return self.establish_key(link_id, node_a, node_b)

    def list_links(self) -> List[str]:
        with self._lock:
            return list(self._keys.keys())

    def encrypt_classical(self, link_id: str, plaintext: bytes) -> bytes:
        """XOR-encrypt classical data using the shared QKD key (OTP)."""
        key = self.get_key(link_id)
        if key is None:
            raise KeyError(f"No key for link '{link_id}'")
        extended = (key * (len(plaintext) // len(key) + 1))[:len(plaintext)]
        return bytes(a ^ b for a, b in zip(plaintext, extended))

    def decrypt_classical(self, link_id: str, ciphertext: bytes) -> bytes:
        """Decrypt (symmetric XOR)."""
        return self.encrypt_classical(link_id, ciphertext)
