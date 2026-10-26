"""Scenario configuration, ground-truth environment, topology/mobility and workload.

Everything is generated from the scenario seed so that every system mode is
evaluated on exactly the same contact trace and the same event workload.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from aeio.factory import make_aeio
from aeio.model import AEIO
from aeio.types import EventType, SourceClass
from core.geo import xy_to_latlon
from core.hashing import short_id

VILLAGES = [(2000.0, 2000.0), (6000.0, 2500.0), (4000.0, 6000.0)]
BASE = (600.0, 7400.0)


@dataclass
class ScenarioConfig:
    name: str = "default"
    seed: int = 1
    horizon_s: int = 10800
    step_s: int = 60
    n_villages: int = 3
    field_per_village: int = 2
    sensor_per_village: int = 2
    n_ferries: int = 3
    n_responders: int = 2
    ferry_speed_mps: float = 8.0
    contact_dwell_s: float = 300.0
    radio_range_m: float = 600.0
    bandwidth_Bps: float = 1000.0
    storage_field_B: int = 262_144
    storage_sensor_B: int = 131_072
    storage_ferry_B: int = 1_048_576
    battery_field_J: float = 20_000.0
    battery_sensor_J: float = 5_000.0
    battery_ferry_J: float = 200_000.0
    energy_tx_J_per_B: float = 1e-6
    energy_rx_J_per_B: float = 5e-7
    human_load: float = 1.0
    human_rates_per_village_h: dict = field(default_factory=lambda: {
        "TRAPPED_PERSON": 2.0, "MEDICATION_NEED": 2.0, "WATER_REQUEST": 6.0, "SAFE_STATUS": 30.0})
    water_surge: dict = field(default_factory=lambda: {"village": 1, "start_s": 3600, "rate_per_h": 40.0})
    flood_village: int = 0
    fire: dict = field(default_factory=lambda: {"village": 2, "start_s": 5400})
    quake: dict = field(default_factory=lambda: {"village": 1, "start_s": 4000, "duration_s": 420, "peak_g": 0.3})
    duplicate_rate: float = 0.3
    max_duplicates: int = 3
    evidence_bytes: dict = field(default_factory=lambda: {
        "TRAPPED_PERSON": 4096, "MEDICATION_NEED": 2048, "WATER_REQUEST": 256, "SAFE_STATUS": 128})
    sensor_publish_s: float = 60.0
    sensor_sample_hz: float = 10.0
    sensor_failure_s: float | None = None
    hll_p: int = 8
    window_s: int = 300
    windows_kept: int = 48
    evidence_replicas: int = 3
    source_loss_s: float | None = None
    source_loss_nodes: list = field(default_factory=list)
    recovery_request_s: float | None = None
    replica_corrupt_prob: float = 0.0
    replica_placement: str = "first_contact"   # or "prefer_mobile": first min(R, ferries) replicas only on ferries
    protected_forward_max_fidelity: int | None = None   # experimental control (E4)
    ml: bool = False
    utility: dict = field(default_factory=dict)
    ecp_thresholds: dict = field(default_factory=dict)
    sample_every_steps: int = 5

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ScenarioConfig":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def load(cls, path: str | Path) -> "ScenarioConfig":
        return cls.from_dict(json.loads(Path(path).read_text()))


# ----------------------------------------------------------------------------
class Environment:
    """Ground-truth physical environment (flood, smoke, vibration)."""

    def __init__(self, cfg: ScenarioConfig):
        self.cfg = cfg
        self.v = VILLAGES[: cfg.n_villages]

    def _village(self, x, y) -> int:
        return int(np.argmin([math.hypot(x - a, y - b) for a, b in self.v]))

    def water_level_cm(self, x, y, t):
        vi = self._village(x, y)
        if vi == self.cfg.flood_village:
            return 30.0 + 190.0 * min(1.0, max(0.0, (t - 1800.0) / 5400.0))
        if vi == (self.cfg.flood_village + 1) % len(self.v):
            return 20.0 + 70.0 * min(1.0, max(0.0, (t - 3600.0) / 7200.0))
        return 10.0

    def smoke_ppm(self, x, y, t):
        f = self.cfg.fire
        vi = self._village(x, y)
        if f and vi == f["village"] and t >= f["start_s"]:
            return 20.0 + 680.0 * min(1.0, (t - f["start_s"]) / 1200.0)
        return 20.0

    def vibration_g(self, x, y, t):
        q = self.cfg.quake
        vi = self._village(x, y)
        if q and vi == q["village"] and q["start_s"] <= t < q["start_s"] + q["duration_s"]:
            return q["peak_g"]
        return 0.01


# ----------------------------------------------------------------------------
@dataclass
class NodeSpec:
    node_id: str
    role: str          # FIELD | SENSOR | FERRY | RESPONDER
    village: int | None
    x: float
    y: float
    storage_B: int | None
    battery_J: float


def build_nodes(cfg: ScenarioConfig, rng: np.random.Generator) -> list[NodeSpec]:
    nodes: list[NodeSpec] = []
    for vi, (vx, vy) in enumerate(VILLAGES[: cfg.n_villages]):
        for k in range(cfg.field_per_village):
            a, r = rng.uniform(0, 2 * math.pi), rng.uniform(0, 200)
            nodes.append(NodeSpec(f"F{vi}_{k}", "FIELD", vi, vx + r * math.cos(a), vy + r * math.sin(a),
                                  cfg.storage_field_B, cfg.battery_field_J))
        for k in range(cfg.sensor_per_village):
            a, r = rng.uniform(0, 2 * math.pi), rng.uniform(50, 250)
            nodes.append(NodeSpec(f"S{vi}_{k}", "SENSOR", vi, vx + r * math.cos(a), vy + r * math.sin(a),
                                  cfg.storage_sensor_B, cfg.battery_sensor_J))
    for k in range(cfg.n_ferries):
        nodes.append(NodeSpec(f"M{k}", "FERRY", None, *BASE, cfg.storage_ferry_B, cfg.battery_ferry_J))
    for k in range(cfg.n_responders):
        nodes.append(NodeSpec(f"R{k}", "RESPONDER", None, BASE[0] + 40 * k, BASE[1], None, 1e12))
    return nodes


class FerryMobility:
    """Ferries cycle BASE -> V0 -> V1 -> ... -> BASE with a dwell at every stop; phase-shifted."""

    def __init__(self, cfg: ScenarioConfig):
        self.cfg = cfg
        self.stops = [BASE] + VILLAGES[: cfg.n_villages]
        legs = []
        for i in range(len(self.stops)):
            a, b = self.stops[i], self.stops[(i + 1) % len(self.stops)]
            legs.append((a, b, math.hypot(b[0] - a[0], b[1] - a[1]) / cfg.ferry_speed_mps))
        self.legs = legs
        self.period = sum(cfg.contact_dwell_s + d for _, _, d in legs)

    def position(self, k: int, t: float) -> tuple[float, float]:
        tt = (t + k * self.period / max(1, self.cfg.n_ferries)) % self.period
        for a, b, d in self.legs:
            if tt < self.cfg.contact_dwell_s:
                return a
            tt -= self.cfg.contact_dwell_s
            if tt < d:
                f = tt / d
                return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
            tt -= d
        return self.stops[0]


# ----------------------------------------------------------------------------
@dataclass
class HumanSubmission:
    t: float
    node_id: str
    aeio: AEIO
    msg_id: str
    duplicate: bool


def generate_human_workload(cfg: ScenarioConfig, nodes: list[NodeSpec], rng: np.random.Generator):
    """Poisson human reports per village/type; duplicates are re-submissions of the same observation."""
    subs: list[HumanSubmission] = []
    fields = {vi: [n for n in nodes if n.role == "FIELD" and n.village == vi] for vi in range(cfg.n_villages)}
    person = 0
    for vi, (vx, vy) in enumerate(VILLAGES[: cfg.n_villages]):
        for etype, rate_h in cfg.human_rates_per_village_h.items():
            rates = [(0.0, cfg.horizon_s, rate_h * cfg.human_load)]
            ws = cfg.water_surge
            if etype == "WATER_REQUEST" and ws and ws["village"] == vi:
                rates.append((ws["start_s"], cfg.horizon_s, ws["rate_per_h"] * cfg.human_load))
            for t0, t1, r in [x for x in rates if x[1] > x[0]]:
                n = rng.poisson(r * (t1 - t0) / 3600.0)
                for t in np.sort(rng.uniform(t0, t1, n)):
                    person += 1
                    a, rad = rng.uniform(0, 2 * math.pi), 400 * math.sqrt(rng.uniform())
                    x, y = vx + rad * math.cos(a), vy + rad * math.sin(a)
                    lat, lon = xy_to_latlon(x, y)
                    reporter = f"P{vi}_{person}"
                    payload = _human_payload(etype, rng)
                    payload.update({"lat": round(lat, 6), "lon": round(lon, 6)})
                    target = fields[vi][int(rng.integers(len(fields[vi])))]
                    ev = rng.bytes(int(cfg.evidence_bytes.get(etype, 0))) if cfg.evidence_bytes.get(etype) else None
                    a0 = make_aeio(EventType(etype), payload, float(t), source_class=SourceClass.SURVIVOR,
                                   observation_key=f"{reporter}:{etype}:0", origin_node=target.node_id,
                                   reporter=reporter, evidence=ev, confidence=0.8)
                    subs.append(HumanSubmission(float(t), target.node_id, a0, short_id("msg", reporter, etype, 0), False))
                    if rng.uniform() < cfg.duplicate_rate:
                        for d in range(1, 1 + int(rng.integers(1, cfg.max_duplicates + 1))):
                            tn = fields[vi][int(rng.integers(len(fields[vi])))]
                            td = float(t + rng.uniform(30, 900))
                            if td >= cfg.horizon_s:
                                continue
                            subs.append(HumanSubmission(td, tn.node_id, a0.replace(provenance={**a0.provenance, "ingest_node": tn.node_id}),
                                                        short_id("msg", reporter, etype, d), True))
    subs.sort(key=lambda s: (s.t, s.msg_id))
    return subs


def _human_payload(etype: str, rng) -> dict:
    if etype == "TRAPPED_PERSON":
        return {"trapped_status": "TRAPPED", "persons": int(rng.integers(1, 5)),
                "injury_text": "injured, under debris near wall", "contact": "+91-XXXXXXXXXX"}
    if etype == "MEDICATION_NEED":
        return {"medication_label": str(rng.choice(["INSULIN", "ANTIBIOTIC", "INHALER", "ANTIEPILEPTIC"])),
                "urgency": int(rng.integers(1, 4)), "notes": "needed within 6 hours"}
    if etype == "WATER_REQUEST":
        return {"household_size": int(rng.integers(1, 8)), "notes": "no drinking water"}
    return {"persons": int(rng.integers(1, 6)), "message": "we are safe at relief camp"}
