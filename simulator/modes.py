"""System modes (baselines A-I plus optional gated-ML J).

All modes share the scenario, contact trace, workload and accounting. They
differ only in the information-management policy at each node.
"""
from __future__ import annotations

MODES: dict[str, dict] = {
    "A_flooding":          dict(kind="record", order="fifo", replicate="always", evict="drop_oldest", adapt=None),
    "B_store_forward":     dict(kind="record", order="fifo", replicate="never", evict="drop_new", adapt=None),
    "C_priority":          dict(kind="record", order="priority", replicate="always", evict="priority", adapt=None),
    "D_utility":           dict(kind="record", order="utility", replicate="utility", evict="utility", adapt=None),
    "E_adaptive_no_spl":   dict(kind="record", order="utility", replicate="utility", evict="utility", adapt="no_spl"),
    "F_utility_spl":       dict(kind="record", order="utility", replicate="utility", evict="utility", adapt="spl"),
    "G_utility_spl_cpmm":  dict(kind="cpmm", ecp=False, defer=False, sensor_adapt=False, recovery=False, ml=False),
    "H_full_core":         dict(kind="cpmm", ecp=True, defer=True, sensor_adapt=True, recovery=False, ml=False),
    "I_full_recovery":     dict(kind="cpmm", ecp=True, defer=True, sensor_adapt=True, recovery=True, ml=False),
    "J_full_gated_ml":     dict(kind="cpmm", ecp=True, defer=True, sensor_adapt=True, recovery=True, ml=True),
}

BASELINES = [m for m in MODES if not m.startswith("J_")]

LABELS = {
    "A_flooding": "A Flooding", "B_store_forward": "B Store-and-forward", "C_priority": "C Priority-only",
    "D_utility": "D Utility-only", "E_adaptive_no_spl": "E Adaptive fidelity w/o SPL",
    "F_utility_spl": "F Utility+SPL", "G_utility_spl_cpmm": "G Utility+SPL+CPMM",
    "H_full_core": "H Full deterministic core", "I_full_recovery": "I Full + recovery",
    "J_full_gated_ml": "J Full + gated ML",
}
