"""HyperLogLog distinct-count sketch (bounded, mergeable, duplicate-insensitive).

Estimator assumptions (documented in docs/architecture.md):
* 64-bit BLAKE2b hash treated as uniformly random over observation keys.
* m = 2^p registers of 1 byte; relative standard error ~ 1.04/sqrt(m)
  (p=8: ~6.5 %, p=10: ~3.3 %, p=12: ~1.6 %).
* Small-range correction: linear counting when E <= 2.5 m and empty registers exist.
* Re-inserting an already-seen key never changes the state (idempotent), so
  replayed/duplicated messages cannot inflate the estimate.
* merge = register-wise max: commutative, associative, idempotent.
"""
from __future__ import annotations

import math

import numpy as np

from core.hashing import h64

_POW = np.array([2.0 ** -r for r in range(65)])


class HLL:
    __slots__ = ("p", "m", "reg")

    def __init__(self, p: int = 8, reg: bytearray | None = None):
        self.p = p
        self.m = 1 << p
        self.reg = reg if reg is not None else bytearray(self.m)

    def add(self, key: str | bytes) -> bool:
        x = h64(key)
        idx = x >> (64 - self.p)
        w = (x << self.p) & ((1 << 64) - 1)
        rank = (64 - self.p + 1) if w == 0 else (65 - w.bit_length())
        rank = min(rank, 64 - self.p + 1)
        if rank > self.reg[idx]:
            self.reg[idx] = rank
            return True
        return False

    def merge_in(self, other: "HLL") -> bool:
        assert self.p == other.p
        if other.reg == self.reg:
            return False
        a = np.frombuffer(self.reg, dtype=np.uint8)
        b = np.frombuffer(other.reg, dtype=np.uint8)
        if (b <= a).all():
            return False
        np.maximum(a, b, out=a)
        return True

    def merged(self, other: "HLL") -> "HLL":
        h = self.copy()
        h.merge_in(other)
        return h

    def dominates(self, other: "HLL") -> bool:
        return bool((np.frombuffer(self.reg, dtype=np.uint8) >= np.frombuffer(other.reg, dtype=np.uint8)).all())

    def copy(self) -> "HLL":
        return HLL(self.p, bytearray(self.reg))

    def estimate(self) -> float:
        m = self.m
        alpha = {16: 0.673, 32: 0.697, 64: 0.709}.get(m, 0.7213 / (1 + 1.079 / m))
        z = float(_POW[np.frombuffer(self.reg, dtype=np.uint8)].sum())
        e = alpha * m * m / z
        zeros = self.reg.count(0)
        if e <= 2.5 * m and zeros:
            e = m * math.log(m / zeros)
        return e

    def is_empty(self) -> bool:
        return not any(self.reg)

    def wire_bytes(self) -> int:
        nz = self.m - self.reg.count(0)
        return 4 + min(self.m, 2 * nz)  # sparse (index,value) pairs vs dense registers

    def key(self) -> bytes:
        return bytes(self.reg)

    @property
    def rse(self) -> float:
        return 1.04 / math.sqrt(self.m)
