"""E7 - Optional gated ML (run only after the deterministic core).

ML-1 ECP threshold calibrator:   fixed T1 vs deterministic adaptive T1 vs ML proposal + gate.
ML-2 duplicate-independence:     deterministic exact-key sketch vs deterministic heuristic vs gated ML prior.
ML-3 invariant-saliency proposer: drop free text (baseline) vs keyword regex vs gated ML.
All ML outputs pass through ml/gates.py. Train and test use disjoint seeds.
"""
from __future__ import annotations

import math
import random
import re
import time

import numpy as np

from common import RAW, TABLES, mean_ci, quick, write_csv, write_manifest

from aeio import codec
from aeio.factory import make_aeio
from aeio.types import EventType, SourceClass
from ml.data import KEYWORD_REGEX, demand_cells, demand_stream, note_text
from ml.gates import gate_duplicate, gate_saliency, gate_threshold
from ml.models import IndependenceEstimator, SaliencyProposer, ThresholdCalibrator
from spl.lock import permit

T_BASE = 40.0
H = 4 * 3600


# ---------------------------------------------------------------- ML-1
def ecp_eval(ev, T):
    arr = np.asarray(ev)
    for t in range(3600, H + 1, 300):
        thr = T(t) if callable(T) else T
        n = np.searchsorted(arr, t, "right") - np.searchsorted(arr, t - 3600, "right")
        if n >= thr:
            return t
    return None


def ml1(seed_train=101, seed_test=202):
    ntr, nte = (600, 400) if quick() else (2000, 1000)
    rng = random.Random(seed_train)
    tr = demand_cells(ntr, seed_train)
    X, y = [], []
    for c in tr:
        ev = demand_stream(c, rng)
        first = sum(1 for e in ev if e < 3600)
        X.append([math.log(c["pop"]), first])
        y.append(c["bg_rate_h"])
    model = ThresholdCalibrator(seed=0).fit(X, y)
    rng = random.Random(seed_test)
    te = demand_cells(nte, seed_test)
    rows = []
    for c in te:
        ev = demand_stream(c, rng)
        first = sum(1 for e in ev if e < 3600)
        d_ml = model.propose_delta([math.log(c["pop"]), first], T_BASE)
        d_det = 1.5 * first + 5.0 - T_BASE
        variants = {"fixed": T_BASE, "deterministic_adaptive": gate_threshold(T_BASE, d_det),
                    "ml_gated": gate_threshold(T_BASE, d_ml), "ml_ungated_diagnostic": T_BASE + d_ml}
        for name, T in variants.items():
            ft = ecp_eval(ev, T)
            fired = ft is not None
            false = fired and (not c["incident"] or ft < c["onset"])
            rows.append({"cell": c["cell"], "pop": round(c["pop"]), "incident": int(c["incident"]), "variant": name,
                         "threshold": T, "fired": int(fired), "false_ecp": int(false),
                         "missed_ecp": int(c["incident"] and (not fired or false)),
                         "latency_s": (ft - c["onset"]) if (fired and c["incident"] and not false) else float("nan"),
                         "gate_clamped": int(name == "ml_gated" and abs(T - (T_BASE + d_ml)) > 2.5)})
    summ = []
    for v in ("fixed", "deterministic_adaptive", "ml_gated", "ml_ungated_diagnostic"):
        sub = [r for r in rows if r["variant"] == v]
        neg = [r for r in sub if not r["incident"]]
        pos = [r for r in sub if r["incident"]]
        lat = mean_ci([r["latency_s"] for r in pos])
        summ.append({"experiment": "ML-1 threshold", "variant": v, "cells": len(sub),
                     "false_ecp_rate_noncident": sum(r["false_ecp"] for r in neg) / len(neg),
                     "false_ecp_any": sum(r["false_ecp"] for r in sub) / len(sub),
                     "missed_ecp_rate": sum(r["missed_ecp"] for r in pos) / len(pos),
                     "latency_mean_s": lat[0], "latency_ci95_s": lat[1],
                     "gate_clamped_frac": sum(r["gate_clamped"] for r in sub) / len(sub)})
    return rows, summ


