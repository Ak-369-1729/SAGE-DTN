"""Independent reference oracle for SPL legality (used by E1 and property tests).

Written separately from spl.lock/spl.invariants (direct field access, own
rounding and quantisation) so that E1 does not merely test code against itself.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.hashing import short_id

_REG = json.loads(Path(__file__).with_name("registry_v1.json").read_text())


def _rule(etype: str, payload: dict):
    r = _REG["rules"][etype]
    inv, minf = list(r["invariants"]), r["min_fidelity"]
    c = r.get("protect_if")
    if c and payload.get(c["field"]) in c["in"]:
        minf = c["min_fidelity"]
    return inv, minf


def _val(name: str, d: dict):
    p = d.get("payload") or {}
    if name == "usable_location":
        if "lat" not in p or "lon" not in p or p["lat"] is None or p["lon"] is None:
            return None
        return (int(round(p["lat"] * 10_000)), int(round(p["lon"] * 10_000)))
    if name == "freshness":
        f = d.get("freshness")
        if not f or f.get("observed_at") is None:
            return None
        return int(f["observed_at"] // (f.get("quantum_s") or 300))
    if name == "geo_cell":
        return d.get("geo_cell")
    if name == "approximate_unique_count_semantics":
        if d.get("aggregation_class") == "NAIVE_COUNTER":
            return None
        if p.get("sketch_key"):
            return p["sketch_key"]
        ok = (d.get("provenance") or {}).get("observation_key")
        return short_id("sk", ok) if ok else None
    field = {"trapped_status": "trapped_status", "medication_category_or_label": "medication_label",
             "urgency": "urgency", "water_level_bucket": "level_bucket", "smoke_density_bucket": "density_bucket",
             "risk_state": "risk_state", "rule_id": "rule_id"}[name]
    return p.get(field)


def is_legal(source: dict, candidate: dict) -> bool:
    """source/candidate are AEIO.to_dict() outputs."""
    if candidate["event_type"] != source["event_type"] or candidate["policy_version"] != _REG["policy_version"]:
        return False
    inv, minf = _rule(source["event_type"], source.get("payload") or {})
    if candidate["fidelity_level"] < source["fidelity_level"] or candidate["fidelity_level"] > minf:
        return False
    for i in inv:
        s = _val(i, source)
        if s is None or _val(i, candidate) != s:
            return False
    return True
