"""E6 - Convergence under random encounter permutations.

Node states are taken from the end of a full-core (H) network run (heterogeneous,
partially synchronised). For each permutation seed we copy the states, apply a
random sequence of pairwise bidirectional merges (with injected duplicate
deliveries), and measure (i) logical-state mismatch vs the global join,
(ii) digest mismatch across permutations, (iii) ECP disagreement.
"""
from __future__ import annotations

import random
import time

from common import RAW, TABLES, quick, write_csv, write_manifest

from cpmm.node_state import merge
from simulator.engine import Simulation
from simulator.scenario import ScenarioConfig


def ecp_set(sim, st, t):
    return frozenset((r.rule_id, m.cell) for r, m in sim.ecp.evaluate(st.aggregate, t))


def main():
    started = time.time()
    run_seeds = [1] if quick() else [1, 2]
    perms = 5 if quick() else 20
    rows, summary = [], []
    for rs in run_seeds:
        sim = Simulation(ScenarioConfig(name="e6", seed=rs), "H_full_core")
        sim.run()
        t_eval = sim.cfg.horizon_s
        base = {nid: n.state for nid, n in sim.nodes.items()}
        ids = sorted(base)
        glob = None
        for nid in ids:
            glob = base[nid].copy() if glob is None else merge(glob, base[nid])
        gd = glob.logical_digest()
        g_ecp = ecp_set(sim, glob, t_eval)
        pre_mismatch = sum(base[i].logical_digest() != gd for i in ids)
        finals = set()
        for p in range(perms):
            rng = random.Random(p * 7919 + rs)
            st = {i: base[i].copy() for i in ids}
            enc = 0
            met = set()
            curve = []
            while len(met) < len(ids) * (len(ids) - 1) // 2 or enc < 3 * len(ids):
                a, b = rng.sample(ids, 2)
                st[b].merge_in(st[a])
                st[a].merge_in(st[b])
                if rng.random() < 0.2:      # duplicate delivery
                    st[b].merge_in(st[a])
                met.add(tuple(sorted((a, b))))
                enc += 1
                if enc % 25 == 0:
                    curve.append(sum(st[i].logical_digest() != gd for i in ids))
            # random-order gossip can leave nodes behind; finish with one more random round
            for _ in range(2):
                order = ids[:]
                rng.shuffle(order)
                for a, b in zip(order, order[1:] + order[:1]):
                    st[b].merge_in(st[a]); st[a].merge_in(st[b])
            mism = sum(st[i].logical_digest() != gd for i in ids)
            ecp_dis = sum(ecp_set(sim, st[i], t_eval) != g_ecp for i in ids)
            conflicts = sum(len(st[i].protected.conflicts()) for i in ids)
            finals.update(st[i].logical_digest() for i in ids)
            rows.append({"run_seed": rs, "perm": p, "nodes": len(ids), "encounters": enc,
                         "pre_mismatch_nodes": pre_mismatch, "final_mismatch_nodes": mism,
                         "ecp_disagreement_nodes": ecp_dis, "conflicts_total": conflicts,
                         "mismatch_curve": " ".join(map(str, curve[:30]))})
        summary.append({"run_seed": rs, "permutations": perms, "nodes": len(ids),
                        "pre_merge_mismatch_nodes": pre_mismatch,
                        "max_final_mismatch_nodes": max(r["final_mismatch_nodes"] for r in rows if r["run_seed"] == rs),
                        "distinct_final_digests_across_permutations": len(finals),
                        "max_ecp_disagreement_nodes": max(r["ecp_disagreement_nodes"] for r in rows if r["run_seed"] == rs),
                        "global_ecp_events": len(g_ecp),
                        "explicit_conflicts_in_global_state": len(glob.protected.conflicts())})
    write_csv(RAW / "e6_convergence.csv", rows)
    write_csv(TABLES / "e6_convergence_summary.csv", summary)
    write_manifest("e6_convergence", seeds=run_seeds, scenario="end-state of H run, random permutations",
                   configuration={"permutations": perms, "duplicate_delivery_prob": 0.2},
                   outputs=["results/raw/e6_convergence.csv", "results/tables/e6_convergence_summary.csv"], started=started)
    for s in summary:
        print(s)


if __name__ == "__main__":
    main()
