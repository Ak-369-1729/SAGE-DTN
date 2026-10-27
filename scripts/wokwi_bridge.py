"""Bridge: sage.aeio.v1 JSON lines (Wokwi serial / ESP32 / virtual sensors) -> AEIO -> SPL -> CPMM NodeState -> ECP.

    python scripts/wokwi_bridge.py --input serial_log.txt
    python scripts/virtual_sensor_demo.py | python scripts/wokwi_bridge.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aeio.factory import make_aeio  # noqa: E402
from aeio.types import EventType, Fidelity, SourceClass  # noqa: E402
from cpmm.node_state import NodeState  # noqa: E402
from ecp.engine import ECPEngine  # noqa: E402
from spl.lock import SemanticPreservationLock  # noqa: E402

BUCKET_FIELD = {"WATER_LEVEL": "level_bucket", "SMOKE_DENSITY": "density_bucket", "COLLAPSE_RISK": "risk_state"}
RISK = {0: "LOW", 1: "ELEVATED", 2: "HIGH"}


def to_aeio(d: dict):
    et = d["event_type"]
    b = d.get("bucket")
    payload = {"lat": d["lat"], "lon": d["lon"], "sensor_id": d.get("origin_node")}
    if et in BUCKET_FIELD:
        payload[BUCKET_FIELD[et]] = RISK.get(b, b) if et == "COLLAPSE_RISK" and isinstance(b, int) else b
    ev = bytes.fromhex(d["evidence_hex"]) if d.get("evidence_hex") else None
    return make_aeio(EventType(et), payload, float(d["observed_at"]), source_class=SourceClass(d.get("source_class", "ENV_SENSOR")),
                     observation_key=d["observation_key"], origin_node=d.get("origin_node", "wokwi"),
                     reporter=d.get("origin_node"), evidence=ev,
                     sensor_metadata={"triggered": d.get("triggered", False), "bridge": True})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="-")
    args = ap.parse_args()
    src = sys.stdin if args.input == "-" else open(args.input)
    st, lock, ecp = NodeState(), SemanticPreservationLock(), ECPEngine()
    n = prot = agg = 0
    last_t = 0.0
    fired = set()
    for line in src:
        line = line.strip()
        if not line.startswith("{") or '"sage.aeio.v1"' not in line:
            continue
        d = json.loads(line)
        a = to_aeio(d)
        n += 1
        last_t = max(last_t, a.observed_at)
        rule = lock.registry.rule_for(a.event_type, a.payload)
        if rule.protected:
            st.protected.put(lock.transition(a, Fidelity.F1))
            prot += 1
        else:
            r = lock.transition(a, Fidelity.F3)
            b = r.payload.get(BUCKET_FIELD.get(a.event_type.value, ""), None)
            st.aggregate.add(a.event_type.value, r.geo_cell, r.observed_at, r.payload["sketch_key"], b,
                             device=a.provenance.get("reporter"), ingest="bridge")
            agg += 1
        for rule_, m in ecp.evaluate(st.aggregate, last_t):
            if (rule_.rule_id, m.cell) in fired:
                continue
            fired.add((rule_.rule_id, m.cell))
            print(json.dumps({"ecp": rule_.derived_type, "cell": m.cell, "unique": round(m.unique, 1), "t": last_t}))
    out = {"lines": n, "protected": prot, "aggregated": agg, "protected_entries": len(st.protected),
           "aggregate_sketches": len(st.aggregate.sketches), "spl": lock.stats.to_dict(),
           "estimates": {f"{et}@{c}": round(st.aggregate.estimate(et, c), 1)
                         for et in ("WATER_LEVEL", "SMOKE_DENSITY", "COLLAPSE_RISK") for c in st.aggregate.cells(et)},
           "logical_digest": st.logical_digest()}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