# ---------------------------------------------------------------- ML-2
def households(n_cells, seed):
    rng = random.Random(seed)
    reps = []
    for c in range(n_cells):
        nh = max(5, int(rng.gauss(60, 15)))
        for h in range(nh):
            x, y = rng.uniform(0, 500), rng.uniform(0, 500)
            t = rng.uniform(0, 7200)
            size = rng.randint(1, 7)
            words = rng.sample(["no", "water", "since", "two", "days", "kids", "thirsty", "tank", "empty", "well",
                                "dirty", "need", "urgent", "family", "old", "mother", "drinking", "help"], 5)
            reps.append((t, c, h, x, y, size, set(words), rng.randrange(2)))
            if rng.random() < 0.4:
                for d in range(rng.randint(1, 3)):
                    w2 = set(words)
                    if rng.random() < 0.5:
                        w2 = set(list(w2)[:4]) | {rng.choice(["please", "again", "still"])}
                    reps.append((t + rng.uniform(60, 1800), c, h, x + rng.gauss(0, 15), y + rng.gauss(0, 15),
                                 size if rng.random() < 0.9 else max(1, size + rng.choice([-1, 1])), w2, rng.randrange(2)))
    reps.sort()
    return reps


def pair_feats(r, q):
    dist = math.hypot(r[3] - q[3], r[4] - q[4])
    dt = r[0] - q[0]
    jac = len(r[6] & q[6]) / len(r[6] | q[6])
    return [dist, dt, int(r[5] == q[5]), jac, int(r[7] == q[7])], dist, dt


def candidates(reps):
    """For each report, the nearest earlier report in the same cell within 1800 s (deterministic pre-filter)."""
    by_cell = {}
    out = []
    for i, r in enumerate(reps):
        lst = by_cell.setdefault(r[1], [])
        best = None
        for j in reversed(lst):
            q = reps[j]
            if r[0] - q[0] > 1800:
                break
            d = math.hypot(r[3] - q[3], r[4] - q[4])
            if best is None or d < best[0]:
                best = (d, j)
        out.append(best[1] if best else None)
        lst.append(i)
    return out


def ml2(seed_train=303, seed_test=404):
    nc = 60 if quick() else 200
    tr = households(nc, seed_train)
    ctr = candidates(tr)
    X = [pair_feats(r, tr[j])[0] for r, j in zip(tr, ctr) if j is not None]
    y = [int(r[1] == tr[j][1] and r[2] == tr[j][2]) for r, j in zip(tr, ctr) if j is not None]
    model = IndependenceEstimator(seed=0).fit(X, y)
    te = households(nc, seed_test)
    cte = candidates(te)
    probs = {}
    feats = [(i, *pair_feats(r, te[j])) for i, (r, j) in enumerate(zip(te, cte)) if j is not None]
    if feats:
        p = model.prob_duplicate([f[1] for f in feats])
        probs = {f[0]: (pi, f[2], f[3], f[1]) for f, pi in zip(feats, p)}
    truth = {}
    for r in te:
        truth.setdefault(r[1], set()).add(r[2])
    rows = []
    for variant in ("exact_key_sketch", "deterministic_heuristic", "ml_gated"):
        key = {}
        false_merge = 0
        merges = 0
        for i, r in enumerate(te):
            j = cte[i]
            merge = False
            if j is not None and i in probs:
                pi, dist, dt, f = probs[i]
                if variant == "deterministic_heuristic":
                    merge = dist <= 15 and dt <= 1800 and f[2] == 1 and f[3] >= 0.5
                elif variant == "ml_gated":
                    merge = gate_duplicate(pi, "WATER_REQUEST", True, dist, dt)
            if merge:
                key[i] = key[j]
                merges += 1
                false_merge += te[j][2] != r[2]
            else:
                key[i] = i
        for c in sorted(truth):
            est = len({key[i] for i, r in enumerate(te) if r[1] == c})
            rows.append({"variant": variant, "cell": c, "true_households": len(truth[c]), "estimate": est,
                         "rel_error": (est - len(truth[c])) / len(truth[c])})
        rows.append({"variant": variant, "cell": "ALL", "merges": merges, "false_merges": false_merge})
    summ = []
    for v in ("exact_key_sketch", "deterministic_heuristic", "ml_gated"):
        sub = [r for r in rows if r["variant"] == v and r["cell"] != "ALL"]
        allr = [r for r in rows if r["variant"] == v and r["cell"] == "ALL"][0]
        summ.append({"experiment": "ML-2 duplicate prior", "variant": v, "cells": len(sub),
                     "mean_rel_error": float(np.mean([r["rel_error"] for r in sub])),
                     "mean_abs_rel_error": float(np.mean([abs(r["rel_error"]) for r in sub])),
                     "undercount_cells": sum(r["rel_error"] < 0 for r in sub),
                     "merges": allr["merges"], "false_merges": allr["false_merges"]})
    return rows, summ


