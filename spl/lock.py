"""Semantic Preservation Lock (SPL).

Permit(Fi -> Fj) holds iff
  (1) level(Fj) >= level(Fi)        -- SPL governs reductions; upgrades require verified evidence
  (2) level(Fj) <= level(F_min)     -- "Fj >= F_minimum" in fidelity order
  (3) for every required invariant I: extract(I, candidate) == extract(I, source) != None
  (4) candidate.policy_version == registry.policy_version and event_type unchanged
Utility may *propose* any action; only permitted candidates are committed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from aeio import codec
from aeio.model import AEIO
from aeio.types import Fidelity

from .invariants import extract
from .registry import InvariantRegistry, default_registry


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reasons: tuple[str, ...] = ()


@dataclass
class SPLStats:
    attempted: int = 0
    permitted: int = 0
    rejected: int = 0
    clamped: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"attempted": self.attempted, "permitted": self.permitted, "rejected": self.rejected,
                "clamped": self.clamped, "by_reason": dict(self.by_reason)}


def permit(source: AEIO, candidate: AEIO, registry: InvariantRegistry | None = None) -> Decision:
    reg = registry or default_registry()
    rule = reg.rule_for(source.event_type, source.payload)
    reasons: list[str] = []
    if candidate.event_type != source.event_type:
        reasons.append("event_type_changed")
    if candidate.policy_version != reg.policy_version:
        reasons.append("policy_version_mismatch")
    if candidate.fidelity_level < source.fidelity_level:
        reasons.append("upgrade_requires_verified_evidence")
    if candidate.fidelity_level > rule.min_fidelity:
        reasons.append("below_minimum_fidelity")
    for inv in rule.invariants:
        s = extract(inv, source)
        if s is None:
            reasons.append(f"source_missing:{inv}")
        elif extract(inv, candidate) != s:
            reasons.append(f"invariant_lost:{inv}")
    return Decision(not reasons, tuple(reasons))


def permit_levels(event_type, fi: int, fj: int, payload: dict | None = None,
                  registry: InvariantRegistry | None = None, aggregator: str = "sketch") -> bool:
    """Catalogue-level Permit(Fi -> Fj): evaluates the canonical representation at Fj."""
    from aeio.factory import make_aeio
    from aeio.types import EventType, SourceClass
    reg = registry or default_registry()
    if fj < fi:
        return False
    payload = payload or _canonical_payload(EventType(event_type))
    src = make_aeio(event_type, payload, 1000.0, source_class=SourceClass.SURVIVOR,
                    observation_key="catalogue", origin_node="n0", registry=reg, evidence=b"x" * 8,
                    geo_cell=None if "lat" in payload else "C1_1")
    src = codec.reduce(src, fi, aggregator) if fi > 0 else src
    return permit(src, codec.reduce(src, fj, aggregator), reg).allowed


def _canonical_payload(t) -> dict:
    from aeio.types import EventType as E
    base = {"lat": 26.11, "lon": 91.71}
    return {
        E.TRAPPED_PERSON: {**base, "trapped_status": "TRAPPED", "persons": 2, "injury_text": "leg"},
        E.MEDICATION_NEED: {**base, "medication_label": "INSULIN", "urgency": 3, "notes": "x"},
        E.WATER_REQUEST: {**base, "household_size": 4, "notes": "x"},
        E.SAFE_STATUS: {**base, "persons": 3, "message": "ok"},
        E.WATER_LEVEL: {**base, "level_cm": 120.0, "level_bucket": 2, "rate_cm_per_min": 1.0},
        E.SMOKE_DENSITY: {**base, "density_ppm": 300.0, "density_bucket": 2},
        E.COLLAPSE_RISK: {**base, "risk_state": "HIGH", "peak_g": 0.4, "dominant_hz": 3.0},
        E.WATER_SHORTAGE: {"rule_id": "ECP-WATER-1", "magnitude": 60},
        E.POTENTIAL_FIRE_CLUSTER: {"rule_id": "ECP-FIRE-1", "magnitude": 6},
    }[t]


class SemanticPreservationLock:
    """Stateful gate used by nodes. `transition` commits only permitted candidates."""

    def __init__(self, registry: InvariantRegistry | None = None, aggregator: str = "sketch",
                 reducer: Callable[[AEIO, int, str], AEIO] = codec.reduce):
        self.registry = registry or default_registry()
        self.aggregator = aggregator
        self.reducer = reducer
        self.stats = SPLStats()
        self.log: list[dict] = []
        self.keep_log = False

    def check(self, source: AEIO, candidate: AEIO) -> Decision:
        d = permit(source, candidate, self.registry)
        self.stats.attempted += 1
        if d.allowed:
            self.stats.permitted += 1
        else:
            self.stats.rejected += 1
            for r in d.reasons:
                k = r.split(":")[0]
                self.stats.by_reason[k] = self.stats.by_reason.get(k, 0) + 1
        if self.keep_log:
            self.log.append({"event_id": source.event_id, "type": source.event_type.value,
                             "from": int(source.fidelity_level), "to": int(candidate.fidelity_level),
                             "allowed": d.allowed, "reasons": list(d.reasons)})
        return d

    def transition(self, source: AEIO, target: int) -> AEIO:
        """Apply the proposed reduction; if forbidden, clamp to the most-reduced permitted level."""
        target = Fidelity(target)
        if target <= source.fidelity_level:
            return source
        cand = self.reducer(source, target, self.aggregator)
        if self.check(source, cand).allowed:
            return cand
        for lvl in range(int(target) - 1, int(source.fidelity_level), -1):
            cand = self.reducer(source, lvl, self.aggregator)
            if permit(source, cand, self.registry).allowed:
                self.stats.clamped += 1
                return cand
        self.stats.clamped += 1
        return source
