"""Virtual IoT sensor-node demo: Python virtual sensors emit the same sage.aeio.v1 lines as the ESP32 firmware.

    python scripts/virtual_sensor_demo.py --village 2 --minutes 180 | python scripts/wokwi_bridge.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from simulator.scenario import VILLAGES, Environment, ScenarioConfig  # noqa: E402
from sensors.virtual import FloodGaugeSensor, SensorConfig, SmokeSensor, VibrationSensor  # noqa: E402

RISKN = {"LOW": 0, "ELEVATED": 1, "HIGH": 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--village", type=int, default=2)
    ap.add_argument("--minutes", type=int, default=180)
    ap.add_argument("--publish-s", type=float, default=60)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    env = Environment(ScenarioConfig())
    x, y = VILLAGES[a.village]
    sensors = []
    for k in range(2):
        for j, (S, sd) in enumerate(((FloodGaugeSensor, 2.0), (SmokeSensor, 8.0), (VibrationSensor, 0.004))):
            sensors.append(S(f"S{a.village}_{k}.{j}", f"S{a.village}_{k}", x + 60 * k, y + 40 * k,
                             SensorConfig(noise_sd=sd, publish_period_s=a.publish_s), np.random.default_rng([a.seed, k, j])))
    for step in range(a.minutes):
        for s in sensors:
            for ae in s.step(env, step * 60.0, 60.0):
                bf = {"WATER_LEVEL": "level_bucket", "SMOKE_DENSITY": "density_bucket", "COLLAPSE_RISK": "risk_state"}[ae.event_type.value]
                b = ae.payload[bf]
                print(json.dumps({"schema": "sage.aeio.v1", "event_id": ae.event_id, "event_type": ae.event_type.value,
                                  "source_class": ae.source_class.value, "fidelity_level": 0, "geo_cell": ae.geo_cell,
                                  "lat": ae.payload["lat"], "lon": ae.payload["lon"], "observed_at": ae.observed_at,
                                  "bucket": RISKN.get(b, b), "observation_key": ae.observation_key,
                                  "origin_node": ae.provenance["origin_node"], "triggered": bool(ae.evidence),
                                  "evidence_len": len(ae.evidence or b""),
                                  "integrity_commitment": (ae.integrity_commitment or {}).get("digest_hex", ""),
                                  "policy_version": ae.policy_version}))


if __name__ == "__main__":
    main()
