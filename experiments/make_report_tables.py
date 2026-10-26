"""Render result CSVs as Markdown tables (results/tables/*.md) for the report. Values are copied, never typed."""
from __future__ import annotations

import csv
import math

from common import TABLES

SPECS = {
    "e1_spl_summary.csv": None,
    "e2_ecp_summary.csv": ["method", "multiplier", "cases", "false_ecp_rate", "missed_ecp_rate", "mean_estimate_ratio",
                           "max_abs_rel_error", "latency_mean_s", "mean_state_bytes"],
    "e3_network_load_summary.csv": ["human_load", "mode", "CDR", "CDR_ci95", "critical_info_loss", "TBT_bytes", "SAT_s",
                                    "SAT_censored_runs", "SA_mean", "peak_storage_B", "summary_error", "utility_per_kB",
                                    "critical_evidence_at_responder", "ecp_false", "ecp_missed", "ecp_latency_mean_s"],
    "e4_recovery_summary.csv": None,
    "e5_sensor_burst_summary.csv": ["sensor_publish_s", "mode", "CDR_human", "bytes_sensor", "TBT_bytes", "peak_storage_B",
                                    "responder_sensor_state_B", "sensor_observations", "SAT_s", "SA_mean"],
    "e6_convergence_summary.csv": None,
    "e7_ml1_summary.csv": None, "e7_ml2_summary.csv": None, "e7_ml3_summary.csv": None,
    "e8_ml_network_summary.csv": None,
}


def fmt(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if math.isnan(f):
        return "n/a"
    if f.is_integer() and abs(f) >= 1:
        return f"{int(f):,}" if abs(f) >= 10_000 else f"{int(f)}"
    return f"{f:.3g}"


def main():
    for name, cols in SPECS.items():
        p = TABLES / name
        if not p.exists() or p.stat().st_size == 0:
            continue
        rows = list(csv.DictReader(p.open()))
        cols = cols or list(rows[0].keys())
        out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        out += ["| " + " | ".join(fmt(r.get(c, "")) for c in cols) + " |" for r in rows]
        (TABLES / name.replace(".csv", ".md")).write_text("\n".join(out) + "\n")
        print("wrote", name.replace(".csv", ".md"))


if __name__ == "__main__":
    main()
