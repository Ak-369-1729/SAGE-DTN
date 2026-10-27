"""E5 - Sensor burst: increase IoT publish rate, measure effect on human critical delivery and state."""
from __future__ import annotations

import time

from common import RAW, TABLES, mean_ci, quick, run_many, write_csv, write_manifest

from simulator.modes import BASELINES
from simulator.scenario import ScenarioConfig

PERIODS = [60.0, 30.0, 15.0, 5.0]
METRICS = ["CDR_human", "CDR", "bytes_sensor", "TBT_bytes", "peak_storage_B", "responder_sensor_state_B",
           "sensor_observations", "SAT_s", "SA_mean", "SA_sensor_final", "energy_proxy_J"]


def main():
    started = time.time()
    seeds = [1] if quick() else [1, 2, 3]
    periods = [60.0, 5.0] if quick() else PERIODS
    jobs = [(ScenarioConfig(name="e5_sensor_burst", seed=s, sensor_publish_s=p).to_dict(), m)
            for p in periods for s in seeds for m in BASELINES]
    rows = run_many(jobs)
    write_csv(RAW / "e5_sensor_burst.csv", rows)
    summ = []
    for p in periods:
        for m in BASELINES:
            sub = [r for r in rows if r["sensor_publish_s"] == p and r["mode"] == m]
            row = {"sensor_publish_s": p, "per_sensor_rate_per_min": 60.0 / p, "mode": m, "runs": len(sub)}
            for k in METRICS:
                mu, ci = mean_ci([r.get(k, 0) for r in sub])
                row[k], row[k + "_ci95"] = mu, ci
            summ.append(row)
    write_csv(TABLES / "e5_sensor_burst_summary.csv", summ)
    write_manifest("e5_sensor_burst", seeds=seeds, scenario="default topology, varying sensor publish period",
                   configuration={"periods_s": periods, "modes": BASELINES},
                   outputs=["results/raw/e5_sensor_burst.csv", "results/tables/e5_sensor_burst_summary.csv"], started=started)


if __name__ == "__main__":
    main()
