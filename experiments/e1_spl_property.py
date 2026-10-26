"""E1 - SPL property test: randomly generated legal and illegal transitions."""
from __future__ import annotations

import random
import time
from collections import Counter

from common import RAW, TABLES, quick, write_csv, write_manifest

from aeio import codec
from aeio.factory import make_aeio
from aeio.types import EventType, SourceClass
from spl.lock import SemanticPreservationLock, _canonical_payload
from spl.oracle import is_legal
from tests.strategies import MUTATIONS, mutate


def random_aeio(rng: random.Random):
    t = rng.choice(list(EventType))
    p = dict(_canonical_payload(t))
    if "lat" in p:
        p["lat"], p["lon"] = rng.uniform(26.0, 26.3), rng.uniform(91.6, 91.9)
    if t == EventType.COLLAPSE_RISK:
        p["risk_state"] = rng.choice(["LOW", "ELEVATED", "HIGH"])
    ev = rng.randbytes(rng.randint(1, 64)) if rng.random() < 0.5 else None
    a = make_aeio(t, p, rng.uniform(0, 20000), source_class=SourceClass.SURVIVOR,
                  observation_key=f"k{rng.randrange(10**9)}", origin_node="n1", evidence=ev,
                  geo_cell=None if "lat" in p else "C3_4")
    start = rng.choice([0, 0, 1, 2])
    return codec.reduce(a, start) if start else a


def main(n: int | None = None, seed: int = 20261026):
    started = time.time()
    n = n or (20_000 if quick() else 200_000)
    rng = random.Random(seed)
    lock = SemanticPreservationLock()
    c = Counter()
    per_type = Counter()
    for i in range(n):
        a = random_aeio(rng)
        kind = rng.choice(MUTATIONS)
        cand = mutate(a, kind, rng, rng.randint(0, 4))
        legal = is_legal(a.to_dict(), cand.to_dict())
        d = lock.check(a, cand)
        committed = d.allowed
        if not legal:
            c["attempted_forbidden"] += 1
            c["rejected_forbidden"] += not committed
            c["committed_forbidden"] += committed
            per_type[(a.event_type.value, "forbidden")] += 1
        else:
            c["attempted_legal"] += 1
            c["committed_legal"] += committed
            c["rejected_legal"] += not committed
            per_type[(a.event_type.value, "legal")] += 1
        # utility-driven path: transition() must never output an illegal representation
        tgt = rng.randint(0, 4)
        out = lock.transition(a, tgt)
        c["transition_calls"] += 1
        if out is not a and not is_legal(a.to_dict(), out.to_dict()):
            c["transition_committed_forbidden"] += 1
    rows = [{"metric": k, "value": v} for k, v in sorted(c.items())]
    rows.append({"metric": "SPLViolationRate", "value": c["committed_forbidden"] / max(1, c["attempted_forbidden"])})
    rows.append({"metric": "false_rejection_rate", "value": c["rejected_legal"] / max(1, c["attempted_legal"])})
    write_csv(RAW / "e1_spl_property.csv", rows, ["metric", "value"])
    write_csv(TABLES / "e1_spl_summary.csv", rows, ["metric", "value"])
    write_csv(RAW / "e1_spl_by_type.csv", [{"event_type": k[0], "class": k[1], "trials": v} for k, v in sorted(per_type.items())])
    write_manifest("e1_spl_property", seeds=[seed], scenario="random AEIO x random mutation",
                   configuration={"trials": n, "mutations": MUTATIONS, "rejections_by_reason": lock.stats.by_reason},
                   outputs=["results/raw/e1_spl_property.csv", "results/tables/e1_spl_summary.csv"], started=started)
    print("E1", dict(c))
    return c


if __name__ == "__main__":
    main()
