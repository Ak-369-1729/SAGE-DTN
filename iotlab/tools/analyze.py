#!/usr/bin/env python3
"""Turn a SAGE-DTN testbed log into E1-E6 hardware tables (Python 3 standard library only).

    analyze.py <results_dir> [--consumption <dir with *.oml>]
    analyze.py --pending <results_dir>      # write the empty PENDING tables

Reads <results_dir>/run.log (written by controller.py) and writes into the same folder:
    hw_trials.csv        one row per trial, every metric
    hw_e1_spl.csv        E1 on-device SPL property test, one row per node
    HW_RESULTS.md        summary tables mirroring the simulator's E1-E6 (PENDING where no data)
    hw_manifest.json     what was run: experiment id, nodes, layout, firmware version, times

Every number comes from the log. Nothing is filled in by hand; a table with no data says PENDING.
"""
import argparse
import csv
import glob
import json
import os
import re
import statistics
import sys
from collections import defaultdict

CRITICAL = ("TRAPPED_PERSON", "MEDICATION_NEED")
M64 = (1 << 64) - 1


def hash_str(s):
    """Same 64-bit hash as sage_core.h hash64 (FNV-1a + splitmix finaliser)."""
    h = 1469598103934665603
    for c in s.encode():
        h ^= c
        h = (h * 1099511628211) & M64
    h ^= h >> 30
    h = (h * 0xBF58476D1CE4E5B9) & M64
    h ^= h >> 27
    h = (h * 0x94D049BB133111EB) & M64
    h ^= h >> 31
    return "%016x" % h


def kv(text):
    return {k: v for k, v in re.findall(r"(\w+)=(\S+)", text)}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def parse_log(path):
    lines = []
    with open(path, errors="replace") as f:
        for raw in f:
            parts = raw.rstrip("\n").split(";", 2)
            if len(parts) != 3:
                continue
            try:
                ts = float(parts[0])
            except ValueError:
                continue
            node, text = parts[1], parts[2]
            if node != "ctl":
                i = text.find("@")
                if i < 0:
                    continue
                text = text[i:]
            lines.append((ts, node, text))
    return lines


def load_consumption(cdir):
    """IoT-LAB .oml consumption files -> {node: [(unix_t, power_W)]}."""
    out = {}
    if not cdir:
        return out
    for path in glob.glob(os.path.join(cdir, "**", "*.oml"), recursive=True):
        m = re.match(r"([a-z0-9]+)_(\d+)\.oml$", os.path.basename(path))
        if not m:
            continue
        node = "%s-%s" % (m.group(1), m.group(2))
        series = []
        with open(path, errors="replace") as f:
            body = False
            for raw in f:
                if not body:
                    body = raw.strip() == ""
                    continue
                cols = raw.split()
                if len(cols) < 8:
                    continue
                try:
                    series.append((int(cols[3]) + int(cols[4]) / 1e6, float(cols[5])))
                except ValueError:
                    continue
        if series:
            out[node] = series
    return out


def analyze(outdir, cdir):
    lines = parse_log(os.path.join(outdir, "run.log"))
    meta, trials, e1, cur = None, [], [], None
    for ts, node, text in lines:
        if node == "ctl":
            if text.startswith("meta "):
                meta = json.loads(text[5:])
            elif text.startswith("trial_start "):
                cur = {"cfg": json.loads(text[12:]), "t0": ts, "lines": []}
                trials.append(cur)
            elif text.startswith("trial_end"):
                cur["t1"] = ts
                cur = None
            elif cur is not None:
                cur["lines"].append((ts, node, text))
        elif text.startswith("@e1 "):
            d = kv(text)
            d["node"] = node
            e1.append(d)
        elif cur is not None:
            cur["lines"].append((ts, node, text))
    if meta is None:
        sys.exit("no controller metadata in run.log")
    roles = {r["node"]: r for r in meta["layout"]["roles"]}
    sink = [n for n, r in roles.items() if r["role"] == "R"][0]
    power = load_consumption(cdir)
    rows = [trial_metrics(t, roles, sink, power) for t in trials if "t1" in t]
    return meta, rows, e1, bool(power)


