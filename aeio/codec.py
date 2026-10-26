"""Representation catalogue: how an AEIO looks at each fidelity level.

This reducer is deliberately *semantics-unaware*: it is the generic,
size-driven compressor that a system without SPL would use. SPL decides
whether the representation it produces may be committed.

F0  full record + raw evidence
F1  drop raw evidence and free text; keep locator/commitment
F2  drop precise coordinates and raw numeric values; keep geo_cell, categories, buckets
F3  geo-cell aggregate contribution (individual identity removed)
      aggregator="sketch": carries sketch_key + time window (duplicate-resistant)
      aggregator="naive" : carries count=1 only (what a simple counter keeps)
F4  regional contribution (geo_cell removed)
"""
from __future__ import annotations

import math

from spl.invariants import sketch_key_of

from .model import AEIO
from .types import AggregationClass, Fidelity

FREE_TEXT = {"injury_text", "notes", "message", "contact", "description"}
PRECISE = {"lat", "lon", "level_cm", "rate_cm_per_min", "density_ppm", "peak_g", "dominant_hz",
           "household_size"}
BUCKET_FIELDS = {"level_bucket", "density_bucket", "risk_state"}


def reduce(a: AEIO, level: Fidelity | int, aggregator: str = "sketch") -> AEIO:
    level = Fidelity(level)
    if level <= a.fidelity_level:
        return a  # never "reduce" upward; upgrades need verified evidence
    p = dict(a.payload)
    fresh = dict(a.freshness) if a.freshness else None
    geo, agg = a.geo_cell, a.aggregation_class
    if level >= Fidelity.F1:
        p = {k: v for k, v in p.items() if k not in FREE_TEXT}
    if level >= Fidelity.F2:
        p = {k: v for k, v in p.items() if k not in PRECISE}
    if level >= Fidelity.F3:
        keep = {k: v for k, v in p.items() if k in BUCKET_FIELDS}
        if aggregator == "sketch":
            keep["sketch_key"] = sketch_key_of(a.observation_key or a.event_id)
            if fresh:
                q = fresh.get("quantum_s") or 300
                fresh = {"observed_at": math.floor(fresh["observed_at"] / q) * q, "quantum_s": q}
            agg = AggregationClass.DISTINCT_COUNT if not keep.keys() & BUCKET_FIELDS else AggregationClass.BUCKET_DISTRIBUTION
        else:
            keep["count"] = 1
            fresh = None
            agg = AggregationClass.NAIVE_COUNTER
        p = keep
    if level >= Fidelity.F4:
        p = {k: v for k, v in p.items() if k in ("sketch_key", "count")}
        p["region"] = "R0"
        geo = None
    prov = dict(a.provenance)
    if level >= Fidelity.F3:
        prov = {"origin_node": prov.get("origin_node")}
        if aggregator == "sketch":
            prov["observation_key"] = None
    return a.replace(fidelity_level=level, payload=p, evidence=None, freshness=fresh, geo_cell=geo,
                     aggregation_class=agg, provenance=prov)
