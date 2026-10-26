"""Hypothesis strategies: random AEIOs and random (legal or illegal) transformations."""
from __future__ import annotations

import random

from hypothesis import strategies as st

from aeio import codec
from aeio.factory import make_aeio
from aeio.types import EventType, Fidelity, SourceClass
from spl.lock import _canonical_payload

ETYPES = list(EventType)


@st.composite
def aeios(draw):
    t = draw(st.sampled_from(ETYPES))
    p = dict(_canonical_payload(t))
    if "lat" in p:
        p["lat"] = draw(st.floats(26.0, 26.3))
        p["lon"] = draw(st.floats(91.6, 91.9))
    if t == EventType.COLLAPSE_RISK:
        p["risk_state"] = draw(st.sampled_from(["LOW", "ELEVATED", "HIGH"]))
    if t == EventType.MEDICATION_NEED:
        p["urgency"] = draw(st.integers(1, 3))
    ev = draw(st.one_of(st.none(), st.binary(min_size=1, max_size=64)))
    obs = draw(st.floats(0, 20000))
    a = make_aeio(t, p, obs, source_class=SourceClass.SURVIVOR, observation_key=f"k{draw(st.integers(0, 10**6))}",
                  origin_node="n1", evidence=ev, geo_cell=None if "lat" in p else "C3_4")
    start = draw(st.sampled_from([0, 0, 1, 2]))
    return codec.reduce(a, start) if start else a


MUTATIONS = ["reduce_sketch", "reduce_naive", "drop_field", "perturb_field", "drop_freshness",
             "shift_freshness", "drop_geo", "change_type", "upgrade", "bad_policy", "identity"]


def mutate(a, kind: str, rng: random.Random, target: int):
    if kind == "reduce_sketch":
        return codec.reduce(a, target, "sketch")
    if kind == "reduce_naive":
        return codec.reduce(a, target, "naive")
    if kind == "drop_field" and a.payload:
        k = rng.choice(sorted(a.payload))
        return a.replace(payload={x: v for x, v in a.payload.items() if x != k}, fidelity_level=Fidelity(max(a.fidelity_level, target)))
    if kind == "perturb_field" and a.payload:
        k = rng.choice(sorted(a.payload))
        v = a.payload[k]
        nv = (v + 1.0) if isinstance(v, (int, float)) else (str(v) + "_x")
        return a.replace(payload={**a.payload, k: nv}, fidelity_level=Fidelity(max(a.fidelity_level, target)))
    if kind == "drop_freshness":
        return a.replace(freshness=None, fidelity_level=Fidelity(max(a.fidelity_level, target)))
    if kind == "shift_freshness" and a.freshness:
        return a.replace(freshness={**a.freshness, "observed_at": a.freshness["observed_at"] + 3600})
    if kind == "drop_geo":
        return a.replace(geo_cell=None)
    if kind == "change_type":
        return a.replace(event_type=EventType.SAFE_STATUS if a.event_type != EventType.SAFE_STATUS else EventType.WATER_REQUEST)
    if kind == "upgrade" and a.fidelity_level > 0:
        return a.replace(fidelity_level=Fidelity(int(a.fidelity_level) - 1))
    if kind == "bad_policy":
        return a.replace(policy_version="SPL-0.9.0")
    return a.replace(fidelity_level=Fidelity(max(a.fidelity_level, target)))