def trial_metrics(t, roles, sink, power):
    c = t["cfg"]
    inj, sens_cross, kills = {}, defaultdict(dict), {}
    best, loss, ecp_sink, aggs, stats, digests, trig, evok, evbad = {}, set(), {}, {}, {}, {}, {}, {}, 0
    for ts, node, text in t["lines"]:
        w = text.split()
        if node == "ctl":
            if w[0] == "inj":
                inj[w[1]] = (ts, w[2], int(w[3]))
            elif w[0] == "sens" and w[2] == "SMOKE_DENSITY" and int(w[3]) >= 15000:
                sens_cross[int(w[4])].setdefault(w[1], ts)
            elif w[0] == "kill":
                kills[w[1]] = ts
            continue
        if w[0] in ("@dl", "@up") and node == sink:
            eid, usable = w[1], w[4] == "1"
            b = best.setdefault(eid, {"usable_ts": None, "seen": True})
            if usable and b["usable_ts"] is None:
                b["usable_ts"] = ts
        elif w[0] == "@loss":
            loss.add(w[1])
        elif w[0] == "@ecp" and node == sink:
            ecp_sink.setdefault((w[1], int(w[2])), ts)
        elif w[0] == "@agg" and node == sink:
            aggs[int(w[1])] = kv(text)
        elif w[0] == "@st":
            stats[node] = kv(text)
        elif w[0] == "@dg":
            digests[node] = w[1]
        elif w[0] == "@trig":
            trig[w[1]] = (node, ts)
        elif w[0] == "@evok" and node == sink:
            evok.setdefault(w[1], ts)
        elif w[0] == "@evbad" and node == sink:
            evbad += 1
    r = {k: c.get(k) for k in ("trial", "exp", "mode", "load", "dup", "srate", "R", "corrupt", "rep")}
    r["duration_s"] = round(t["t1"] - t["t0"], 1)
    crit = {hash_str(k): v for k, v in inj.items() if v[1] in CRITICAL}
    r["critical_injected"] = len(crit)
    deliv = {e: best[e]["usable_ts"] for e in crit if e in best and best[e]["usable_ts"] is not None}
    r["CDR"] = round(len(deliv) / len(crit), 4) if crit else None
    lost = {e for e in crit if e in loss or (e in best and best[e]["usable_ts"] is None)}
    r["critical_info_loss"] = round(len(lost) / len(crit), 4) if crit else None
    lat = [deliv[e] - crit[e][0] for e in deliv]
    r["latency_mean_s"] = round(mean(lat), 1) if lat else None
    human = {hash_str(k): v for k, v in inj.items()}
    r["human_injected"] = len(human)
    cfgd = [n for n in roles if n in stats]
    r["TBT_bytes"] = sum(int(stats[n].get("tx_b", 0)) for n in cfgd)
    r["sensor_bytes"] = sum(int(stats[n].get("txs_b", 0)) for n in cfgd)
    r["tx_packets"] = sum(int(stats[n].get("tx_p", 0)) for n in cfgd)
    r["peak_storage_B"] = max([int(stats[n].get("peak_b", 0)) for n in cfgd if n != sink] or [0])
    r["responder_state_B"] = int(stats.get(sink, {}).get("store_b", 0)) if sink in stats else None
    for k in ("red", "rej", "evict", "drop", "pdrop"):
        r[{"red": "reductions", "rej": "spl_clamps", "evict": "evictions", "drop": "drops", "pdrop": "protected_drops"}[k]] = sum(int(stats[n].get(k, 0)) for n in cfgd)
    r["nodes_reporting"] = len(cfgd)
    # ECP ground truth: >= ecpw distinct water requests in a village; >= 2 distinct smoke sensors above 150 ppm
    truth = {}
    water = defaultdict(list)
    for k, (ts, typ, v) in sorted(inj.items(), key=lambda kv_: kv_[1][0]):
        if typ == "WATER_REQUEST":
            water[v].append(ts)
    for v, tss in water.items():
        if len(tss) >= c.get("ecpw", 6):
            truth[("WATER_SHORTAGE", v)] = sorted(tss)[c.get("ecpw", 6) - 1]
    for v, d in sens_cross.items():
        if len(d) >= c.get("ecps", 2):
            truth[("POTENTIAL_FIRE_CLUSTER", v)] = sorted(d.values())[c.get("ecps", 2) - 1]
    det = [k for k in truth if k in ecp_sink]
    r["ecp_true"] = len(truth)
    r["ecp_detected"] = len(det)
    r["ecp_missed"] = len(truth) - len(det)
    r["ecp_false"] = len([k for k in ecp_sink if k not in truth])
    r["ecp_latency_mean_s"] = round(mean([ecp_sink[k] - truth[k] for k in det]), 1) if det else None
    # E2: aggregate estimates at the responder against the true distinct count
    ratios = defaultdict(list)
    for v, a in aggs.items():
        true_n = len(water.get(v, []))
        if true_n:
            ratios["raw"].append(int(a["raw"]) / true_n)
            ratios["exact"].append(int(a["exact"]) / true_n)
            ratios["hll"].append(int(a["hll_x10"]) / 10.0 / true_n)
    for k in ("raw", "exact", "hll"):
        r["water_%s_ratio" % k] = round(mean(ratios[k]), 3) if ratios[k] else None
    # E4: evidence recovery of the destroyed sources' triggered evidence
    lost_src = {e for e, (n, _) in trig.items() if n in kills}
    r["evidence_objects_lost_source"] = len(lost_src)
    r["evidence_recovered"] = len([e for e in lost_src if e in evok])
    r["recovery_probability"] = round(r["evidence_recovered"] / len(lost_src), 3) if lost_src else None
    kill_ts = min(kills.values()) if kills else None
    r["evidence_recovered_after_loss"] = len([e for e in lost_src if e in evok and kill_ts and evok[e] >= kill_ts])
    rl = [evok[e] - trig[e][1] for e in lost_src if e in evok]
    r["recovery_latency_from_trigger_s"] = round(mean(rl), 1) if rl else None
    r["integrity_failures_detected"] = evbad
    # E6: digests of all live configured nodes
    live = {n: d for n, d in digests.items() if n in roles and n not in kills}
    r["digest_nodes"] = len(live)
    r["distinct_digests"] = len(set(live.values())) if live else None
    # energy from IoT-LAB consumption monitoring
    if power:
        per = []
        for n in roles:
            s = [p for (ts, p) in power.get(n, []) if t["t0"] <= ts <= t["t1"]]
            if s:
                per.append(statistics.mean(s))
        r["mean_node_power_mW"] = round(1000 * statistics.mean(per), 2) if per else None
        r["energy_all_nodes_J"] = round(sum(per) * r["duration_s"], 2) if per else None
    return r


