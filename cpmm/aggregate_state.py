"""BoundedAggregateState: fixed-budget mergeable sketches for aggregatable AEIOs.

Key = (event_type, geo_cell, window, bucket) where bucket is "*" for distinct
counting, a bucket value for distribution classes, or "dev:" for the sketch of
distinct reporting devices/ingest nodes (used for ECP confidence).
Only the last `windows_kept` windows (relative to the max window seen) are
retained, so state is bounded by
  |types| x |cells| x windows_kept x (|buckets|+2) x 2^p bytes.
merge = per-key register max followed by deterministic window pruning; both are
join operations so merge is commutative, associative and idempotent.
"""
from __future__ import annotations

from core.hashing import sha256_hex

from .hll import HLL

Key = tuple  # (etype:str, cell:str, window:int, bucket:str)


class BoundedAggregateState:
    def __init__(self, p: int = 8, window_s: int = 300, windows_kept: int = 48):
        self.p = p
        self.window_s = window_s
        self.windows_kept = windows_kept
        self.sketches: dict[Key, HLL] = {}
        self.max_window = -1
        self.latest: dict[tuple, int] = {}        # derived index (not part of logical state)
        self._sb: dict[Key, int] = {}              # cached encoded size per key
        self.cell_index: dict[str, set] = {}      # derived index

    def window_of(self, t: float) -> int:
        return int(t // self.window_s)

    def _new(self):
        return HLL(self.p)

    def _sk(self, key: Key) -> HLL:
        s = self.sketches.get(key)
        if s is None:
            s = self.sketches[key] = self._new()
        return s

    def add(self, etype: str, cell: str, t: float, sketch_key: str, bucket=None,
            device: str | None = None, ingest: str | None = None) -> list[Key]:
        """Insert one observation; returns the keys whose sketch changed."""
        w = self.window_of(t)
        if w <= self.max_window - self.windows_kept:
            return []
        changed = []
        for b, item in (("*", sketch_key), (None if bucket is None else f"b{bucket}", sketch_key),
                        ("dev", device), ("ing", ingest)):
            if b is None or not item:
                continue
            k = (etype, cell, w, b)
            if self._sk(k).add(item):
                changed.append(k)
                self._touch(k)
        if w > self.max_window:
            self.max_window = w
            self._prune()
        return changed

    def _touch(self, k: Key):
        self._sb[k] = self.sketches[k].wire_bytes() + 24
        idx = (k[0], k[1], k[3])
        if self.latest.get(idx, -1) < k[2]:
            self.latest[idx] = k[2]
        self.cell_index.setdefault(k[0], set()).add(k[1])

    def _prune(self):
        lo = self.max_window - self.windows_kept
        for k in [k for k in self.sketches if k[2] <= lo]:
            del self.sketches[k]
            self._sb.pop(k, None)

    def merge_key(self, key: Key, sk: HLL) -> bool:
        if key[2] <= self.max_window - self.windows_kept:
            return False
        cur = self.sketches.get(key)
        if cur is None:
            self.sketches[key] = sk.copy()
            changed = True
        else:
            changed = cur.merge_in(sk)
        if changed:
            self._touch(key)
        if key[2] > self.max_window:
            self.max_window = key[2]
            self._prune()
        return changed

    def merge_in(self, other: "BoundedAggregateState") -> bool:
        changed = False
        for k, s in other.sketches.items():
            changed |= self.merge_key(k, s)
        return changed

    def copy(self) -> "BoundedAggregateState":
        b = self.__class__(self.p, self.window_s, self.windows_kept)
        b.sketches = {k: v.copy() for k, v in self.sketches.items()}
        b.max_window = self.max_window
        b.latest = dict(self.latest)
        b._sb = dict(self._sb)
        b.cell_index = {k: set(v) for k, v in self.cell_index.items()}
        return b

    # ---- queries ------------------------------------------------------
    def union(self, etype: str, cell: str, w_from: int, w_to: int, bucket: str = "*") -> HLL:
        h = self._new()
        for w in range(w_from, w_to + 1):
            s = self.sketches.get((etype, cell, w, bucket))
            if s is not None:
                h.merge_in(s)
        return h

    def estimate(self, etype: str, cell: str, w_from: int | None = None, w_to: int | None = None,
                 bucket: str = "*") -> float:
        w_from = self.max_window - self.windows_kept + 1 if w_from is None else w_from
        w_to = self.max_window if w_to is None else w_to
        return self.union(etype, cell, w_from, w_to, bucket).estimate()

    def cells(self, etype: str) -> list[str]:
        return sorted(self.cell_index.get(etype, ()))

    def latest_window(self, etype: str, cell: str, bucket: str = "*") -> int | None:
        return self.latest.get((etype, cell, bucket))

    def buckets_in_window(self, etype: str, cell: str, w: int) -> dict[str, float]:
        return {k[3]: s.estimate() for k, s in self.sketches.items()
                if k[0] == etype and k[1] == cell and k[2] == w and k[3].startswith("b")}

    def digest(self) -> str:
        items = sorted((repr(k), v.key().hex()) for k, v in self.sketches.items())
        return sha256_hex(repr((self.max_window, items)).encode())[:16]

    def storage_bytes(self) -> int:
        """Encoded size (sparse or dense HLL encoding, whichever is smaller, + 24 B key)."""
        return sum(self._sb.values())

    def wire_bytes(self, key: Key) -> int:
        return self.sketches[key].wire_bytes() + 24

    def bound_bytes(self, n_types: int, n_cells: int, n_buckets: int) -> int:
        return n_types * n_cells * self.windows_kept * (n_buckets + 3) * (1 << self.p)
