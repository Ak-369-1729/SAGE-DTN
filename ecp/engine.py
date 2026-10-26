"""Emergent Criticality Promotion (ECP).

A deterministic function of (BoundedAggregateState, rule, thresholds, now).
Inputs are duplicate-resistant sketch estimates, so replaying the same
observations cannot raise magnitude, growth or confidence.

Fire condition for cell c:
  UniqueDemand(c)   = |∪ windows retained|            >= T1
  Growth(c)         = |∪ last L windows| / L          >= T2   (unique arrivals per window)
  Confidence(c)     = 0.5 min(1, devices/dev_ref) + 0.5 min(1, ingest_nodes/ing_ref) >= T3
  Fresh(c)          = latest data window >= now_window - freshness_windows
The promoted event is a DERIVED_PROTECTED AEIO with event_id = H(rule_id, cell),
so independent nodes promote the *same* logical event.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from aeio.factory import make_aeio
from aeio.model import AEIO
from aeio.types import EventType, SourceClass
from cpmm.aggregate_state import BoundedAggregateState
from cpmm.hll import HLL
from core.hashing import short_id


@dataclass
class ECPRule:
    rule_id: str
    source_type: str
    derived_type: str
    T1_unique: float
    T2_growth: float
    T3_confidence: float
    lookback_windows: int = 3
    freshness_windows: int = 3
    buckets: list[str] | None = None
    dev_ref: float = 3.0
    ing_ref: float = 2.0


DEFAULT_RULES = [
    ECPRule("ECP-WATER-1", "WATER_REQUEST", "WATER_SHORTAGE", T1_unique=40, T2_growth=2.0,
            T3_confidence=0.6, lookback_windows=3, freshness_windows=3, dev_ref=10, ing_ref=2),
    ECPRule("ECP-FIRE-1", "SMOKE_DENSITY", "POTENTIAL_FIRE_CLUSTER", T1_unique=4, T2_growth=0.5,
            T3_confidence=0.6, lookback_windows=3, freshness_windows=2, buckets=["b2", "b3", "b4"],
            dev_ref=2, ing_ref=1),
]


@dataclass
class ECPMeasure:
    cell: str
    unique: float
    growth: float
    confidence: float
    fresh: bool
    latest_window: int | None

    def to_dict(self):
        return asdict(self)


@dataclass
class ECPEngine:
    rules: list[ECPRule] = field(default_factory=lambda: [ECPRule(**asdict(r)) for r in DEFAULT_RULES])

    @staticmethod
    def _union(st: BoundedAggregateState, etype: str, cell: str, w0: int, w1: int, buckets) -> HLL:
        h = st._new()
        for b in (buckets or ["*"]):
            h.merge_in(st.union(etype, cell, w0, w1, b))
        return h

    def measure(self, st: BoundedAggregateState, rule: ECPRule, cell: str, now: float) -> ECPMeasure:
        w_now = st.window_of(now)
        lo = max(st.max_window - st.windows_kept + 1, 0)
        total = self._union(st, rule.source_type, cell, lo, w_now, rule.buckets).estimate()
        recent = self._union(st, rule.source_type, cell, w_now - rule.lookback_windows + 1, w_now,
                             rule.buckets).estimate()
        dev = st.union(rule.source_type, cell, lo, w_now, "dev").estimate()
        ing = st.union(rule.source_type, cell, lo, w_now, "ing").estimate()
        conf = 0.5 * min(1.0, dev / rule.dev_ref) + 0.5 * min(1.0, ing / rule.ing_ref)
        lw = None
        for b in (rule.buckets or ["*"]):
            x = st.latest_window(rule.source_type, cell, b)
            if x is not None and x <= w_now:
                lw = x if lw is None else max(lw, x)
        fresh = lw is not None and lw >= w_now - rule.freshness_windows
        return ECPMeasure(cell, total, recent / rule.lookback_windows, conf, fresh, lw)

    def evaluate(self, st: BoundedAggregateState, now: float, origin: str = "ecp",
                 thresholds: dict | None = None) -> list[tuple[ECPRule, ECPMeasure]]:
        fired = []
        for rule in self.rules:
            for cell in st.cells(rule.source_type):
                T1, T2, T3 = (thresholds or {}).get((rule.rule_id, cell),
                                                    (rule.T1_unique, rule.T2_growth, rule.T3_confidence))
                m = self.measure(st, rule, cell, now)
                if m.unique >= T1 and m.growth >= T2 and m.confidence >= T3 and m.fresh:
                    fired.append((rule, m))
        return fired

    @staticmethod
    def derived_event(rule: ECPRule, m: ECPMeasure, now: float, origin: str, window_s: int) -> AEIO:
        magnitude = int(round(m.unique / 10.0) * 10) if rule.source_type == "WATER_REQUEST" else int(round(m.unique))
        payload = {"rule_id": rule.rule_id, "magnitude": magnitude,
                   "confidence_bucket": round(m.confidence, 1)}
        obs_t = (m.latest_window if m.latest_window is not None else int(now // window_s)) * window_s
        return make_aeio(EventType(rule.derived_type), payload, obs_t,
                         source_class=SourceClass.AGGREGATE_DERIVED,
                         observation_key=short_id("ecp", rule.rule_id, m.cell), origin_node="ECP",
                         geo_cell=m.cell, confidence=m.confidence,
                         extra_provenance={"derived_from": rule.source_type, "logical_ts": float(obs_t)})
