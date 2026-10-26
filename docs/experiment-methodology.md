# Experiment methodology

## Common scenario (`simulator/scenario.py`)
* 3 villages (cells of 500 m), 2 field nodes + 2 multi-sensor nodes (flood, smoke, vibration) per village,
  3 ferries cycling base→V0→V1→V2→base at 8 m/s with 300 s dwell, 2 responders at base. 17 nodes.
* 60 s steps, 3 h horizon, radio range 600 m, 1000 B/s per contact (half per direction), storage 256 KB field,
  128 KB sensor, 1 MB ferry, responders unbounded.
* Human Poisson reports per village per hour (×load): TRAPPED 2, MEDICATION 2, WATER_REQUEST 6, SAFE 30;
  WATER_REQUEST surge +40/h in village 1 from t=3600 s. Duplicate re-submissions with probability 0.3
  (1–3 extra, same observation, new message id, random field node in the village). Raw evidence sizes:
  trapped 4096 B, medication 2048 B, water 256 B, safe 128 B.
* Environment: flood in village 0 (30→220 cm), slow rise in village 1, fire in village 2 from 5400 s,
  earthquake shaking in village 1 (0.3 g, 4000–4420 s).
* Each mode is run on identical node placements, contact traces and workloads (separate RNG streams).

These parameters are **assumptions**, chosen to create resource pressure; they are not calibrated to a real
deployment.

## Metrics (`simulator/engine.py`)
* **Critical events** = registry-critical observations (TRAPPED, MEDICATION, COLLAPSE_RISK HIGH counted at its
  triggering transition so the denominator is mode-independent).
* **CDR** = critical events whose mandatory invariants are present and *equal to the original* at a responder
  by the horizon / critical generated. `CDR_any` counts delivery in any form.
* **Critical-information loss** = critical events delivered without their invariants, or absorbed into an
  aggregate at some node and never delivered usable, / generated.
* **TBT** = all bytes charged on contacts (offers + payloads + evidence + recovery).
* **SA(t)** = 0.5·(usable critical fraction) + 0.3·(fraction of SAFE/WATER cells with ≥3 reports whose responder
  estimate is within ±25 %) + 0.2·(fraction of sensor (type, cell) pairs with responder information ≤900 s old).
  **SAT** = first time SA ≥ 0.6 (censored if never; reported with censor counts). SA_mean = time-average.
* **Peak storage** = max over non-responder nodes and time of stored bytes (queue for record modes; protected +
  sketches + evidence for CPMM modes).
* **Summary error** = mean |estimate − truth| / truth over SAFE/WATER cells with ≥3 reports at the horizon.
* **Utility/kB** = Σ utility-at-generation of usably delivered critical events + Σ per cell of
  (utility of aggregatable reports × min(1, estimate/truth)) per kB transmitted (no credit for over-count).
* **ECP false/missed/latency** are relative to an *oracle* that evaluates the same rule on exact ground-truth
  counts. Record-based modes have no distributed ECP; for them the same rule is evaluated centrally at the
  responder on exact distinct counts of delivered records (reported as `central_exact_at_responder`).
* **Energy proxy** = 1 µJ/B tx + 0.5 µJ/B rx + sensor sampling/publishing energy.

## Experiments
| Id | Script | Design |
|---|---|---|
| E1 | `e1_spl_property.py` | 200 000 random AEIO × random mutation (11 kinds incl. adversarial edits); lock vs independent oracle; plus 200 000 `transition()` calls |
| E2 | `e2_ecp_duplicates.py` | single cell; true populations 10…150; replay ×1…×100; raw count vs exact distinct vs HLL; 20 seeds |
| E3 | `e3_network_load.py` | load 0.5,1,2,4,8 × 9 baselines × 5 seeds |
| E4 | `e4_source_loss_recovery.py` | mode I; both village-0 field nodes destroyed at 5400 s; request at 5460 s; R=0,1,3,5; 0 % and 10 % corrupted replicas; 10 seeds |
| E5 | `e5_sensor_burst.py` | sensor publish period 60/30/15/5 s × 9 baselines × 3 seeds |
| E6 | `e6_convergence.py` | end-states of H runs (2 seeds); 20 random encounter permutations each with 20 % duplicate deliveries |
| E7 | `e7_ml_gated.py` | ML-1 thresholds, ML-2 duplicate prior, ML-3 saliency on synthetic generators with disjoint train/test seeds |
| E8 | `e8_ml_network_integration.py` | J vs I in the network simulator (integration check, not a benefit test) |

Every result file has a manifest in `results/manifests/` with seeds, scenario, code version (git sha),
policy version, registry digest, timestamp and configuration; every raw row also carries its full config.
