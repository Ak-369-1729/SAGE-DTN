"""E4 - Source-loss evidence recovery with R = 0, 1, 3, 5 replicas.

Mode I. Both village-0 field nodes (the evidence sources) are destroyed at
t=5400 s; the responder issues authorised recovery requests at t=5460 s for
every reduced protected record originating there. Evidence is not eagerly
forwarded (protected_forward_max_fidelity=F1) so recovery is actually needed.
10 % of placed replicas are deliberately corrupted to exercise verification.
"""
from __future__ import annotations

import time

from common import RAW, TABLES, mean_ci, quick, run_many, write_csv, write_manifest

from simulator.scenario import ScenarioConfig

REPLICAS = [0, 1, 3, 5]


def cfg(seed, R, corrupt):
    return ScenarioConfig(name="e4_recovery", seed=seed, evidence_replicas=R, source_loss_s=5400,
                          source_loss_nodes=["F0_0", "F0_1"], recovery_request_s=5460,
                          protected_forward_max_fidelity=1, replica_corrupt_prob=corrupt).to_dict()


def main():
    started = time.time()
    seeds = [1, 2, 3] if quick() else list(range(1, 11))
    jobs = [(cfg(s, R, c), "I_full_recovery") for c in (0.0, 0.1) for R in REPLICAS for s in seeds]
    rows = run_many(jobs)
    for r in rows:
        r["replica_corrupt_prob"] = r["config"]["replica_corrupt_prob"]
    write_csv(RAW / "e4_recovery.csv", rows)
    summ = []
    for c in (0.0, 0.1):
        for R in REPLICAS:
            sub = [r for r in rows if r["evidence_replicas"] == R and r["replica_corrupt_prob"] == c]
            req = sum(r.get("recovery_requests", 0) for r in sub)
            ok = sum(r.get("recovery_success", 0) for r in sub)
            lat = mean_ci([r.get("recovery_latency_mean_s", float("nan")) for r in sub])
            summ.append({"replica_corrupt_prob": c, "replicas": R, "runs": len(sub), "requests": req, "recovered": ok,
                         "recovery_probability": ok / req if req else float("nan"),
                         "latency_mean_s": lat[0], "latency_ci95_s": lat[1],
                         "recovery_bytes_per_request": sum(r.get("recovery_bytes", 0) for r in sub) / req if req else float("nan"),
                         "replica_bytes_total": sum(r.get("bytes_evidence_replica", 0) for r in sub),
                         "integrity_failures_detected": sum(r.get("recovery_integrity_failures_detected", 0) for r in sub),
                         "corrupt_evidence_accepted": sum(r.get("recovery_corrupt_accepted", 0) for r in sub),
                         "CDR": mean_ci([r["CDR"] for r in sub])[0]})
    write_csv(TABLES / "e4_recovery_summary.csv", summ)
    write_manifest("e4_source_loss_recovery", seeds=seeds, scenario="source loss F0_0,F0_1 @5400s, request @5460s",
                   configuration={"replicas": REPLICAS, "corrupt_probs": [0.0, 0.1], "mode": "I_full_recovery"},
                   outputs=["results/raw/e4_recovery.csv", "results/tables/e4_recovery_summary.csv"], started=started)
    for r in summ:
        print(r)


if __name__ == "__main__":
    main()
