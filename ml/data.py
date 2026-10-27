"""Synthetic generators for the ML experiments (shared, seeded).

LIMITATION: models are trained and tested on data from these generators, so
any measured benefit is conditional on the generator's assumptions.
"""
from __future__ import annotations

import math
import random

SALIENT = ["insulin-dependent", "insulin dependant", "infant", "new born baby", "pregnant", "expecting mother",
           "dialysis patient", "kidney dialysis", "wheelchair user", "cannot walk", "on oxygen", "needs o2 cylinder"]
NEUTRAL = ["please help", "near the temple", "family of four", "roof is leaking", "phone battery low",
           "road blocked", "behind school", "no electricity", "water entered house", "waiting since morning"]
KEYWORD_REGEX = r"insulin|infant|pregnan|dialysis|wheelchair|oxygen"


def cell_population(rng):
    return math.exp(rng.uniform(math.log(300), math.log(6000)))


def demand_cells(n, seed, incident_frac=0.3):
    rng = random.Random(seed)
    cells = []
    for i in range(n):
        pop = cell_population(rng)
        bg = pop * 0.004            # background unique requests per hour
        inc = rng.random() < incident_frac
        onset = rng.uniform(3600, 7200) if inc else None
        extra = 2.0 * bg + 5.0 if inc else 0.0
        cells.append({"cell": f"X{i}", "pop": pop, "bg_rate_h": bg, "incident": inc, "onset": onset,
                      "extra_rate_h": extra})
    return cells


def demand_stream(cell, rng, horizon=4 * 3600):
    ev = []
    t = 0.0
    while True:
        t += rng.expovariate(cell["bg_rate_h"] / 3600)
        if t >= horizon:
            break
        ev.append(t)
    if cell["incident"]:
        t = cell["onset"]
        while True:
            t += rng.expovariate(cell["extra_rate_h"] / 3600)
            if t >= horizon:
                break
            ev.append(t)
    return sorted(ev)


def note_text(rng, salient: bool):
    parts = rng.sample(NEUTRAL, 2)
    if salient:
        parts.insert(rng.randrange(3), rng.choice(SALIENT))
    s = ", ".join(parts)
    if rng.random() < 0.15:  # typos
        i = rng.randrange(len(s))
        s = s[:i] + s[i + 1:]
    return s
