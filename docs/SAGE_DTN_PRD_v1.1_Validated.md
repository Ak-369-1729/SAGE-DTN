# SAGE-DTN PRD v1.1 (validated against the reference implementation)

v1.1 restates PRD v1.0 with what was built, the configuration actually used, and what the experiments
showed. A hypothesis stays a hypothesis unless an experiment in `results/` measured it. Measured effects are
simulated effects in one synthetic scenario (see `EXPERIMENT_REPORT.md` §1 and §8).

## 1. Implementation status
| PRD v1.0 component | Status | Where |
|---|---|---|
| AEIO data model with fidelity F0–F4, provenance, utility fields | Implemented | `aeio/` |
| Semantics-unaware reducer | Implemented | `aeio/codec.py` |
| Utility engine (utility, pressure, proposed fidelity, sensor and evidence actions) | Implemented | `utility/` |
| SPL: versioned invariant registry, permit on concrete candidate, clamp | Implemented (`SPL-1.0.0`, digest `12a165f1f65d0f83`) | `spl/` |
| CPMM: ProtectedMap (MV-register), BoundedAggregateState (HLL), EvidenceStore | Implemented | `cpmm/` |
| Delta anti-entropy within a contact byte budget | Implemented | `simulator/cpmm_node.py` |
| ECP (WATER_SHORTAGE, POTENTIAL_FIRE_CLUSTER), derived id H(rule, cell) | Implemented | `ecp/` |
| Evidence ring buffer, commitments, sealed store, replicas, authorised recovery | Implemented (simulated AEAD) | `evidence/`, `sensors/` |
| Virtual sensors: water level, smoke, vibration | Implemented | `sensors/virtual.py` |
| Simulator with baselines A–J | Implemented | `simulator/` |
| Browser simulator (Run, Pause, Reset, Export scenario, Export results) | Implemented | `web/`, `app.py` |
| Gated ML-1/2/3 | Implemented, offline and (ML-1) in-network | `ml/` |
| ESP32 firmware: field, sensor, responder | Written; host-compiled and unit-tested only, **not flashed** | `firmware/` |
| Wokwi sensor project | Written; **not executed** in this environment | `wokwi/` |
| Real radio transport (LoRa/BLE/Wi-Fi) | **Not implemented**; adapter interface only | `firmware/common/radio_adapter.h`, `transport/` |
| Real AEAD (e.g. AES-GCM / ChaCha20-Poly1305) | **Not implemented** in the simulator; firmware uses mbedTLS hooks | `evidence/crypto.py` |

## 2. Configuration actually used
* Utility: `U = C·(wF·F + wR·R + wS·S + wG·G + wQ·Q)/(1 + wK·K)·(1 − wD·D)`, weights in `utility/config.py`.
* Pressure: `P = max(weighted resource sum, storage occupancy, queue occupancy)`.
* Proposed fidelity: `floor(5·P·(1 − min(1, U/0.5)))`, then the SPL permit or clamp.
* Protected types are stored at ≤F1. Raw evidence goes to the EvidenceStore. Sensor nodes are producer-only.
* HLL precision p=8, keyed by (type, cell, 5-min window, bucket), 48 windows kept, plus device and ingest
  sketches.
* ECP WATER: T1=40 distinct, T2=2 per window, T3=0.6 confidence (device ref 10, ingest ref 2).
  FIRE: T1=4, T2=0.5, buckets b2–b4.
* Scenario: `simulator/scenario.py::ScenarioConfig` defaults; each run's full configuration is in its manifest.

## 3. Measured effects (simulation)
| Claim in v1.0 | v1.1 status | Measurement |
|---|---|---|
| SPL blocks semantically destructive reduction | Measured, holds | E1: 0 of 138,060 forbidden committed, 0 false rejections; E3: E loses 2.8–22.6 % critical info, SPL modes 0 % |
| CPMM lowers bytes and storage | Measured, holds | E3: about 50 % lower TBT and 2.6–4.6× lower peak storage than D/F |
| CPMM keeps human reports flowing under sensor floods | Measured, holds | E5: G–I human CDR 0.828 at 1–12/min; F falls to 0.694, B to 0.375 |
| Faster situational awareness | Measured, holds for the SA definition used | E3: G–I SAT 5,520–6,480 s; F censored at ≥4× |
| ECP is replay-resistant | Measured, holds with sketch error | E2: estimate independent of replay ×1–×100; 12.5 % missed, 2.5 % false near threshold |
| Convergence regardless of merge order | Measured, holds (2 seeds) | E6: 1 distinct final digest across 20 orders, 0 ECP disagreement |
| Evidence recoverable after source loss, integrity enforced | Measured, holds with mobile placement | E4: prefer_mobile R≥1 recovers 1.0 (0.83 with 10 % corruption at R=1); 0 corrupt accepted |
| Sensor-rate adaptation saves energy | Measured, only at high sensor rate | E5: at 12/min, H −11 % and I −20 % energy proxy vs G; no effect at ≤4/min |

## 4. Failed or unsupported hypotheses
* **"The full core delivers more critical information than simpler policies."** Not supported at load ≤2×:
  Utility + SPL (F) matches H, and B/D match at 0.5×. At 4–8× H leads F by only 0.02–0.03 CDR (E3).
* **"The full core improves evidence availability for responders."** Refuted: G–I deliver 0.06–0.33 of critical
  evidence vs up to 0.86 for record modes (E3).
* **"HLL is required for duplicate-resistant ECP."** Not supported at this scale: an exact distinct set had 0
  error at about 2× the bytes (E2).
* **"ML improves ECP thresholds."** Not supported: ML-1 equals the deterministic adaptive threshold (E7) and
  added false ECP in the network at 1× (E8, 3 seeds).
* **"ECP is faster than central detection."** Not supported at high load: H latency 1,404–1,571 s vs 936–1,104 s
  for record modes at ≥4× (E3).

## 5. Unmeasured effects (remain hypotheses)
* Any performance on real radios, real mobility traces, real disaster data, or real ESP32 hardware.
* Real energy consumption and battery life.
* Robustness to Byzantine or malicious nodes beyond tag/commitment verification of evidence.
* Human factors: whether responders act faster with SA as defined here.
* Behaviour with more than 17 nodes, other topologies, or other SA weights.
* ML-2/ML-3 benefit outside the synthetic generator used for training.
* Cryptographic security of the evidence store (simulated AEAD only).

## 6. Requirement changes from v1.0 to v1.1
1. Evidence replicas **must** prefer mobile nodes (first-contact placement at R=1 recovered 2.9 %).
2. Sensor publishing must be simulated below the network tick (E5 bug, now fixed and tested).
3. An exact distinct-set ECP input should be offered where state budget allows; HLL stays for bounded state.
4. CPMM nodes need an evidence-forwarding policy that competes better with record modes (open problem).
5. ML stays optional, gated and off by default; no ML effect is claimed.
6. Every result must carry a manifest (seed, scenario, code version, policy version, timestamp, config).
