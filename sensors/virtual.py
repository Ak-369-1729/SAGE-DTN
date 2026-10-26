"""Virtual IoT sensors that emit AEIOs.

Each sensor: sampling frequency, Gaussian noise, publish period (adaptable),
local ring buffer of raw samples, event-triggered evidence freezing, failure
time and an energy budget. Ground truth comes from an `Environment` object
with methods water_level_cm(cell_or_xy, t), smoke_ppm(...), vibration_g(...).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from aeio.factory import make_aeio
from aeio.model import AEIO
from aeio.types import EventType, SourceClass
from core.geo import xy_to_latlon

WATER_EDGES = [50, 100, 150, 200]
SMOKE_EDGES = [50, 150, 300, 600]


def bucket(v: float, edges: list[float]) -> int:
    return int(sum(v >= e for e in edges))


def near_edge(v: float, edges: list[float], frac: float = 0.05) -> bool:
    return any(abs(v - e) <= frac * e for e in edges)


@dataclass
class SensorConfig:
    sample_hz: float = 10.0
    publish_period_s: float = 60.0
    noise_sd: float = 1.0
    ring_seconds: float = 30.0
    energy_budget_J: float = 5000.0
    energy_per_sample_J: float = 2e-4
    energy_per_publish_J: float = 0.05
    failure_time_s: float | None = None


@dataclass
class VirtualSensor:
    sensor_id: str
    node_id: str
    x: float
    y: float
    cfg: SensorConfig
    rng: np.random.Generator
    event_type: EventType = EventType.WATER_LEVEL
    source_class: SourceClass = SourceClass.ENV_SENSOR
    ring: deque = field(default_factory=deque)
    energy_used: float = 0.0
    publish_multiplier: float = 1.0
    next_publish: float = 0.0
    seq: int = 0
    last_bucket: object = None
    samples_taken: int = 0
    publications: int = 0
    triggered: int = 0

    def __post_init__(self):
        self.ring = deque(maxlen=max(1, int(self.cfg.ring_seconds * self.cfg.sample_hz)))
        self.lat, self.lon = xy_to_latlon(self.x, self.y)

    # subclasses implement
    def truth(self, env, t: float) -> float: ...
    def classify(self, v: float): ...
    def payload(self, v: float, window: np.ndarray) -> dict: ...
    def trigger(self, v: float, prev_bucket, cur_bucket) -> bool: ...

    @property
    def alive(self) -> bool:
        return self.energy_used < self.cfg.energy_budget_J

    def failed(self, t: float) -> bool:
        return (self.cfg.failure_time_s is not None and t >= self.cfg.failure_time_s) or not self.alive

    def step(self, env, t: float, dt: float) -> list[AEIO]:
        if self.failed(t):
            return []
        n = max(1, int(round(dt * self.cfg.sample_hz)))
        ts = t + np.arange(n) / self.cfg.sample_hz
        vals = np.array([self.truth(env, float(x)) for x in ts[:: max(1, n // 8)]])
        vals = np.interp(np.arange(n), np.linspace(0, n - 1, len(vals)), vals) if len(vals) > 1 else np.full(n, vals[0])
        vals = vals + self.rng.normal(0.0, self.cfg.noise_sd, n)
        self.ring.extend(vals.tolist())
        self.samples_taken += n
        self.energy_used += n * self.cfg.energy_per_sample_J
        v = float(np.mean(vals[-max(1, int(self.cfg.sample_hz * 5)):]))
        cur = self.classify(v)
        changed = self.last_bucket is not None and cur != self.last_bucket
        due = t + dt >= self.next_publish
        if not (due or changed):
            return []
        trig = self.trigger(v, self.last_bucket, cur)
        prev = self.last_bucket
        self.last_bucket = cur
        self.next_publish = t + dt + self.cfg.publish_period_s * self.publish_multiplier
        self.seq += 1
        self.publications += 1
        self.energy_used += self.cfg.energy_per_publish_J
        window = np.array(self.ring)
        evidence = None
        if trig:
            self.triggered += 1
            evidence = np.clip(window * 100, -32768, 32767).astype("<i2").tobytes()
        p = self.payload(v, window)
        p.update({"lat": round(self.lat, 6), "lon": round(self.lon, 6), "sensor_id": self.sensor_id})
        meta = {"sensor_id": self.sensor_id, "sample_hz": self.cfg.sample_hz,
                "publish_period_s": self.cfg.publish_period_s * self.publish_multiplier,
                "ring_samples": len(window), "triggered": trig, "prev_state": prev,
                "energy_used_J": round(self.energy_used, 3)}
        return [make_aeio(self.event_type, p, t + dt, source_class=self.source_class,
                          observation_key=f"{self.sensor_id}:{self.event_type.value}:{self.seq}",
                          origin_node=self.node_id, reporter=self.sensor_id, evidence=evidence,
                          sensor_metadata=meta, confidence=0.9)]


class FloodGaugeSensor(VirtualSensor):
    def __init__(self, *a, **k):
        super().__init__(*a, event_type=EventType.WATER_LEVEL, **k)
        self._hist: deque = deque(maxlen=12)

    def truth(self, env, t):
        return env.water_level_cm(self.x, self.y, t)

    def classify(self, v):
        return bucket(v, WATER_EDGES)

    def payload(self, v, window):
        self._hist.append(v)
        rate = (self._hist[-1] - self._hist[0]) / max(1, len(self._hist) - 1) if len(self._hist) > 1 else 0.0
        return {"level_cm": round(v, 1), "level_bucket": self.classify(v), "rate_cm_per_min": round(rate, 2)}

    def trigger(self, v, prev, cur):
        return prev is not None and cur > prev


class SmokeSensor(VirtualSensor):
    def __init__(self, *a, **k):
        super().__init__(*a, event_type=EventType.SMOKE_DENSITY, **k)

    def truth(self, env, t):
        return env.smoke_ppm(self.x, self.y, t)

    def classify(self, v):
        return bucket(v, SMOKE_EDGES)

    def payload(self, v, window):
        return {"density_ppm": round(max(0.0, v), 1), "density_bucket": self.classify(v)}

    def trigger(self, v, prev, cur):
        return prev is not None and cur > prev and cur >= 2


class VibrationSensor(VirtualSensor):
    def __init__(self, *a, **k):
        super().__init__(*a, event_type=EventType.COLLAPSE_RISK, source_class=SourceClass.STRUCT_SENSOR, **k)

    def truth(self, env, t):
        return env.vibration_g(self.x, self.y, t)

    def classify(self, v):
        v = abs(v)
        return "HIGH" if v >= 0.2 else ("ELEVATED" if v >= 0.05 else "LOW")

    def payload(self, v, window):
        peak = float(np.max(np.abs(window))) if len(window) else abs(v)
        return {"peak_g": round(peak, 3), "risk_state": self.classify(v), "dominant_hz": 3.0}

    def trigger(self, v, prev, cur):
        return cur == "HIGH" and prev != "HIGH"
