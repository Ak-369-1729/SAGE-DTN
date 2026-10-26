"""Generate every figure from result CSVs only (no values are typed in here)."""
from __future__ import annotations

import csv
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from common import PLOTS, TABLES  # noqa: E402

from simulator.modes import BASELINES, LABELS  # noqa: E402

COLORS = dict(zip(BASELINES, ["#7f7f7f", "#bcbd22", "#8c564b", "#1f77b4", "#ff7f0e", "#9467bd",
                              "#17becf", "#2ca02c", "#d62728"]))
MARK = dict(zip(BASELINES, "osD^v<>Pp"))


def load(name):
    p = TABLES / name
    if not p.exists() or p.stat().st_size == 0:
        return []
    with p.open() as f:
        return [{k: _num(v) for k, v in r.items()} for r in csv.DictReader(f)]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v if v != "" else float("nan")


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(PLOTS / name, dpi=140)
    plt.close(fig)
    print("wrote", PLOTS / name)


def by_mode(rows):
    d = defaultdict(list)
    for r in rows:
        d[r["mode"]].append(r)
    return d


def e3():
    rows = load("e3_network_load_summary.csv")
    if not rows:
        return
    bm = by_mode(rows)
    for ycol, fname, ylabel in (("CDR", "CDR_vs_TBT.png", "Critical delivery rate (usable)"),
                                ("SAT_s", "SAT_vs_TBT.png", "Situational-awareness time SAT (s); hollow = some runs censored")):
        fig, ax = plt.subplots(figsize=(7.5, 5))
        for m in BASELINES:
            rs = sorted(bm.get(m, []), key=lambda r: r["human_load"])
            xs = [r["TBT_bytes"] / 1e6 for r in rs]
            ys = [r[ycol] for r in rs]
            ax.plot(xs, ys, "-", color=COLORS[m], alpha=0.5)
            for r, x, y in zip(rs, xs, ys):
                hollow = ycol == "SAT_s" and r["SAT_censored_runs"] > 0
                ax.scatter([x], [y], color="none" if hollow else COLORS[m], edgecolors=COLORS[m], marker=MARK[m], s=40,
                           label=LABELS[m] if r is rs[0] else None)
        ax.set_xscale("log")
        ax.set_xlabel("Total bytes transmitted TBT (MB, log) — points = offered load 0.5x..8x")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, ncol=2)
        _save(fig, fname)
    for ycol, fname, ylabel in (("CDR", "CDR_vs_load.png", "Critical delivery rate (usable)"),
                                ("peak_storage_B", "queue_vs_load.png", "Peak per-node queue/storage (KB)")):
        fig, ax = plt.subplots(figsize=(7.5, 5))
        for m in BASELINES:
            rs = sorted(bm.get(m, []), key=lambda r: r["human_load"])
            xs = [r["human_load"] for r in rs]
            ys = [r[ycol] / (1024 if ycol == "peak_storage_B" else 1) for r in rs]
            es = [r[ycol + "_ci95"] / (1024 if ycol == "peak_storage_B" else 1) for r in rs]
            ax.errorbar(xs, ys, yerr=es, color=COLORS[m], marker=MARK[m], ms=5, capsize=2, label=LABELS[m])
        ax.set_xscale("log", base=2)
        ax.set_xlabel("Offered human-report load (x baseline)")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, ncol=2)
        _save(fig, fname)


def e2():
    rows = load("e2_ecp_summary.csv")
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for meth, c, lab in (("raw", "#d62728", "Raw message count"), ("exact", "#7f7f7f", "Exact distinct (oracle, unbounded)"),
                         ("sketch", "#2ca02c", "CPMM HLL sketch (bounded)")):
        rs = sorted([r for r in rows if r["method"] == meth], key=lambda r: r["multiplier"])
        ax.plot([r["multiplier"] for r in rs], [r["false_ecp_rate"] for r in rs], "-o", color=c, label=lab)
    ax.set_xscale("log")
    ax.set_xlabel("Replay multiplier (copies of each true WATER_REQUEST)")
    ax.set_ylabel("False ECP rate (cells below true threshold)")
    ax.grid(alpha=0.3)
    ax.legend()
    _save(fig, "false_ECP_vs_duplicates.png")


def e4():
    rows = load("e4_recovery_summary.csv")
    if not rows:
        return
    fig, ax = plt.subplots(1, 2, figsize=(10, 4.2))
    for c, col in ((0.0, "#1f77b4"), (0.1, "#ff7f0e")):
        rs = sorted([r for r in rows if r["replica_corrupt_prob"] == c], key=lambda r: r["replicas"])
        ax[0].plot([r["replicas"] for r in rs], [r["recovery_probability"] for r in rs], "-o", color=col,
                   label=f"corrupt replica prob {c}")
        ax[1].errorbar([r["replicas"] for r in rs], [r["latency_mean_s"] for r in rs],
                       yerr=[r["latency_ci95_s"] for r in rs], marker="o", color=col, capsize=3, label=f"corrupt {c}")
    ax[0].set_xlabel("Evidence replicas R (source destroyed)")
    ax[0].set_ylabel("Recovery probability")
    ax[1].set_xlabel("Evidence replicas R")
    ax[1].set_ylabel("Recovery latency (s)")
    for a in ax:
        a.grid(alpha=0.3)
        a.legend(fontsize=8)
    _save(fig, "recovery_vs_replicas.png")


def e5():
    rows = load("e5_sensor_burst_summary.csv")
    if not rows:
        return
    bm = by_mode(rows)
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for m in BASELINES:
        rs = sorted(bm.get(m, []), key=lambda r: r["sensor_observations"])
        ax.plot([r["sensor_observations"] for r in rs], [r["responder_sensor_state_B"] / 1024 for r in rs],
                "-", marker=MARK[m], color=COLORS[m], label=LABELS[m])
    ax.set_xlabel("Sensor observations generated per run")
    ax.set_ylabel("Sensor state held at responder (KB)")
    ax.set_yscale("log")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    _save(fig, "storage_vs_observation_count.png")
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for m in BASELINES:
        rs = sorted(bm.get(m, []), key=lambda r: r["per_sensor_rate_per_min"])
        ax.plot([r["per_sensor_rate_per_min"] for r in rs], [r["CDR_human"] for r in rs], "-", marker=MARK[m],
                color=COLORS[m], label=LABELS[m])
    ax.set_xlabel("Per-sensor publish rate (per min)")
    ax.set_ylabel("Critical human CDR (usable)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    _save(fig, "human_CDR_vs_sensor_rate.png")


def main():
    e2(); e3(); e4(); e5()


if __name__ == "__main__":
    main()
