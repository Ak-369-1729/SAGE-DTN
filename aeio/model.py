"""Adaptive Emergency Information Object (AEIO)."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from core.hashing import canonical_json, sha256_hex, short_id
from .types import AggregationClass, EventType, Fidelity, PreservationClass, SourceClass


@dataclass(frozen=True)
class AEIO:
    event_id: str
    event_type: EventType
    source_class: SourceClass
    criticality: float
    utility: float
    fidelity_level: Fidelity
    geo_cell: str | None
    freshness: dict | None          # {"observed_at": s, "quantum_s": s}
    confidence: float
    corroboration: int
    preservation_class: PreservationClass
    minimum_fidelity: Fidelity
    semantic_invariants: tuple[str, ...]
    aggregation_class: AggregationClass
    evidence_locator: dict | None
    integrity_commitment: dict | None
    provenance: dict
    sensor_metadata: dict | None
    policy_version: str
    payload: dict = field(default_factory=dict)
    evidence: bytes | None = None   # plaintext high-fidelity evidence (F0 only)

    # ---- convenience -------------------------------------------------
    @property
    def observed_at(self) -> float | None:
        return None if not self.freshness else self.freshness.get("observed_at")

    @property
    def observation_key(self) -> str | None:
        return self.provenance.get("observation_key")

    def header_dict(self) -> dict[str, Any]:
        d = {f.name: getattr(self, f.name) for f in dataclasses.fields(self) if f.name != "evidence"}
        d["semantic_invariants"] = list(self.semantic_invariants)
        return d

    def to_dict(self, with_evidence: bool = False) -> dict[str, Any]:
        d = self.header_dict()
        for k in ("event_type", "source_class", "preservation_class", "aggregation_class"):
            d[k] = getattr(self, k).value
        d["fidelity_level"] = int(self.fidelity_level)
        d["minimum_fidelity"] = int(self.minimum_fidelity)
        if with_evidence and self.evidence is not None:
            d["evidence_hex"] = self.evidence.hex()
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "AEIO":
        d = dict(d)
        ev = d.pop("evidence_hex", None)
        return AEIO(
            event_id=d["event_id"], event_type=EventType(d["event_type"]),
            source_class=SourceClass(d["source_class"]), criticality=d["criticality"],
            utility=d["utility"], fidelity_level=Fidelity(d["fidelity_level"]), geo_cell=d["geo_cell"],
            freshness=d["freshness"], confidence=d["confidence"], corroboration=d["corroboration"],
            preservation_class=PreservationClass(d["preservation_class"]),
            minimum_fidelity=Fidelity(d["minimum_fidelity"]),
            semantic_invariants=tuple(d["semantic_invariants"]),
            aggregation_class=AggregationClass(d["aggregation_class"]),
            evidence_locator=d["evidence_locator"], integrity_commitment=d["integrity_commitment"],
            provenance=d["provenance"], sensor_metadata=d["sensor_metadata"],
            policy_version=d["policy_version"], payload=d.get("payload", {}),
            evidence=bytes.fromhex(ev) if ev else None)

    @cached_property
    def wire_bytes(self) -> int:
        """Encoded size of this representation (canonical JSON header + raw evidence)."""
        return len(canonical_json(self.header_dict())) + (len(self.evidence) if self.evidence else 0)

    @cached_property
    def digest(self) -> str:
        """Content digest of this representation. Transport-only provenance (which
        node happened to ingest a re-submission) is excluded so that duplicate
        submissions of one observation have identical digests."""
        d = self.to_dict(with_evidence=False)
        d["provenance"] = {k: v for k, v in d["provenance"].items() if k != "ingest_node"}
        d["utility"] = 0.0
        return sha256_hex(canonical_json(d))[:16]

    def replace(self, **kw) -> "AEIO":
        return dataclasses.replace(self, **kw)


def make_event_id(observation_key: str) -> str:
    return short_id("event", observation_key)
