"""E2 - ECP duplicate/replay attack.

Known true WATER_REQUEST populations per cell arrive over 60 min at two ingest
nodes; every record is then replayed at multiplier m (re-sent copies with new
message ids, same observation). Three counting front-ends feed the *same* ECP
rule: raw message count, exact distinct (oracle, unbounded memory) and the
bounded HLL sketch used by CPMM.
"""
from __future__ import annotations

import random
import time

import numpy as np

from common import RAW, TABLES, mean_ci, quick, write_csv, write_manifest

from cpmm.aggregate_state import BoundedAggregateState
from cpmm.exact import ExactAggregateState
from ecp.engine import ECPEngine

POPS = [10, 20, 30, 39, 41, 50, 80, 150]
MULTS = [1, 2, 5, 10, 20, 50, 100]


def stream(n_true, mult, rng, dur=3600.0):
    ev = []
    for i in range(n_true):
        t = rng.uniform(0, dur)
        ev.append((t, f"obs{i}", f"P{i}", f"F{i % 2}", f"msg{i}:0"))
        for r in range(1, mult):  # replays at later times (any node)
            ev.append((min(dur * 1.5, t + rng.uniform(0, 1800)), f"obs{i}", f"P{i}", f"F{rng.randrange(2)}", f"msg{i}:{r}"))
    ev.sort()
    return ev


def run_case(n_true, mult, seed, p=8):
    rng = random.Random(seed * 1000 + n_true * 7 + mult)
    ev = stream(n_true, mult, rng)
    eng = ECPEngine()
    T1 = eng.rules[0].T1_unique
    st = {"raw": ExactAggregateState(8), "exact": ExactAggregateState(8), "sketch": BoundedAggregateState(p)}
    fire_t = {k: None for k in st}
    truth_cross = None
    seen = set()
    i = 0
    for step in range(0, 7200 + 1, 60):
        while i < len(ev) and ev[i][0] <= step:
            t, ok, dev, ing, mid = ev[i]
            i += 1
            st["raw"].add("WATER_REQUEST", "C0_0", t, mid, device=mid, ingest=ing)
            st["exact"].add("WATER_REQUEST", "C0_0", t, ok, device=dev, ingest=ing)
            st["sketch"].add("WATER_REQUEST", "C0_0", t, f"{seed}:{ok}", device=f"{seed}:{dev}", ingest=ing)
            seen.add(ok)
            if truth_cross is None and len(seen) >= T1:
                truth_cross = t
        for k, s in st.items():
            if fire_t[k] is None and eng.evaluate(s, step):
                fire_t[k] = step
    est = {k: s.estimate("WATER_REQUEST", "C0_0") for k, s in st.items()}
    oracle_fires = fire_t["exact"] is not None
    rows = []
    for k in st:
        fired = fire_t[k] is not None
        rows.append({"true_population": n_true, "multiplier": mult, "seed": seed, "method": k,
                     "messages": len(ev), "estimate": est[k], "estimate_ratio": est[k] / n_true,
                     "fired": int(fired), "oracle_fires": int(oracle_fires),
                     "false_ecp": int(fired and not oracle_fires), "missed_ecp": int(oracle_fires and not fired),
                     "promotion_latency_s": (fire_t[k] - truth_cross) if (fired and truth_cross is not None) else float("nan"),
                     "state_bytes": (s.storage_bytes() if k == "sketch" else 8 * sum(len(x.s) for x in st[k].sketches.values()))})
    return rows


def main():
    started = time.time()
    seeds = list(range(1, 6 if quick() else 21))
    rows = [r for s in seeds for n in POPS for m in MULTS for r in run_case(n, m, s)]
    write_csv(RAW / "e2_ecp_duplicates.csv", rows)
    summ = []
    for method in ("raw", "exact", "sketch"):
        for m in MULTS:
            sub = [r for r in rows if r["method"] == method and r["multiplier"] == m]
            neg = [r for r in sub if not r["oracle_fires"]]
            pos = [r for r in sub if r["oracle_fires"]]
            lat = mean_ci([r["promotion_latency_s"] for r in pos])
            summ.append({"method": method, "multiplier": m, "cases": len(sub),
                         "false_ecp_rate": sum(r["false_ecp"] for r in neg) / max(1, len(neg)),
                         "missed_ecp_rate": sum(r["missed_ecp"] for r in pos) / max(1, len(pos)),
                         "mean_estimate_ratio": float(np.mean([r["estimate_ratio"] for r in sub])),
                         "max_abs_rel_error": float(np.max([abs(r["estimate_ratio"] - 1) for r in sub])),
                         "latency_mean_s": lat[0], "latency_ci95_s": lat[1],
                         "mean_state_bytes": float(np.mean([r["state_bytes"] for r in sub]))})
    write_csv(TABLES / "e2_ecp_summary.csv", summ)
    write_manifest("e2_ecp_duplicates", seeds=seeds, scenario="single cell WATER_REQUEST replay",
                   configuration={"populations": POPS, "multipliers": MULTS, "rule": ECPEngine().rules[0].__dict__, "hll_p": 8},
                   outputs=["results/raw/e2_ecp_duplicates.csv", "results/tables/e2_ecp_summary.csv"], started=started)
    for r in summ:
        print(r)


if __name__ == "__main__":
    main()
