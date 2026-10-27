"""Shared experiment utilities: result storage with provenance manifests and a process pool."""
from __future__ import annotations

import csv
import json
import math
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.version import code_version  # noqa: E402
from spl.registry import default_registry  # noqa: E402

RAW, TABLES, PLOTS, MANIFESTS = (ROOT / "results" / d for d in ("raw", "tables", "plots", "manifests"))
for d in (RAW, TABLES, PLOTS, MANIFESTS):
    d.mkdir(parents=True, exist_ok=True)


def workers() -> int:
    return int(os.environ.get("SAGE_WORKERS", max(1, (os.cpu_count() or 2))))


def quick() -> bool:
    return os.environ.get("SAGE_QUICK") == "1"


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None):
    if not rows:
        path.write_text("")
        return
    fields = fields or [k for k in rows[0] if k != "config"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (r.get(k) if not isinstance(r.get(k), float) or not math.isnan(r.get(k)) else "") for k in fields})


def write_manifest(name: str, *, seeds, scenario: str, configuration: dict, outputs: list[str], started: float, extra=None):
    reg = default_registry()
    m = {"experiment": name, "seeds": list(seeds), "scenario": scenario, "code_version": code_version(),
         "policy_version": reg.policy_version, "registry_digest": reg.digest,
         "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "wall_s": round(time.time() - started, 1), "python": sys.version.split()[0], "platform": platform.platform(),
         "configuration": configuration, "outputs": outputs}
    if extra:
        m.update(extra)
    (MANIFESTS / f"{name}.json").write_text(json.dumps(m, indent=2, default=str))


def _run_one(args):
    from simulator.engine import run
    from simulator.scenario import ScenarioConfig
    cfg_d, mode = args
    r = run(ScenarioConfig.from_dict(cfg_d), mode)
    return r


def run_many(jobs: list[tuple[dict, str]]) -> list[dict]:
    with ProcessPoolExecutor(max_workers=workers()) as ex:
        return list(ex.map(_run_one, jobs))


def mean_ci(xs):
    import numpy as np
    xs = [x for x in xs if x == x]
    if not xs:
        return float("nan"), float("nan")
    a = np.array(xs, dtype=float)
    if len(a) < 2:
        return float(a.mean()), float("nan")
    return float(a.mean()), float(1.96 * a.std(ddof=1) / math.sqrt(len(a)))
