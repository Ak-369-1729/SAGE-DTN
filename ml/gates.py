"""Deterministic gates for ML proposals.  ML PROPOSES; DETERMINISTIC POLICY DISPOSES.

No gate output can: write authoritative AEIO state, override SPL, delete a
protected event, increase an authoritative count, fire ECP, or authorise
evidence access. Each gate is a pure function of (base policy, proposal).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdGatePolicy:
    max_decrease_frac: float = 0.5   # T* >= T_base * (1 - 0.5)
    max_increase_frac: float = 1.5   # T* <= T_base * (1 + 1.5)
    quantum: float = 5.0
    floor: float = 10.0


def gate_threshold(t_base: float, delta: float | None, pol: ThresholdGatePolicy = ThresholdGatePolicy()) -> float:
    """T* = DeterministicGate(T_base, ΔT). Invalid/absent proposals fall back to T_base."""
    if delta is None or not math.isfinite(delta):
        return t_base
    d = min(max(delta, -pol.max_decrease_frac * t_base), pol.max_increase_frac * t_base)
    t = round((t_base + d) / pol.quantum) * pol.quantum
    return max(pol.floor, t)


@dataclass(frozen=True)
class DuplicateGatePolicy:
    min_prob: float = 0.9
    max_distance_m: float = 50.0
    max_dt_s: float = 1800.0
    allowed_types: tuple = ("WATER_REQUEST", "SAFE_STATUS")


def gate_duplicate(prob: float | None, etype: str, same_cell: bool, distance_m: float, dt_s: float,
                   pol: DuplicateGatePolicy = DuplicateGatePolicy()) -> bool:
    """True => the new observation may reuse the earlier observation's sketch key.
    Merging can only reduce the authoritative count; protected types are never eligible."""
    if prob is None or not math.isfinite(prob):
        return False
    return (etype in pol.allowed_types and same_cell and prob >= pol.min_prob
            and distance_m <= pol.max_distance_m and 0 <= dt_s <= pol.max_dt_s)


@dataclass(frozen=True)
class SaliencyGatePolicy:
    min_prob: float = 0.7
    max_extra_bytes: int = 64
    preservable_fields: tuple = ("notes", "injury_text")


def gate_saliency(prob: float | None, field: str, value: str, pol: SaliencyGatePolicy = SaliencyGatePolicy()):
    """Returns the extra (field, truncated value) to preserve, or None. Never removes anything."""
    if prob is None or not math.isfinite(prob) or prob < pol.min_prob or field not in pol.preservable_fields:
        return None
    b = value.encode()[: pol.max_extra_bytes]
    return field, b.decode(errors="ignore")
