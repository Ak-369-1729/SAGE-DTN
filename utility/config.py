"""Scenario-configurable utility and pressure coefficients.

Model choice (documented in docs/architecture.md §Utility):
  U = C * (wF*F + wR*R + wS*S + wG*G + wQ*Q) / (1 + wK*K) * (1 - wD*D)
* Criticality C multiplies the context terms, so context can re-rank events of
  similar criticality but cannot lift a low-criticality item above a high one
  by more than the bounded context factor (all context terms are in [0,1]).
* The context terms are a convex combination (weights sum to 1): transparent,
  monotone, and each coefficient has a direct operational meaning.
* Cost K divides, so U is a utility-per-cost score usable for byte-budgeted scheduling.
* Duplication D (already-held observation) discounts multiplicatively.
Pressure P is a weighted sum of normalised resource components, floored by the
hard occupancy terms (a full buffer is high pressure regardless of other terms).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class UtilityWeights:
    w_fresh: float = 0.30
    w_resp: float = 0.20
    w_scarce: float = 0.15
    w_geo: float = 0.15
    w_conf: float = 0.20
    w_cost: float = 0.50
    w_dup: float = 0.90
    cost_ref_bytes: float = 2048.0
    tau_s: dict = field(default_factory=lambda: {
        "TRAPPED_PERSON": 7200, "MEDICATION_NEED": 7200, "WATER_REQUEST": 3600, "SAFE_STATUS": 3600,
        "WATER_LEVEL": 900, "SMOKE_DENSITY": 900, "COLLAPSE_RISK": 600,
        "WATER_SHORTAGE": 3600, "POTENTIAL_FIRE_CLUSTER": 1800})
    responder_relevance: dict = field(default_factory=lambda: {
        "TRAPPED_PERSON": 1.0, "MEDICATION_NEED": 0.9, "WATER_REQUEST": 0.5, "SAFE_STATUS": 0.3,
        "WATER_LEVEL": 0.6, "SMOKE_DENSITY": 0.6, "COLLAPSE_RISK": 0.8,
        "WATER_SHORTAGE": 1.0, "POTENTIAL_FIRE_CLUSTER": 1.0})


@dataclass
class PressureWeights:
    queue: float = 0.25
    growth: float = 0.10
    bandwidth: float = 0.10
    storage: float = 0.20
    energy: float = 0.15
    contact: float = 0.05
    human_rate: float = 0.05
    sensor_rate: float = 0.10
    growth_ref_Bps: float = 200.0
    bandwidth_ref_Bps: float = 2000.0
    contact_ref_s: float = 600.0
    human_rate_ref_per_min: float = 5.0
    sensor_rate_ref_per_min: float = 10.0


@dataclass
class ActionPolicy:
    replicate_min_utility: float = 0.45
    replicate_max_pressure: float = 0.6
    defer_min_pressure: float = 0.75
    defer_max_utility: float = 0.08
    evidence_request_min_utility: float = 0.6
    sensor_aggregation_pressure: float = 0.5
    adapt_min_pressure: float = 0.2


@dataclass
class UtilityConfig:
    utility: UtilityWeights = field(default_factory=UtilityWeights)
    pressure: PressureWeights = field(default_factory=PressureWeights)
    actions: ActionPolicy = field(default_factory=ActionPolicy)

    @classmethod
    def from_dict(cls, d: dict | None) -> "UtilityConfig":
        d = d or {}
        return cls(UtilityWeights(**d.get("utility", {})), PressureWeights(**d.get("pressure", {})),
                   ActionPolicy(**d.get("actions", {})))

    def to_dict(self) -> dict:
        return asdict(self)
