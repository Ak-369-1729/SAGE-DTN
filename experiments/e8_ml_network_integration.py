"""E8 - Integration check of gated ML inside the network simulator (J vs I).

This is NOT an ML-benefit test: ECP 'false/missed' here are relative to the
fixed-threshold oracle, which J intentionally departs from. It checks that ML
on/off leaves SPL, CDR and protected-state behaviour intact and that every
ML output is gated.
"""
from __future__ import annotations

import time

from common import RAW, TABLES, mean_ci, quick, write_csv, write_manifest

from ml.runtime_gate import MLThresholdGate
from simulator.engine import Simulation
from simulator.scenario import ScenarioConfig

METRICS = ["CDR", "critical_info_loss", "TBT_bytes", "SA_mean", "spl_rejected", "ecp_detected", "ecp_false",
           "ecp_missed", "ecp_latency_mean_s"]


def main():
    started = time.time()
    gate = MLThresholdGate()
    seeds = [1] if quick() else [1, 2, 3]
    rows = []
    for load in (1.0, 4.0):
        for s in seeds:
            for mode in ("I_full_recovery", "J_full_gated_ml"):
                gate.proposals = gate.clamped = 0
                r = Simulation(ScenarioConfig(name="e8", seed=s, human_load=load), mode, ml_gate=gate).run()
                r["ml_proposals"] = gate.proposals if mode.startswith("J") else 0
                r["ml_clamped"] = gate.clamped if mode.startswith("J") else 0
                rows.append(r)
    write_csv(RAW / "e8_ml_network.csv", rows)
    summ = []
    for load in (1.0, 4.0):
        for mode in ("I_full_recovery", "J_full_gated_ml"):
            sub = [r for r in rows if r["mode"] == mode and r["human_load"] == load]
            row = {"human_load": load, "mode": mode, "runs": len(sub),
                   "ml_proposals": sum(r["ml_proposals"] for r in sub), "ml_clamped": sum(r["ml_clamped"] for r in sub)}
            for k in METRICS:
                row[k] = mean_ci([r.get(k, float("nan")) for r in sub])[0]
            summ.append(row)
    write_csv(TABLES / "e8_ml_network_summary.csv", summ)
    write_manifest("e8_ml_network_integration", seeds=seeds, scenario="default, loads 1x and 4x",
                   configuration={"modes": ["I_full_recovery", "J_full_gated_ml"]},
                   outputs=["results/tables/e8_ml_network_summary.csv"], started=started)
    for r in summ:
        print(r)


if __name__ == "__main__":
    main()
