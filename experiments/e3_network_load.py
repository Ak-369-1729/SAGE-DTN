"""E3 - Network load sweep across all baselines (same seeds/contact traces per load)."""
from __future__ import annotations

import time

from common import RAW, TABLES, mean_ci, quick, run_many, write_csv, write_manifest

from simulator.modes import BASELINES
from simulator.scenario import ScenarioConfig

LOADS = [0.5, 1, 2, 4, 8]
METRICS = ["CDR", "CDR_any", "critical_info_loss", "TBT_bytes", "SAT_s", "SA_mean", "peak_storage_B", "mean_storage_B",
           "summary_error", "utility_per_kB", "energy_proxy_J", "critical_latency_mean_s",
           "critical_evidence_at_responder", "ecp_false", "ecp_missed", "ecp_latency_mean_s"]


def main():
    started = time.time()
    seeds = [1, 2] if quick() else [1, 2, 3, 4, 5]
    loads = [1, 4] if quick() else LOADS
    jobs = [(ScenarioConfig(name="e3_load", seed=s, human_load=float(l)).to_dict(), m)
            for l in loads for s in seeds for m in BASELINES]
    rows = run_many(jobs)
    write_csv(RAW / "e3_network_load.csv", rows)
    summ = []
    for l in loads:
        for m in BASELINES:
            sub = [r for r in rows if r["human_load"] == float(l) and r["mode"] == m]
            row = {"human_load": l, "mode": m, "runs": len(sub),
                   "SAT_censored_runs": sum(bool(r["SAT_censored"]) for r in sub)}
            for k in METRICS:
                mu, ci = mean_ci([r.get(k, float("nan")) for r in sub])
                row[k], row[k + "_ci95"] = mu, ci
            summ.append(row)
    write_csv(TABLES / "e3_network_load_summary.csv", summ)
    write_manifest("e3_network_load", seeds=seeds, scenario="3 villages, 2 field + 2 sensor nodes each, 3 ferries, 2 responders",
                   configuration={"loads": loads, "modes": BASELINES, "base": ScenarioConfig().to_dict()},
                   outputs=["results/raw/e3_network_load.csv", "results/tables/e3_network_load_summary.csv"], started=started)


if __name__ == "__main__":
    main()
