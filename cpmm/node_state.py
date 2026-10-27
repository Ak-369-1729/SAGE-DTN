"""NodeState = ProtectedMap ∪ BoundedAggregateState ∪ EvidenceStore, with deterministic merge."""
from __future__ import annotations

from core.hashing import sha256_hex

from .aggregate_state import BoundedAggregateState
from .evidence_store import EvidenceStore
from .protected_map import ProtectedMap


class NodeState:
    def __init__(self, p: int = 8, window_s: int = 300, windows_kept: int = 48):
        self.protected = ProtectedMap()
        self.aggregate = BoundedAggregateState(p, window_s, windows_kept)
        self.evidence = EvidenceStore()

    def copy(self) -> "NodeState":
        n = NodeState.__new__(NodeState)
        n.protected = self.protected.copy()
        n.aggregate = self.aggregate.copy()
        n.evidence = EvidenceStore()
        n.evidence.records = dict(self.evidence.records)
        return n

    def merge_in(self, other: "NodeState") -> None:
        """Merges propagated logical state. EvidenceStore is *not* propagated by merge;
        evidence moves only by explicit replication/recovery."""
        self.protected.merge_in(other.protected)
        self.aggregate.merge_in(other.aggregate)

    def logical_digest(self) -> str:
        return sha256_hex(f"{self.protected.digest()}|{self.aggregate.digest()}".encode())[:16]


def merge(a: NodeState, b: NodeState) -> NodeState:
    out = a.copy()
    out.merge_in(b)
    return out