# ---------------------------------------------------------------- ML-3
def ml3(seed_train=505, seed_test=606):
    n_tr, n_te = (1000, 800) if quick() else (4000, 2000)
    rng = random.Random(seed_train)
    tr = [(note_text(rng, s), s) for s in (rng.random() < 0.25 for _ in range(n_tr))]
    model = SaliencyProposer(seed=0).fit([t for t, _ in tr], [int(s) for _, s in tr])
    rng = random.Random(seed_test)
    te = [(note_text(rng, s), s) for s in (rng.random() < 0.25 for _ in range(n_te))]
    probs = model.prob([t for t, _ in te])
    rx = re.compile(KEYWORD_REGEX, re.I)
    summ = []
    rows = []
    for variant in ("drop_free_text", "keyword_regex", "ml_gated"):
        kept_sal = kept_non = extra = viol = 0
        for (txt, sal), p in zip(te, probs):
            a = make_aeio(EventType.MEDICATION_NEED, {"medication_label": "INSULIN", "urgency": 2, "lat": 26.12,
                                                      "lon": 91.71, "notes": txt}, 100.0,
                          source_class=SourceClass.SURVIVOR, observation_key=txt, origin_node="n")
            red = codec.reduce(a, 1)
            keep = None
            if variant == "keyword_regex" and rx.search(txt):
                keep = ("notes", txt.encode()[:64].decode(errors="ignore"))
            elif variant == "ml_gated":
                keep = gate_saliency(float(p), "notes", txt)
            if keep:
                red = red.replace(payload={**red.payload, keep[0]: keep[1]})
                extra += len(keep[1].encode())
            viol += not permit(a, red).allowed
            kept = keep is not None
            kept_sal += kept and sal
            kept_non += kept and not sal
            rows.append({"variant": variant, "salient": int(sal), "preserved": int(kept), "p_ml": round(float(p), 4)})
        ns = sum(1 for _, s in te if s)
        summ.append({"experiment": "ML-3 saliency", "variant": variant, "records": len(te),
                     "salient_recall": kept_sal / ns, "false_preserve_rate": kept_non / (len(te) - ns),
                     "extra_bytes_per_record": extra / len(te), "spl_violations": viol})
    return rows, summ


def main():
    started = time.time()
    r1, s1 = ml1()
    r2, s2 = ml2()
    r3, s3 = ml3()
    write_csv(RAW / "e7_ml1_threshold.csv", r1)
    write_csv(RAW / "e7_ml2_duplicates.csv", r2, ["variant", "cell", "true_households", "estimate", "rel_error", "merges", "false_merges"])
    write_csv(RAW / "e7_ml3_saliency.csv", r3)
    write_csv(TABLES / "e7_ml1_summary.csv", s1)
    write_csv(TABLES / "e7_ml2_summary.csv", s2)
    write_csv(TABLES / "e7_ml3_summary.csv", s3)
    write_manifest("e7_ml_gated", seeds={"ml1": [101, 202], "ml2": [303, 404], "ml3": [505, 606]},
                   scenario="synthetic generators in ml/data.py (train/test disjoint seeds)",
                   configuration={"T_base": T_BASE, "gates": "ml/gates.py defaults"},
                   outputs=[f"results/tables/e7_ml{i}_summary.csv" for i in (1, 2, 3)], started=started)
    for s in s1 + s2 + s3:
        print(s)


if __name__ == "__main__":
    main()
