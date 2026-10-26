"""ProtectedMap: individually addressable protected records.

Each event_id maps to a multi-value register of AEIO versions. The order on
versions is (logical_ts, fidelity_rank) where higher fidelity ranks higher.
merge(A,B) keeps, per key, the set of maximal versions of A ∪ B. This is a
join-semilattice, so merge is commutative, associative and idempotent.
Concurrent maximal versions with different content are retained and reported
by `conflicts()` instead of being silently averaged or overwritten.
"""
from __future__ import annotations

from aeio.model import AEIO
from core.hashing import sha256_hex


def order_key(a: AEIO) -> tuple:
    ts = a.provenance.get("logical_ts", a.observed_at or 0.0)
    return (float(ts), -int(a.fidelity_level))


class ProtectedMap:
    def __init__(self):
        self.entries: dict[str, dict[str, AEIO]] = {}  # event_id -> {digest: AEIO}

    def __len__(self) -> int:
        return len(self.entries)

    def put(self, a: AEIO) -> bool:
        """Insert a version; returns True if logical state changed."""
        cur = self.entries.get(a.event_id)
        if cur is None:
            self.entries[a.event_id] = {a.digest: a}
            return True
        if a.digest in cur:
            return False
        k = order_key(a)
        best = order_key(next(iter(cur.values())))
        if k < best:
            return False
        if k > best:
            self.entries[a.event_id] = {a.digest: a}
        else:
            cur[a.digest] = a
        return True

    def get(self, event_id: str) -> list[AEIO]:
        return sorted(self.entries.get(event_id, {}).values(), key=lambda a: a.digest)

    def best(self, event_id: str) -> AEIO | None:
        v = self.get(event_id)
        return v[0] if v else None

    def best_key(self, event_id: str) -> tuple | None:
        cur = self.entries.get(event_id)
        return order_key(next(iter(cur.values()))) if cur else None

    def merge_in(self, other: "ProtectedMap") -> int:
        changed = 0
        for vs in other.entries.values():
            for a in vs.values():
                changed += self.put(a)
        return changed

    def copy(self) -> "ProtectedMap":
        pm = ProtectedMap()
        pm.entries = {k: dict(v) for k, v in self.entries.items()}
        return pm

    def conflicts(self) -> list[str]:
        return sorted(k for k, v in self.entries.items() if len(v) > 1)

    def digest(self) -> str:
        items = sorted((k, sorted(v)) for k, v in self.entries.items())
        return sha256_hex(repr(items).encode())[:16]

    def storage_bytes(self) -> int:
        return sum(a.wire_bytes for vs in self.entries.values() for a in vs.values())