# ----------------------------------------------------------------------------- output
def md_table(rows, cols):
    if not rows:
        return "PENDING: no hardware data yet.\n"
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join("" if r.get(c) is None else ("%.3g" % r[c] if isinstance(r[c], float) else str(r[c])) for c in cols) + " |")
    return "\n".join(out) + "\n"


def group(rows, keys, cols):
    g = defaultdict(list)
    for r in rows:
        g[tuple(r.get(k) for k in keys)].append(r)
    out = []
    for k, rs in sorted(g.items(), key=lambda kv_: tuple(str(x) for x in kv_[0])):
        d = dict(zip(keys, k))
        d["runs"] = len(rs)
        for c in cols:
            vals = [x[c] for x in rs if isinstance(x.get(c), (int, float))]
            d[c] = round(statistics.mean(vals), 4) if vals else None
        out.append(d)
    return out


def write_report(outdir, meta, rows, e1, has_power):
    hw = meta is not None and meta.get("backend") == "iotlab"
    src = ("FIT IoT-LAB experiment %s, %d nodes" % (meta.get("exp_id"), len(meta.get("nodes", []))) if hw else
           ("LOCAL EMULATION (%s), not hardware" % meta.get("kind")) if meta else "none yet, the hardware run is PENDING")
    L = ["# SAGE-DTN hardware results", "",
         "Source: **%s**." % src,
         "All values are computed by `iotlab/tools/analyze.py` from `run.log`. Tables with no data say PENDING.", ""]
    if meta and not hw:
        L += ["> These numbers come from local processes, not radios. They only show that the pipeline works.",
              "> Do not cite them as hardware results.", ""]
    L += ["## E1 SPL property on the device", "",
          md_table(e1, ["node", "iters", "forbidden", "committed_forbidden", "legal", "committed_legal", "permit_ns", "clamp_fid"])]
    e3 = group([r for r in rows if r["exp"] == "E3"], ["load", "mode"],
               ["CDR", "critical_info_loss", "latency_mean_s", "TBT_bytes", "peak_storage_B", "spl_clamps", "ecp_detected", "ecp_missed", "ecp_false"] +
               (["mean_node_power_mW", "energy_all_nodes_J"] if has_power else []))
    L += ["## E3 network load (real radio, software contact plan)", "", md_table(e3, ["load", "mode", "runs", "CDR", "critical_info_loss", "latency_mean_s", "TBT_bytes",
                                                                                     "peak_storage_B", "spl_clamps", "ecp_detected", "ecp_missed", "ecp_false"] +
                                                                                    (["mean_node_power_mW", "energy_all_nodes_J"] if has_power else []))]
    e2 = group([r for r in rows if r["exp"] == "E2"], ["dup", "mode"], ["water_raw_ratio", "water_exact_ratio", "water_hll_ratio", "ecp_detected", "ecp_missed", "ecp_false"])
    L += ["## E2 duplicate replay (estimate / true distinct water requests)", "",
          md_table(e2, ["dup", "mode", "runs", "water_raw_ratio", "water_exact_ratio", "water_hll_ratio", "ecp_detected", "ecp_missed", "ecp_false"])]
    e5 = group([r for r in rows if r["exp"] == "E5"], ["srate", "mode"], ["CDR", "sensor_bytes", "TBT_bytes", "responder_state_B"])
    L += ["## E5 sensor publish rate", "", md_table(e5, ["srate", "mode", "runs", "CDR", "sensor_bytes", "TBT_bytes", "responder_state_B"])]
    e4 = group([r for r in rows if r["exp"] == "E4"], ["R", "corrupt"], ["evidence_objects_lost_source", "evidence_recovered", "evidence_recovered_after_loss",
                                                                       "recovery_probability", "recovery_latency_from_trigger_s", "integrity_failures_detected", "CDR"])
    L += ["## E4 source loss and evidence recovery (replicas on ferries)", "",
          md_table(e4, ["R", "corrupt", "runs", "evidence_objects_lost_source", "evidence_recovered", "evidence_recovered_after_loss", "recovery_probability", "recovery_latency_from_trigger_s",
                        "integrity_failures_detected", "CDR"])]
    e6 = [r for r in rows if r["exp"] == "E6"]
    L += ["## E6 convergence after an all-contact phase", "", md_table(e6, ["trial", "mode", "digest_nodes", "distinct_digests"])]
    L += ["## E7 / E8", "", "Not run on hardware. E7 is an offline ML evaluation and E8 needs the ML models on the node, which this port does not include.", ""]
    with open(os.path.join(outdir, "HW_RESULTS.md"), "w") as f:
        f.write("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--consumption", help="folder with IoT-LAB consumption .oml files")
    ap.add_argument("--pending", action="store_true", help="write empty PENDING tables")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    if a.pending:
        write_report(a.outdir, None, [], [], False)
        return
    meta, rows, e1, has_power = analyze(a.outdir, a.consumption)
    if rows:
        cols = list(rows[0].keys())
        for r in rows:
            cols += [k for k in r if k not in cols]
        with open(os.path.join(a.outdir, "hw_trials.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    if e1:
        with open(os.path.join(a.outdir, "hw_e1_spl.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(e1[0].keys()))
            w.writeheader()
            w.writerows(e1)
    write_report(a.outdir, meta, rows, e1, has_power)
    with open(os.path.join(a.outdir, "hw_manifest.json"), "w") as f:
        json.dump({"meta": meta, "trials": len(rows), "e1_nodes": len(e1), "consumption": has_power}, f, indent=1)
    print("wrote", os.path.join(a.outdir, "HW_RESULTS.md"), "(%d trials)" % len(rows))


if __name__ == "__main__":
    main()
