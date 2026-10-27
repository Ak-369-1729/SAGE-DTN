# SAGE-DTN

**Semantic-Adaptive Governed Emergency Utility and Disruption-Tolerant Network**: an executable reference
implementation, simulator, virtual IoT prototype and experiment suite for the architecture frozen in the
SAGE-DTN PRD v1.0.

> UTILITY PROPOSES RESOURCE ACTION. SPL CONTROLS PERMISSIBLE INFORMATION LOSS.
> ML PROPOSES. DETERMINISTIC POLICY DISPOSES.

All numbers in `results/`, `EXPERIMENT_REPORT.md` and `docs/SAGE_DTN_PRD_v1.1_Validated.md` were produced by
executing the code in this repository. Nothing was typed in by hand.

## Quick start

```bash
git clone https://github.com/Ak-369-1729/SAGE-DTN.git
cd SAGE-DTN
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest                               # unit + property + merge-convergence + simulator + web tests
python experiments/run_all.py        # all experiments -> results/raw, tables, plots, manifests (~30-60 min, 4 cores)
SAGE_QUICK=1 python experiments/run_all.py   # reduced seeds/sweeps (~5-10 min)
python app.py                        # browser simulator at http://127.0.0.1:8000
```

Run one experiment: `python experiments/e3_network_load.py` (each writes `results/raw/*.csv`,
`results/tables/*.csv|md`, `results/manifests/*.json`). Regenerate figures only: `python experiments/plots.py`.

### Virtual IoT / sensor demo

```bash
python scripts/virtual_sensor_demo.py --village 2 | python scripts/wokwi_bridge.py
bash firmware/host_stub/compile_check.sh                         # host compile+run of field & sensor sketches
g++ -std=c++17 firmware/common/test_sage_core.cpp -o /tmp/t && /tmp/t   # firmware core unit test
```
Wokwi: see `wokwi/README.md`. ESP32 build/flash: see `firmware/README.md`.

### Real radios on FIT IoT-LAB
```bash
./iotlab/run_local.sh                 # test the hardware pipeline locally (no account)
./iotlab/run_on_iotlab.sh             # on the IoT-LAB SSH frontend: reserve, flash, run E1-E6, collect
```
RIOT OS port for IoT-LAB M3 / nRF52840 nodes. See `iotlab/README.md`. Hardware results: `iotlab/results/` (PENDING until run).

### Docker
```bash
docker build -f docker/Dockerfile -t sage-dtn .
docker run -p 8000:8000 sage-dtn                  # simulator UI
docker run sage-dtn python experiments/run_all.py # experiments
```

## Repository map

| Path | Content |
|---|---|
| `aeio/` | AEIO data model (all PRD fields), event types, fidelity levels F0–F4, representation catalogue (`codec.py`), factory |
| `utility/` | Utility U_i, resource pressure P, candidate actions (PRESERVE_FULL … REQUEST_EVIDENCE); coefficients in `config.py` |
| `spl/` | Versioned invariant registry (`registry_v1.json`, SPL-1.0.0), extractors, `permit()`, gate `SemanticPreservationLock`, independent oracle |
| `cpmm/` | ProtectedMap (MV-register semilattice), BoundedAggregateState (HyperLogLog), EvidenceStore, NodeState + deterministic merge |
| `ecp/` | Emergent Criticality Promotion (WATER_REQUEST→WATER_SHORTAGE, SMOKE_DENSITY→POTENTIAL_FIRE_CLUSTER) |
| `evidence/` | IntegrityCommitment, EvidenceLocator, simulated AEAD, capability-token authorization, recovery protocol objects |
| `sensors/` | FloodGaugeSensor, SmokeSensor, VibrationSensor (sampling, noise, ring buffer, triggered evidence, failure, energy) |
| `simulator/` | Scenario/mobility/workload, record-based nodes (baselines A–F), CPMM nodes (G–J), engine and metrics |
| `transport/` | Contact/budget model notes (exchange logic lives in `simulator/*_node.py`) |
| `ml/` | Optional advisory models + deterministic gates |
| `web/`, `app.py` | FastAPI + canvas browser simulator |
| `experiments/` | E1–E8 runners, plots, report tables, `run_all.py` |
| `tests/` | pytest suite (hypothesis property tests) |
| `firmware/` | ESP32 field / sensor / responder node firmware, BOM, pin map, schemas |
| `iotlab/` | RIOT OS port for FIT IoT-LAB nodes, controller, analyzer, one-command run scripts |
| `wokwi/` | Wokwi sensor-node project |
| `docs/` | architecture, threat model, methodology, PRD v1.1, patent package, prior art, filing checklist, simulated FER |
| `results/` | Generated CSV / plots / manifests |

## System modes (baselines)
A Flooding · B Store-and-forward · C Priority-only · D Utility-only · E Adaptive fidelity without SPL ·
F Utility+SPL · G Utility+SPL+CPMM · H Full deterministic core · I Full + evidence recovery · J (optional) Full + gated ML.
All modes share the same seeds, contact traces and workloads.

## Honest status
See `EXPERIMENT_REPORT.md` for results, failures and the GO/NO-GO assessment. Not done here: ESP32 toolchain
build/flash, IoT-LAB hardware runs (scripts ready, results PENDING), Wokwi execution, field trials. The patent documents are drafts for review by a
registered patent agent; nothing here is legal advice or a promise of grant.
