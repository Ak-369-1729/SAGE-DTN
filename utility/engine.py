"""Emergency Utility Engine: U_i, resource pressure P, and candidate actions.

UTILITY PROPOSES RESOURCE ACTION. SPL CONTROLS PERMISSIBLE INFORMATION LOSS.
Nothing in this module commits a representation change; callers pass the
proposed target fidelity to spl.lock.SemanticPreservationLock.transition.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from aeio.model import AEIO
from aeio.types import Fidelity, SourceClass

from .config import UtilityConfig


class Action(str, Enum):
    PRESERVE_FULL = "PRESERVE_FULL"
    REDUCE_FIDELITY = "REDUCE_FIDELITY"
    AGGREGATE = "AGGREGATE"
    DEFER = "DEFER"
    REPLICATE = "REPLICATE"
    INCREASE_SENSOR_AGGREGATION = "INCREASE_SENSOR_AGGREGATION"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"


@dataclass
class UtilityContext:
    now: float
    similar_in_cell: int = 0       # scarcity: how many comparable items this node already holds
    geo_priority: float = 0.5      # geographic relevance of the cell (0..1)
    duplicate: bool = False        # the observation is already held
    utility_rose: bool = False


@dataclass
class ResourceState:
    queue_bytes: float = 0.0
    queue_capacity: float = 1.0
    queue_growth_Bps: float = 0.0
    bandwidth_Bps: float = 0.0
    storage_used: float = 0.0
    storage_capacity: float = 1.0
    battery_frac: float = 1.0
    expected_contact_s: float = 0.0
    human_rate_per_min: float = 0.0
    sensor_rate_per_min: float = 0.0


@dataclass
class CandidateAction:
    action: Action
    target_fidelity: Fidelity
    utility: float
    pressure: float
    replicate: bool = False
    defer: bool = False


class UtilityEngine:
    def __init__(self, cfg: UtilityConfig | None = None):
        self.cfg = cfg or UtilityConfig()

    def utility(self, a: AEIO, ctx: UtilityContext, size_bytes: float | None = None) -> float:
        w = self.cfg.utility
        t = a.event_type.value
        obs = a.observed_at
        age = max(0.0, ctx.now - (obs if obs is not None else ctx.now))
        F = math.exp(-age / w.tau_s.get(t, 3600))
        R = w.responder_relevance.get(t, 0.5)
        S = 1.0 / (1.0 + ctx.similar_in_cell)
        G = ctx.geo_priority
        Q = min(1.0, a.confidence * (0.5 + 0.5 * min(1.0, a.corroboration / 3.0))) if a.confidence else 0.0
        K = (size_bytes if size_bytes is not None else a.wire_bytes) / w.cost_ref_bytes
        D = 1.0 if ctx.duplicate else 0.0
        ctxsum = w.w_fresh * F + w.w_resp * R + w.w_scarce * S + w.w_geo * G + w.w_conf * Q
        return a.criticality * ctxsum / (1.0 + w.w_cost * K) * (1.0 - w.w_dup * D)

    def pressure(self, r: ResourceState) -> float:
        w = self.cfg.pressure
        q = min(1.0, r.queue_bytes / max(1.0, r.queue_capacity))
        g = min(1.0, max(0.0, r.queue_growth_Bps) / w.growth_ref_Bps)
        b = 1.0 - min(1.0, r.bandwidth_Bps / w.bandwidth_ref_Bps)
        s = min(1.0, r.storage_used / max(1.0, r.storage_capacity))
        e = 1.0 - max(0.0, min(1.0, r.battery_frac))
        c = 1.0 - min(1.0, r.expected_contact_s / w.contact_ref_s)
        h = min(1.0, r.human_rate_per_min / w.human_rate_ref_per_min)
        z = min(1.0, r.sensor_rate_per_min / w.sensor_rate_ref_per_min)
        p = (w.queue * q + w.growth * g + w.bandwidth * b + w.storage * s + w.energy * e
             + w.contact * c + w.human_rate * h + w.sensor_rate * z)
        return max(0.0, min(1.0, max(p, s, q)))

    def propose(self, a: AEIO, U: float, P: float) -> CandidateAction:
        """Monotone rule: proposed reduction depth grows with pressure and shrinks with utility.
        target_level = floor(5 * P * (1 - Un)), Un = min(1, U / 0.5)."""
        ap = self.cfg.actions
        un = min(1.0, U / 0.5)
        lvl = Fidelity(min(4, int(math.floor(5 * P * (1 - un)))))
        if P < ap.adapt_min_pressure:
            lvl = Fidelity(a.fidelity_level)
        lvl = max(lvl, Fidelity(a.fidelity_level))
        replicate = U >= ap.replicate_min_utility and P <= ap.replicate_max_pressure
        defer = P >= ap.defer_min_pressure and U <= ap.defer_max_utility
        if defer:
            act = Action.DEFER
        elif lvl == a.fidelity_level:
            act = Action.REPLICATE if replicate else Action.PRESERVE_FULL
        elif lvl >= Fidelity.F3:
            act = Action.AGGREGATE
        else:
            act = Action.REDUCE_FIDELITY
        return CandidateAction(act, lvl, U, P, replicate, defer)

    def sensor_action(self, P: float, sensor_rate_per_min: float) -> tuple[Action, float]:
        """Returns (action, publish-period multiplier) for a sensor source."""
        ap = self.cfg.actions
        if P >= ap.sensor_aggregation_pressure:
            return Action.INCREASE_SENSOR_AGGREGATION, min(8.0, 2.0 ** math.ceil((P - ap.sensor_aggregation_pressure) / 0.15 + 1e-9))
        return Action.PRESERVE_FULL, 1.0

    def evidence_action(self, a: AEIO, U: float, ctx: UtilityContext) -> Action | None:
        if (ctx.utility_rose and a.evidence_locator and a.fidelity_level > Fidelity.F0
                and U >= self.cfg.actions.evidence_request_min_utility):
            return Action.REQUEST_EVIDENCE
        return None


def is_sensor(a: AEIO) -> bool:
    return a.source_class in (SourceClass.ENV_SENSOR, SourceClass.STRUCT_SENSOR)
