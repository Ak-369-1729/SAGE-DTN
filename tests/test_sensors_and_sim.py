import numpy as np

from sensors.virtual import FloodGaugeSensor, SensorConfig, SmokeSensor, VibrationSensor
from simulator.engine import run
from simulator.modes import MODES
from simulator.scenario import Environment, ScenarioConfig


def test_sensors_emit_aeios_with_bounded_ring_and_trigger():
    cfg = ScenarioConfig()
    env = Environment(cfg)
    s = FloodGaugeSensor("s", "n", 2000, 2000, SensorConfig(noise_sd=1.0, ring_seconds=10), np.random.default_rng(1))
    out = []
    for step in range(180):
        out += s.step(env, step * 60.0, 60.0)
    assert len(s.ring) == 100
    assert {a.payload["level_bucket"] for a in out} >= {0, 1, 2, 3, 4}
    assert any(a.evidence for a in out)                # rising bucket froze the ring buffer as evidence
    assert all(a.integrity_commitment for a in out if a.evidence)
    v = VibrationSensor("v", "n", 6000, 2500, SensorConfig(noise_sd=0.004), np.random.default_rng(2))
    states = [a.payload["risk_state"] for st in range(180) for a in v.step(env, st * 60.0, 60.0)]
    assert "HIGH" in states
    f = SmokeSensor("f", "n", 4000, 6000, SensorConfig(noise_sd=5, failure_time_s=600), np.random.default_rng(3))
    assert sum(len(f.step(env, st * 60.0, 60.0)) for st in range(30)) <= 11   # fails at 600 s


def test_every_mode_runs_and_is_deterministic():
    cfg = ScenarioConfig(horizon_s=2400, seed=5)
    for m in MODES:
        if m.startswith("J_"):
            continue
        r1, r2 = run(cfg, m), run(cfg, m)
        for k in ("TBT_bytes", "CDR", "critical_generated", "peak_storage_B"):
            assert r1[k] == r2[k] or (r1[k] != r1[k] and r2[k] != r2[k]), (m, k)
