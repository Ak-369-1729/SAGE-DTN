"""FastAPI backend for the browser simulator. Runs the deterministic core server-side."""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simulator.engine import Simulation  # noqa: E402
from simulator.modes import LABELS, MODES  # noqa: E402
from simulator.scenario import ScenarioConfig  # noqa: E402

app = FastAPI(title="SAGE-DTN simulator")
STATIC = Path(__file__).with_name("static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

MAX_NODES = 60
MAX_HORIZON = 6 * 3600


class RunRequest(BaseModel):
    mode: str = "I_full_recovery"
    scenario: dict = {}


@lru_cache(maxsize=1)
def _ml_gate():
    from ml.runtime_gate import MLThresholdGate
    return MLThresholdGate()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/modes")
def modes():
    return [{"id": k, "label": LABELS[k], **v} for k, v in MODES.items()]


@app.get("/api/default-scenario")
def default_scenario():
    d = ScenarioConfig().to_dict()
    d["sample_every_steps"] = 1
    return d


@app.post("/api/run")
def run(req: RunRequest):
    if req.mode not in MODES:
        raise HTTPException(400, f"unknown mode {req.mode}")
    cfg = ScenarioConfig.from_dict({**ScenarioConfig().to_dict(), "sample_every_steps": 1, **req.scenario})
    n = cfg.n_villages * (cfg.field_per_village + cfg.sensor_per_village) + cfg.n_ferries + cfg.n_responders
    if n > MAX_NODES or cfg.horizon_s > MAX_HORIZON or cfg.n_villages > 3:
        raise HTTPException(400, f"limits: <= {MAX_NODES} nodes, <= {MAX_HORIZON}s horizon, <= 3 villages")
    if cfg.recovery_request_s is None and cfg.source_loss_s is not None:
        cfg.recovery_request_s = cfg.source_loss_s + cfg.step_s
    sim = Simulation(cfg, req.mode, ml_gate=_ml_gate() if MODES[req.mode].get("ml") else None, timeline=True)
    metrics = sim.run()
    return _clean({"metrics": metrics, "timeline": sim.timeline, "events": sim.events_log,
            "cells_m": 500, "villages": [[2000, 2000], [6000, 2500], [4000, 6000]][: cfg.n_villages], "base": [600, 7400]})


def _clean(o):
    if isinstance(o, float) and o != o:
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o
