"""Gated ML threshold proposals for the network simulator (mode J).

The model sees only what a node has: the duplicate-resistant first-hour unique
count of a cell from its own sketch. Its ΔT passes through gate_threshold.
ECP still evaluates deterministically; the model never fires ECP.
"""
from __future__ import annotations

import random

from .data import demand_cells, demand_stream
from .gates import gate_threshold
from .models import ThresholdCalibrator


class MLThresholdGate:
    def __init__(self, seed: int = 101, n_cells: int = 1500, rule_id: str = "ECP-WATER-1"):
        rng = random.Random(seed)
        X, y = [], []
        for c in demand_cells(n_cells, seed):
            ev = demand_stream(c, rng)
            X.append([sum(1 for e in ev if e < 3600)])
            y.append(c["bg_rate_h"])
        self.model = ThresholdCalibrator(seed=0).fit(X, y)
        self.rule_id = rule_id
        self.proposals = 0
        self.clamped = 0

    def thresholds(self, agg, rules, t):
        if t < 3600:
            return None
        out = {}
        for r in rules:
            if r.rule_id != self.rule_id:
                continue
            w1 = int(3600 // agg.window_s) - 1
            for cell in agg.cells(r.source_type):
                first = agg.estimate(r.source_type, cell, 0, w1)
                d = self.model.propose_delta([first], r.T1_unique)
                T = gate_threshold(r.T1_unique, d)
                self.proposals += 1
                self.clamped += abs(T - (r.T1_unique + d)) > 2.5
                out[(r.rule_id, cell)] = (T, r.T2_growth, r.T3_confidence)
        return out
