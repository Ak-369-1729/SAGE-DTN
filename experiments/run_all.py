"""One command to run every experiment and regenerate tables/plots/report.

    python experiments/run_all.py          # full run (~30-60 min on 4 cores)
    SAGE_QUICK=1 python experiments/run_all.py   # reduced seeds/sweeps for a smoke run
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["e1_spl_property.py", "e2_ecp_duplicates.py", "e6_convergence.py", "e4_source_loss_recovery.py",
         "e3_network_load.py", "e5_sensor_burst.py", "e7_ml_gated.py", "e8_ml_network_integration.py",
         "plots.py", "make_report_tables.py"]


def main():
    steps = sys.argv[1:] or STEPS
    for s in steps:
        t = time.time()
        print(f"==> {s}", flush=True)
        r = subprocess.run([sys.executable, str(HERE / s)], cwd=HERE)
        print(f"<== {s} exit={r.returncode} {time.time() - t:.0f}s", flush=True)
        if r.returncode != 0:
            sys.exit(r.returncode)


if __name__ == "__main__":
    main()
