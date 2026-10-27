"""Exact (unbounded) distinct-count state with the BoundedAggregateState interface.

Used only as an oracle / reference in experiments (ground truth for ECP and
for measuring sketch error). It is NOT bounded and is not part of the node.
"""
from __future__ import annotations

from .aggregate_state import BoundedAggregateState


class ExactSet:
    __slots__ = ("s",)

    def __init__(self, s=None):
        self.s = set() if s is None else s

    def add(self, key) -> bool:
        if key in self.s:
            return False
        self.s.add(key)
        return True

    def merge_in(self, other: "ExactSet") -> bool:
        n = len(self.s)
        self.s |= other.s
        return len(self.s) != n

    def copy(self) -> "ExactSet":
        return ExactSet(set(self.s))

    def estimate(self) -> float:
        return float(len(self.s))

    def key(self) -> bytes:
        return repr(sorted(self.s)).encode()

    def wire_bytes(self) -> int:
        return 8 * len(self.s)

    @property
    def m(self) -> int:
        return 8 * len(self.s)


class ExactAggregateState(BoundedAggregateState):
    def _new(self):
        return ExactSet()
