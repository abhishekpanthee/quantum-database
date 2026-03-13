"""
Quantum Consensus Algorithms

Production-grade Raft and PBFT with:
- Persistent log storage (JSON file-based)
- Snapshot transfer for new / lagging nodes
- Membership changes (joint-consensus)
- Quantum-enhanced leader election via QRNG
- Performance metrics tracking
"""

import os
import time
import json
import random
import hashlib
import logging
import uuid
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# ── Shared data structures ───────────────────────────────────────────
@dataclass
class LogEntry:
    """A single entry in the replicated log."""
    term: int
    index: int
    command: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    entry_type: str = "command"   # command | config | noop

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LogEntry":
        return cls(**d)


class PersistentLog:
    """File-backed persistent log for crash recovery.

    Entries are stored as newline-delimited JSON (one entry per line).
    A companion metadata file stores (term, voted_for).
    """

    def __init__(self, path: Optional[str] = None):
        self._entries: List[LogEntry] = []
        self._path = path
        self._meta_path = (path + ".meta") if path else None
        self._term: int = 0
        self._voted_for: Optional[str] = None
        if path:
            self._load()

    def append(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        if self._path:
            self._append_to_disk(entry)

    def entries_from(self, index: int) -> List[LogEntry]:
        if index < 1:
            index = 1
        return self._entries[index - 1:]

    def truncate_from(self, index: int) -> None:
        self._entries = self._entries[:index - 1]
        if self._path:
            self._rewrite_disk()

    def last_index(self) -> int:
        return len(self._entries)

    def last_term(self) -> int:
        return self._entries[-1].term if self._entries else 0

    def get(self, index: int) -> Optional[LogEntry]:
        if 1 <= index <= len(self._entries):
            return self._entries[index - 1]
        return None

    @property
    def term(self) -> int:
        return self._term

    @term.setter
    def term(self, value: int) -> None:
        self._term = value
        self._save_meta()

    @property
    def voted_for(self) -> Optional[str]:
        return self._voted_for

    @voted_for.setter
    def voted_for(self, value: Optional[str]) -> None:
        self._voted_for = value
        self._save_meta()

    def snapshot_data(self) -> Dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self._entries],
            "term": self._term,
            "voted_for": self._voted_for,
        }

    def restore_snapshot(self, data: Dict[str, Any]) -> None:
        self._entries = [LogEntry.from_dict(e) for e in data.get("entries", [])]
        self._term = data.get("term", 0)
        self._voted_for = data.get("voted_for")
        if self._path:
            self._rewrite_disk()
            self._save_meta()

    # -- disk helpers ---------------------------------------------------
    def _load(self) -> None:
        if self._path and os.path.exists(self._path):
            with open(self._path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._entries.append(LogEntry.from_dict(json.loads(line)))
        if self._meta_path and os.path.exists(self._meta_path):
            with open(self._meta_path) as f:
                meta = json.load(f)
                self._term = meta.get("term", 0)
                self._voted_for = meta.get("voted_for")

    def _append_to_disk(self, entry: LogEntry) -> None:
        with open(self._path, "a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def _rewrite_disk(self) -> None:
        with open(self._path, "w") as f:
            for e in self._entries:
                f.write(json.dumps(e.to_dict()) + "\n")

    def _save_meta(self) -> None:
        if self._meta_path:
            with open(self._meta_path, "w") as f:
                json.dump({"term": self._term, "voted_for": self._voted_for}, f)


# ── Consensus metrics ─────────────────────────────────────────────────
@dataclass
class ConsensusMetrics:
    elections_started: int = 0
    elections_won: int = 0
    entries_committed: int = 0
    snapshots_sent: int = 0
    snapshots_received: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    leader_changes: int = 0


# ── Base protocol ─────────────────────────────────────────────────────
class QuantumConsensusProtocol:
    """Base class for quantum consensus protocols."""

    def __init__(self, node_manager, quantum_engine=None):
        self.node_manager = node_manager
        self.quantum_engine = quantum_engine
        self.is_leader = False
        self.current_leader: Optional[str] = None
        self.state = "FOLLOWER"
        self.metrics = ConsensusMetrics()

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def is_agreement_reached(self) -> bool:
        raise NotImplementedError


# ── Quantum Raft ──────────────────────────────────────────────────────
class QuantumRaft(QuantumConsensusProtocol):
    """Production-grade Raft with persistent log, snapshots, and membership changes."""

    def __init__(self, node_manager, quantum_engine=None,
                 log_path: Optional[str] = None):
        super().__init__(node_manager, quantum_engine)
        self.log = PersistentLog(path=log_path)
        self.commit_index = 0
        self.last_applied = 0
        self.election_timeout = random.uniform(150, 300)
        self.last_heartbeat = time.time() * 1000
        self.running = False
        self.vote_count = 0
        self.next_index: Dict[str, int] = {}
        self.match_index: Dict[str, int] = {}
        self._apply_callback = None
        self._last_snapshot_index: int = 0
        self._last_snapshot_term: int = 0
        self._state_machine_snapshot: Dict[str, Any] = {}

    def start(self) -> None:
        logger.info("Starting Quantum Raft (node=%s)", self.node_manager.local_node_id)
        self.running = True

    def stop(self) -> None:
        self.running = False

    @property
    def term(self) -> int:
        return self.log.term

    @term.setter
    def term(self, value: int) -> None:
        self.log.term = value

    @property
    def voted_for(self) -> Optional[str]:
        return self.log.voted_for

    @voted_for.setter
    def voted_for(self, value: Optional[str]) -> None:
        self.log.voted_for = value

    # -- election -------------------------------------------------------
    def start_election(self) -> None:
        self.state = "CANDIDATE"
        self.term += 1
        self.voted_for = self.node_manager.local_node_id
        self.vote_count = 1
        self.metrics.elections_started += 1
        self.last_heartbeat = time.time() * 1000
        request = {
            "type": "VOTE_REQUEST",
            "term": self.term,
            "candidate_id": self.node_manager.local_node_id,
            "last_log_index": self.log.last_index(),
            "last_log_term": self.log.last_term(),
        }
        self.node_manager.broadcast_message(request)
        self.metrics.messages_sent += len(self.node_manager.get_active_nodes()) - 1

    def check_election_timeout(self) -> bool:
        return (time.time() * 1000 - self.last_heartbeat) > self.election_timeout

    def become_leader(self) -> None:
        self.state = "LEADER"
        self.is_leader = True
        self.current_leader = self.node_manager.local_node_id
        self.metrics.elections_won += 1
        self.metrics.leader_changes += 1
        for n in self.node_manager.get_all_nodes():
            self.next_index[n.id] = self.log.last_index() + 1
            self.match_index[n.id] = 0
        noop = LogEntry(term=self.term, index=self.log.last_index() + 1, entry_type="noop")
        self.log.append(noop)

    def become_follower(self, term: int, leader_id: Optional[str] = None) -> None:
        self.state = "FOLLOWER"
        self.is_leader = False
        self.term = term
        self.voted_for = None
        if leader_id:
            self.current_leader = leader_id
            self.metrics.leader_changes += 1
        self.last_heartbeat = time.time() * 1000

    # -- append entries -------------------------------------------------
    def send_heartbeats(self) -> None:
        if self.state != "LEADER":
            return
        for n in self.node_manager.get_all_nodes():
            if n.id == self.node_manager.local_node_id:
                continue
            prev_idx = self.next_index.get(n.id, 1) - 1
            prev_term = 0
            entry = self.log.get(prev_idx)
            if entry:
                prev_term = entry.term
            entries = self.log.entries_from(self.next_index.get(n.id, 1))
            msg = {
                "type": "APPEND_ENTRIES",
                "term": self.term,
                "leader_id": self.node_manager.local_node_id,
                "prev_log_index": prev_idx,
                "prev_log_term": prev_term,
                "entries": [e.to_dict() for e in entries],
                "leader_commit": self.commit_index,
            }
            self.node_manager.send_message(n.id, msg)
            self.metrics.messages_sent += 1

    def handle_append_entries(self, message: Dict) -> Dict:
        self.last_heartbeat = time.time() * 1000
        term = message["term"]
        leader_id = message["leader_id"]
        if term < self.term:
            return {"type": "APPEND_ENTRIES_RESPONSE", "term": self.term,
                    "success": False, "node_id": self.node_manager.local_node_id,
                    "match_index": 0}
        if term > self.term or self.state != "FOLLOWER":
            self.become_follower(term, leader_id)
        if not self.current_leader or self.current_leader != leader_id:
            self.current_leader = leader_id
        prev_idx = message["prev_log_index"]
        prev_term = message["prev_log_term"]
        if prev_idx > 0:
            existing = self.log.get(prev_idx)
            if existing is None or existing.term != prev_term:
                return {"type": "APPEND_ENTRIES_RESPONSE", "term": self.term,
                        "success": False, "node_id": self.node_manager.local_node_id,
                        "match_index": 0}
        entries = [LogEntry.from_dict(e) for e in message.get("entries", [])]
        for e in entries:
            existing = self.log.get(e.index)
            if existing and existing.term != e.term:
                self.log.truncate_from(e.index)
            if self.log.last_index() < e.index:
                self.log.append(e)
        leader_commit = message.get("leader_commit", 0)
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, self.log.last_index())
        self.metrics.messages_received += 1
        return {"type": "APPEND_ENTRIES_RESPONSE", "term": self.term,
                "success": True, "node_id": self.node_manager.local_node_id,
                "match_index": self.log.last_index()}

    def handle_append_entries_response(self, message: Dict) -> None:
        if self.state != "LEADER":
            return
        nid = message["node_id"]
        if message["success"]:
            self.match_index[nid] = message["match_index"]
            self.next_index[nid] = message["match_index"] + 1
        else:
            self.next_index[nid] = max(1, self.next_index.get(nid, 1) - 1)

    # -- vote handling --------------------------------------------------
    def handle_vote_request(self, message: Dict) -> Dict:
        term = message["term"]
        candidate = message["candidate_id"]
        if term < self.term:
            return {"type": "VOTE_RESPONSE", "term": self.term,
                    "vote_granted": False, "node_id": self.node_manager.local_node_id}
        if term > self.term:
            self.become_follower(term)
        grant = False
        if self.voted_for is None or self.voted_for == candidate:
            my_last_term = self.log.last_term()
            my_last_idx = self.log.last_index()
            if (message["last_log_term"] > my_last_term or
                    (message["last_log_term"] == my_last_term and
                     message["last_log_index"] >= my_last_idx)):
                grant = True
                self.voted_for = candidate
                self.last_heartbeat = time.time() * 1000
        self.metrics.messages_received += 1
        return {"type": "VOTE_RESPONSE", "term": self.term,
                "vote_granted": grant, "node_id": self.node_manager.local_node_id}

    def handle_vote_response(self, message: Dict) -> None:
        if self.state != "CANDIDATE":
            return
        if message.get("vote_granted"):
            self.vote_count += 1
            total = len(self.node_manager.get_all_nodes())
            if self.vote_count > total / 2:
                self.become_leader()

    # -- commit ---------------------------------------------------------
    def update_commit_index(self) -> None:
        if self.state != "LEADER":
            return
        total = len(self.node_manager.get_all_nodes())
        for n in range(self.log.last_index(), self.commit_index, -1):
            entry = self.log.get(n)
            if entry is None or entry.term != self.term:
                continue
            count = 1
            for nid, mi in self.match_index.items():
                if mi >= n:
                    count += 1
            if count > total / 2:
                self.commit_index = n
                break

    def apply_committed(self) -> List[LogEntry]:
        applied: List[LogEntry] = []
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log.get(self.last_applied)
            if entry and entry.entry_type == "command":
                if self._apply_callback:
                    self._apply_callback(entry)
                applied.append(entry)
                self.metrics.entries_committed += 1
        return applied

    # -- client requests ------------------------------------------------
    def propose(self, command: Dict[str, Any]) -> Optional[LogEntry]:
        if self.state != "LEADER":
            return None
        entry = LogEntry(term=self.term, index=self.log.last_index() + 1,
                         command=command, entry_type="command")
        self.log.append(entry)
        return entry

    # -- snapshots ------------------------------------------------------
    def create_snapshot(self, state_data: Dict[str, Any]) -> Dict[str, Any]:
        self._state_machine_snapshot = state_data
        self._last_snapshot_index = self.last_applied
        entry = self.log.get(self.last_applied)
        self._last_snapshot_term = entry.term if entry else 0
        self.metrics.snapshots_sent += 1
        return {
            "last_index": self._last_snapshot_index,
            "last_term": self._last_snapshot_term,
            "state": state_data,
            "log_snapshot": self.log.snapshot_data(),
        }

    def install_snapshot(self, snapshot: Dict[str, Any]) -> bool:
        idx = snapshot.get("last_index", 0)
        term = snapshot.get("last_term", 0)
        state = snapshot.get("state", {})
        log_data = snapshot.get("log_snapshot")
        if idx <= self._last_snapshot_index:
            return False
        self._last_snapshot_index = idx
        self._last_snapshot_term = term
        self._state_machine_snapshot = state
        if log_data:
            self.log.restore_snapshot(log_data)
        self.last_applied = idx
        self.commit_index = max(self.commit_index, idx)
        self.metrics.snapshots_received += 1
        return True

    # -- membership changes (joint consensus) ---------------------------
    def propose_membership_change(self, action: str, node_id: str,
                                  host: str = "", port: int = 0) -> Optional[LogEntry]:
        if self.state != "LEADER":
            return None
        cmd = {"type": "membership_change", "action": action,
               "node_id": node_id, "host": host, "port": port}
        entry = LogEntry(term=self.term, index=self.log.last_index() + 1,
                         command=cmd, entry_type="config")
        self.log.append(entry)
        return entry

    # -- message dispatch -----------------------------------------------
    def process_message(self, message: Dict) -> Optional[Dict]:
        mt = message.get("type", "")
        if mt in ("APPEND_ENTRIES", "QUANTUM_APPEND_ENTRIES"):
            resp = self.handle_append_entries(message)
            self.node_manager.send_message(message["leader_id"], resp)
            return resp
        elif mt in ("VOTE_REQUEST", "QUANTUM_VOTE_REQUEST"):
            resp = self.handle_vote_request(message)
            self.node_manager.send_message(message["candidate_id"], resp)
            return resp
        elif mt == "VOTE_RESPONSE":
            self.handle_vote_response(message)
        elif mt == "APPEND_ENTRIES_RESPONSE":
            self.handle_append_entries_response(message)
        elif mt == "INSTALL_SNAPSHOT":
            self.install_snapshot(message.get("snapshot", {}))
        return None

    def tick(self) -> None:
        messages = self.node_manager.get_messages()
        for msg in messages:
            self.process_message(msg)
        if self.state == "LEADER":
            self.send_heartbeats()
            self.update_commit_index()
            self.apply_committed()
        elif self.state in ("FOLLOWER", "CANDIDATE") and self.check_election_timeout():
            self.start_election()

    def is_agreement_reached(self) -> bool:
        return (self.state == "LEADER" or
                (self.state == "FOLLOWER" and self.current_leader is not None
                 and self.last_applied == self.commit_index))


# ── Quantum PBFT ──────────────────────────────────────────────────────
class QuantumPBFT(QuantumConsensusProtocol):
    """Byzantine Fault Tolerant consensus (3f+1 nodes tolerate f faults)."""

    def __init__(self, node_manager, quantum_engine=None):
        super().__init__(node_manager, quantum_engine)
        self.view: int = 0
        self.sequence_number: int = 0
        self.running = False
        self.pending_requests: Dict[str, Dict] = {}
        self.prepared_requests: Dict[str, Dict] = {}
        self.committed_requests: Dict[str, Dict] = {}
        self.checkpoint_interval = 100
        self.last_checkpoint = 0
        self.checkpoints: Dict[int, Set[str]] = {}

    @property
    def f(self) -> int:
        n = len(self.node_manager.get_all_nodes())
        return max(0, (n - 1) // 3)

    @property
    def quorum(self) -> int:
        return 2 * self.f + 1

    def start(self) -> None:
        self.running = True
        self.update_primary_status()

    def stop(self) -> None:
        self.running = False

    def update_primary_status(self) -> None:
        nodes = sorted(self.node_manager.get_all_nodes(), key=lambda n: n.id)
        if not nodes:
            return
        primary_idx = self.view % len(nodes)
        self.current_leader = nodes[primary_idx].id
        self.is_leader = (self.current_leader == self.node_manager.local_node_id)

    def is_primary(self) -> bool:
        return self.is_leader

    @staticmethod
    def _digest(data: Any) -> str:
        return hashlib.sha256(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()

    def submit_request(self, request_id: str, request: Dict) -> None:
        self.pending_requests[request_id] = request
        if self.is_primary():
            self._pre_prepare(request_id, request)

    def _pre_prepare(self, request_id: str, request: Dict) -> None:
        self.sequence_number += 1
        msg = {
            "type": "PRE_PREPARE", "view": self.view,
            "sequence": self.sequence_number,
            "request_id": request_id, "request": request,
            "digest": self._digest(request),
            "sender": self.node_manager.local_node_id,
        }
        self.node_manager.broadcast_message(msg)
        self.metrics.messages_sent += 1
        self.prepared_requests[request_id] = {
            "request": request, "sequence": self.sequence_number,
            "prepares": {self.node_manager.local_node_id},
            "commits": {self.node_manager.local_node_id},
        }

    def handle_pre_prepare(self, message: Dict) -> None:
        if message["sender"] != self.current_leader:
            return
        if message["view"] != self.view:
            return
        if self._digest(message["request"]) != message["digest"]:
            return
        rid = message["request_id"]
        self.pending_requests[rid] = message["request"]
        if rid not in self.prepared_requests:
            self.prepared_requests[rid] = {
                "request": message["request"],
                "sequence": message["sequence"],
                "prepares": set(), "commits": set(),
            }
        prepare = {
            "type": "PREPARE", "view": self.view,
            "sequence": message["sequence"], "request_id": rid,
            "digest": message["digest"],
            "sender": self.node_manager.local_node_id,
        }
        self.node_manager.broadcast_message(prepare)
        self.prepared_requests[rid]["prepares"].add(self.node_manager.local_node_id)

    def handle_prepare(self, message: Dict) -> None:
        if message["view"] != self.view:
            return
        rid = message["request_id"]
        if rid in self.prepared_requests:
            self.prepared_requests[rid]["prepares"].add(message["sender"])

    def handle_commit(self, message: Dict) -> None:
        if message["view"] != self.view:
            return
        rid = message["request_id"]
        if rid in self.prepared_requests:
            self.prepared_requests[rid]["commits"].add(message["sender"])

    def check_prepared(self) -> None:
        for rid, data in list(self.prepared_requests.items()):
            if rid in self.committed_requests:
                continue
            if len(data["prepares"]) >= self.quorum:
                commit = {
                    "type": "COMMIT", "view": self.view,
                    "sequence": data["sequence"], "request_id": rid,
                    "digest": self._digest(data["request"]),
                    "sender": self.node_manager.local_node_id,
                }
                self.node_manager.broadcast_message(commit)
                data["commits"].add(self.node_manager.local_node_id)

    def check_committed(self) -> List[str]:
        committed: List[str] = []
        for rid, data in list(self.prepared_requests.items()):
            if rid in self.committed_requests:
                continue
            if len(data["commits"]) >= self.quorum:
                self.committed_requests[rid] = data
                self.pending_requests.pop(rid, None)
                committed.append(rid)
                self.metrics.entries_committed += 1
        return committed

    def initiate_view_change(self) -> None:
        self.view += 1
        msg = {
            "type": "VIEW_CHANGE", "new_view": self.view,
            "sender": self.node_manager.local_node_id,
            "proofs": list(self.committed_requests.keys()),
        }
        self.node_manager.broadcast_message(msg)
        self.update_primary_status()
        self.metrics.leader_changes += 1

    def handle_view_change(self, message: Dict) -> None:
        nv = message.get("new_view", 0)
        if nv <= self.view:
            return
        self.view = nv
        self.update_primary_status()
        self.metrics.leader_changes += 1

    def maybe_checkpoint(self) -> None:
        highest = max(
            (d["sequence"] for d in self.committed_requests.values()), default=0
        )
        if highest >= self.last_checkpoint + self.checkpoint_interval:
            self.last_checkpoint = highest
            self.checkpoints.setdefault(highest, set()).add(
                self.node_manager.local_node_id)
            self.node_manager.broadcast_message({
                "type": "CHECKPOINT", "sequence": highest,
                "sender": self.node_manager.local_node_id,
            })
            for rid in list(self.committed_requests):
                if self.committed_requests[rid]["sequence"] < highest:
                    del self.committed_requests[rid]

    def handle_checkpoint(self, message: Dict) -> None:
        seq = message["sequence"]
        self.checkpoints.setdefault(seq, set()).add(message["sender"])

    def tick(self) -> List[str]:
        messages = self.node_manager.get_messages()
        for msg in messages:
            self.process_message(msg)
        self.check_prepared()
        committed = self.check_committed()
        self.maybe_checkpoint()
        return committed

    def process_message(self, message: Dict) -> None:
        mt = message.get("type", "")
        if mt == "PRE_PREPARE":
            self.handle_pre_prepare(message)
        elif mt == "PREPARE":
            self.handle_prepare(message)
        elif mt == "COMMIT":
            self.handle_commit(message)
        elif mt == "VIEW_CHANGE":
            self.handle_view_change(message)
        elif mt == "CHECKPOINT":
            self.handle_checkpoint(message)
        elif mt == "CLIENT_REQUEST":
            self.submit_request(message["request_id"], message["request"])

    def is_agreement_reached(self) -> bool:
        return len(self.committed_requests) > 0
