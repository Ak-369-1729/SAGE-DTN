"""Invariant extractors.

Each extractor maps an AEIO representation to the canonical value of one
semantic invariant, or None when the representation no longer carries it.
SPL compares extractor(candidate) with extractor(source).
"""
from __future__ import annotations

import math
from typing import Callable

from aeio.model import AEIO
from aeio.types import AggregationClass
from core.hashing import short_id


def _payload(field: str) -> Callable[[AEIO], object]:
    return lambda a: a.payload.get(field)


def _usable_location(a: AEIO):
    lat, lon = a.payload.get("lat"), a.payload.get("lon")
    if lat is None or lon is None:
        return None
    return (round(float(lat), 4), round(float(lon), 4))  # ~11 m


def _freshness(a: AEIO):
    if not a.freshness or a.freshness.get("observed_at") is None:
        return None
    q = a.freshness.get("quantum_s") or 300
    return int(math.floor(float(a.freshness["observed_at"]) / q))


def sketch_key_of(observation_key: str) -> str:
    return short_id("sk", observation_key)


def _unique_count_semantics(a: AEIO):
    # an individual record keeps its observation key (exact distinct counting possible);
    # an aggregate contribution must carry the duplicate-resistant sketch key.
    if a.aggregation_class == AggregationClass.NAIVE_COUNTER:
        return None
    if a.payload.get("sketch_key"):
        return a.payload["sketch_key"]
    ok = a.provenance.get("observation_key")
    return sketch_key_of(ok) if ok else None


def _geo_cell(a: AEIO):
    return a.geo_cell


EXTRACTORS: dict[str, Callable[[AEIO], object]] = {
    "trapped_status": _payload("trapped_status"),
    "usable_location": _usable_location,
    "freshness": _freshness,
    "medication_category_or_label": _payload("medication_label"),
    "urgency": _payload("urgency"),
    "water_level_bucket": _payload("level_bucket"),
    "smoke_density_bucket": _payload("density_bucket"),
    "risk_state": _payload("risk_state"),
    "geo_cell": _geo_cell,
    "approximate_unique_count_semantics": _unique_count_semantics,
    "rule_id": _payload("rule_id"),
}


def extract(name: str, a: AEIO):
    return EXTRACTORS[name](a)
