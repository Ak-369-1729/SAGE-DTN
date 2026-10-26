"""Conditional evidence recovery protocol objects and replica placement policy."""
from __future__ import annotations

from dataclasses import dataclass, field

from .auth import AuthToken
from .commitment import EvidenceLocator

REQUEST_BYTES = 96  # locator id + token + requester + timestamp


@dataclass
class RecoveryRequest:
    locator: EvidenceLocator
    token: AuthToken
    requester: str
    created_at: float

    @property
    def rid(self) -> str:
        return f"{self.locator.evidence_id}:{self.requester}"


@dataclass
class RecoveryOutcome:
    evidence_id: str
    requested_at: float
    recovered_at: float | None = None
    holder: str | None = None
    integrity_failures: int = 0
    bytes: int = 0
    attempts: list = field(default_factory=list)


@dataclass
class ReplicaPolicy:
    replicas: int = 3
    prefer_roles: tuple = ("FERRY", "FIELD", "SENSOR")

    def choose(self, peers: list[tuple[str, str, float]], already: set[str], k: int) -> list[str]:
        """peers: (node_id, role, free_bytes). Deterministic: role preference, free space, id."""
        rank = {r: i for i, r in enumerate(self.prefer_roles)}
        cand = [p for p in peers if p[0] not in already and p[1] in rank and p[2] > 0]
        cand.sort(key=lambda p: (rank[p[1]], -p[2], p[0]))
        return [p[0] for p in cand[:k]]
