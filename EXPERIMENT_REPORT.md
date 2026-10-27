# SAGE-DTN experiment report

All numbers below are copied from `results/tables/*.csv`, produced by `python experiments/run_all.py`.
Each experiment writes a manifest in `results/manifests/` recording seeds, scenario, configuration, code
version (git sha; every manifest in this run records `1.1.0+gb085bbc`), policy version (`SPL-1.0.0`, registry digest `12a165f1f65d0f83`) and UTC timestamp.
Every result is from a **synthetic simulation** of one scenario family. Nothing here was measured on hardware
or in the field. This report does not declare success automatically: each hypothesis is assessed against
the baselines, and where a simpler baseline wins, that is stated.

## 1. Method
* **Scenario.** About 8×8 km split into 500 m cells; 3 villages with 2 field nodes and 2 sensor nodes each
  (each sensor node runs water-level, smoke and vibration sensors), 3 mobile ferries on a looped route,
  2 responders at a base; 3-hour horizon; 1 kB/s contact bandwidth. Human reports from a Poisson workload
  with surges, duplicates and replays. 60 s simulation tick; contacts have a byte budget. Full parameters
  are in `simulator/scenario.py` (`ScenarioConfig`) and in each manifest.
* **Ground truth.** Every generated object is registered once. A critical event counts as delivered when a
  usable representation (all SPL invariants intact) reaches the responder. Aggregates are checked against an
  exact oracle (`cpmm/exact.py`).
* **Metrics.** CDR (critical delivery rate, usable), critical_info_loss (critical events destroyed by
  reduction), TBT (total bytes transmitted), peak node storage, SA (situational awareness =
  0.5·critical + 0.3·aggregate accuracy + 0.2·sensor freshness), SAT (first time SA ≥ 0.6; censored if never),
  ECP missed/false/latency, evidence at responder, energy proxy.
  Definitions: `docs/experiment-methodology.md`.
* **Statistics.** Means over seeds with 95 % CI half-widths (t-distribution) in the CSVs. Seed counts are
  small (2–20), so differences inside the CI are not claimed.

## 2. Baselines
| Mode | Description |
|---|---|
| A | Epidemic flooding |
| B | Store-and-forward (gradient toward responder) |
| C | Priority-only queue |
| D | Utility-only (utility ordering and eviction, no representation change) |
| E | Adaptive fidelity **without** SPL (utility-proposed reduction committed unchecked) |
| F | Utility + SPL (record store, naive summaries) |
| G | Utility + SPL + CPMM (no ECP) |
| H | Full deterministic core (G + ECP) |
| I | H + evidence replicas and recovery |
| J | I + gated ML threshold advisor (ML-1) |

## 3. Results

### E1: SPL safety property (`e1_spl_summary.csv`)
200,000 random transitions over all event types and fidelity levels. 138,060 forbidden attempts were all
rejected (0 committed). 61,940 legal attempts were all committed (0 false rejections). Legality was judged
by an independently written oracle (`spl/oracle.py`), so the permit agreed with it on every trial.
`SemanticPreservationLock.transition` committed 0 forbidden representations. The firmware C++ port (`firmware/common/test_sage_core.cpp`) also
committed 0 of 90,109 forbidden mutations.

### E2: ECP under duplicate replay (`e2_ecp_summary.csv`, 20 seeds, 160 cases per multiplier)
| Method | ×1 false / missed | ×2 false | ×5–×100 false | Estimate ratio | State bytes ×100 |
|---|---|---|---|---|---|
| Raw message count | 0 / 0 | 0.525 | 1.0 | = multiplier | 84,284 |
| Exact distinct set | 0 / 0 | 0 | 0 | 1.0 | 6,119 |
| HLL sketch (p=8) | 0.024 / 0.128 | 0.025 | 0.025 | 0.997 | 2,919 |

The sketch estimate is independent of the replay multiplier. It is not free: about 12.5 % of near-threshold
cells are missed and 2.5 % are false, due to HLL error (max relative error 0.113). An exact distinct set has
no error and is only about 2× larger at ×100; at this scale the exact set is the better ECP input. The sketch
pays off only where its fixed size matters (state bytes grow with distinct keys for the exact set, not for HLL).

### E3: Network load sweep (`e3_network_load_summary.csv`, 5 seeds, loads 0.5×–8×)
| Load | Best non-core CDR | H CDR | H TBT vs D TBT | H peak storage vs D | E critical_info_loss |
|---|---|---|---|---|---|
| 0.5× | B, D, F 0.855 | 0.855 | 2.90 MB vs 6.06 MB | 141 KB vs 645 KB | 0.028 |
| 1× | F 0.836 | 0.836 | 3.35 MB vs 6.86 MB | 200 KB vs 718 KB | 0.065 |
| 2× | F 0.835 | 0.835 | 4.06 MB vs 8.01 MB | 281 KB vs 997 KB | 0.113 |
| 4× | F 0.847 | 0.868 | 5.22 MB vs 10.08 MB | 392 KB vs 1049 KB (full) | 0.176 |
| 8× | F 0.801 | 0.833 | 7.02 MB vs 15.05 MB | 566 KB vs 1049 KB (full) | 0.226 |

* At load ≤2×, **Utility + SPL (F) delivers the same CDR as the full core**, and at ≤0.5× so do plain
  store-and-forward (B) and utility-only (D). The CDR advantage of H appears only at 4× and 8×, and even
  there F is within 0.02–0.03. The full core's consistent gains are in **bytes (about 50 % lower TBT), peak
  storage (2.6–4.6× lower) and SA_mean (0.44–0.46 vs ≤0.38)**, not in CDR.
* Mode E (reduction without SPL) destroys critical information in proportion to load (2.8 % to 22.6 %),
  while every SPL mode loses 0 %. This is the clearest effect of SPL.
* SAT: G–I reach SA ≥ 0.6 at 5,520–6,480 s at every load. F is censored (never reaches it) at 4× and 8×;
  A–D are censored at ≥2×.
* ECP: H missed 0–1.4 ECP events per run against 1.8–7.4 for G (which has no ECP) and 0–5.6 for record modes
  using a central exact detector at the responder. No false ECP in any mode. ECP latency in H rose with load
  (876 s at 0.5× to 1,571 s at 8×), above the record modes' 936–1,104 s at ≥4×.
* **Evidence at responder is worse in CPMM modes.** The fraction of critical events whose raw evidence reached
  the responder was 0.06–0.33 for G–I versus up to 0.86 for record modes at low load (B 0.855 at 0.5×). CPMM
  keeps evidence in the sealed store and forwards it separately; record modes carry it inside every message.
  At 8× all modes deliver little evidence (F 0.0, H 0.062, B 0.335).

### E4: Source loss and evidence recovery (`e4_recovery_summary.csv`, 10 seeds, 35 requests per cell)
| Placement | Corrupt replica prob. | R=0 | R=1 | R=3 | R=5 |
|---|---|---|---|---|---|
| first_contact | 0.0 | 0.0 | 0.029 | 1.0 (3,384 s) | 1.0 (743 s) |
| first_contact | 0.1 | 0.0 | 0.029 | 1.0 (3,384 s) | 1.0 (1,020 s) |
| prefer_mobile | 0.0 | 0.0 | 1.0 (1,206 s) | 1.0 (180 s) | 1.0 (180 s) |
| prefer_mobile | 0.1 | 0.0 | 0.829 (1,138 s) | 1.0 (264 s) | 1.0 (264 s) |

(Values are recovery probability with mean latency.) Corrupted replicas were detected 3–8 times per
configuration with corruption, and **0 corrupt evidence was accepted** in any configuration. Placement
matters more than replica count: first-contact placement at R=1 puts the replica in the same village, which
is destroyed with the source.

### E5: Sensor publish-rate sweep (`e5_sensor_burst_summary.csv`, 3 seeds, 1–12 publications/min/sensor)
| Rate/min | B CDR_human | C | D | F | G/H/I |
|---|---|---|---|---|---|
| 1 | 0.789 | 0.809 | 0.809 | 0.828 | 0.828 |
| 2 | 0.510 | 0.800 | 0.694 | 0.731 | 0.828 |
| 4 | 0.385 | 0.760 | 0.694 | 0.694 | 0.828 |
| 12 | 0.375 | 0.722 | 0.694 | 0.694 | 0.828 |

* In CPMM modes, human-report CDR does not change as sensor traffic grows 12×, because sensor data enters
  bounded sketches. Every record mode degrades, priority-only (C) least.
* Sensor bytes at 12/min: H 4.36 MB vs F 14.65 MB vs A 100.2 MB. Responder sensor state: H 153 KB vs F 3.10 MB.
* Sensor-rate adaptation (H, I vs G) reduced sensor observations at 12/min by 13 % (H) and 24 % (I), and the
  energy proxy from 2,343 J (G) to 2,089 J (H) and 1,871 J (I), with no change in CDR. At ≤4/min adaptation
  had no effect in H.

### E6: Convergence (`e6_convergence_summary.csv`, 2 seeds × 20 random merge orders, 17 nodes)
All 17 nodes differed before merging. After all-pairs merging in every order: 0 mismatching nodes,
**1 distinct final state digest per seed across all 20 orders**, 0 ECP disagreement between nodes, 0
explicit conflicts. Only 2 seeds were run because of compute limits.

### E7: Gated ML, offline (`e7_ml*_summary.csv`)
* **ML-1 threshold advisor (1,000 cells):** gated ML missed 0.377 and false 0.015 versus the deterministic
  adaptive threshold 0.384 / 0.025. The difference is inside the noise. Fixed threshold: missed 0.743. The
  gate clamped 64 % of proposals. Ungated ML (diagnostic only) missed 0.007 but would be unsafe without a gate.
* **ML-2 duplicate prior (200 cells):** gated ML mean relative error 0.066 vs deterministic heuristic 0.479
  vs exact keys 0.800, with 20 false merges (vs 1). The training and test data come from the same synthetic
  duplicate generator, so this gain is **generator-dependent** and is not evidence of field performance.
* **ML-3 saliency (2,000 records):** gated ML recall 1.0 vs keyword regex 0.661, 0 false preserves, 11.6 vs
  7.6 extra bytes/record, 0 SPL violations. Same caveat: the text generator is synthetic and matches training.

### E8: Gated ML in the network (`e8_ml_network_summary.csv`, 3 seeds)
| Load | Mode | CDR | TBT | ECP detected / false | ECP latency |
|---|---|---|---|---|---|
| 1× | I | 0.837 | 3.89 MB | 1.67 / 0 | 900 s |
| 1× | J | 0.837 | 3.90 MB | 2.33 / **0.67** | 900 s |
| 4× | I | 0.859 | 5.61 MB | 5.67 / 0 | 1,648 s |
| 4× | J | 0.859 | 5.63 MB | 5.67 / 0 | 711 s |

ML in the loop left CDR, bytes and SPL unchanged. At 1× it **added false ECP events** (0.67 per run). At 4×
it reduced ECP latency. With 3 seeds neither effect is established.

## 4. Failures
* **E5 was invalid in its first run.** Sensors stepped once per 60 s tick, so publish periods below 60 s had
  no effect and every rate gave identical output. Fixed by sub-stepping sensors (`simulator/engine.py`), a
  regression test was added, and E5 was rerun. The figures above are from the fixed run.
* Evidence delivery to responders: CPMM modes deliver less evidence than record modes (E3).
* ECP sketch inputs miss about 12.5 % of near-threshold events (E2).
* First-contact replica placement with R=1 recovered 2.9 % of evidence (E4).
* ECP latency in H exceeds record modes at high load (E3).

## 5. Unexpected behaviour
* Mode I keeps evidence replicas on sensor nodes; the extra storage raises their pressure and triggers sensor
  adaptation, so I uses less energy than H (444 vs 561 J at 8×) and has slightly lower SA.
* Raw-count ECP fires *before* the true threshold crossing under replay (negative mean latency in E2), which
  looks fast but is a false alarm mechanism.
* G and H have identical CDR, TBT and SA; ECP adds about 1 % bytes.
* prefer_mobile R=3 and R=5 give identical recovery latency (180 s): the first ferry contact after the
  request already carries a replica.

## 6. Core hypothesis assessment
| Hypothesis | Verdict in simulation | Evidence |
|---|---|---|
| SPL prevents utility-driven reduction from destroying critical information | **Supported** | E1; E3 E vs F (2.8–22.6 % vs 0 %) |
| Full core delivers more critical information than simpler baselines | **Not supported at load ≤2×; small gain at 4–8×** | E3: F equals H at ≤2×; H +0.02–0.03 over F at 4–8× |
| CPMM reduces bytes and storage at equal or better CDR | **Supported** | E3: ~50 % TBT, 2.6–4.6× storage; E5 |
| CPMM isolates human reports from sensor traffic | **Supported** | E5: CPMM CDR flat, record modes fall |
| ECP is replay-resistant | **Supported, with error** | E2: estimate independent of multiplier; 12.5 % missed near threshold |
| Independent nodes converge to the same state and ECP events | **Supported (2 seeds)** | E6 |
| Evidence survives source loss with integrity | **Supported when replicas are placed on mobile nodes** | E4 |
| Full core improves evidence delivery | **Refuted** | E3 critical_evidence_at_responder |

## 7. ML assessment
ML-1 gave no advantage over the deterministic adaptive threshold and, in the network (E8), added false ECP at
1×. ML-2 and ML-3 improved over their deterministic baselines only on synthetic data from the same generator
used for training. Every ML path is gated (`ml/gates.py`): no gated variant produced an SPL violation or
created a protected event on its own. **No ML advantage is claimed.** ML embodiments should stay optional,
dependent, and unclaimed as effects.

## 8. Limitations
* One synthetic scenario family with hand-chosen parameters; no real mobility traces or disaster data.
* Radio is an abstract contact model with a byte budget; no PHY, interference or LoRa duty cycle.
* Seed counts are small (E3 5, E5 3, E6 2, E8 3). Several differences are within the CI.
* Energy is a proxy (per-sample, per-publish, per-byte constants), not measured current.
* Encryption is simulated (HMAC-CTR + tag). Not audited.
* Firmware is compiled and tested on a host stub only; it was not flashed to an ESP32. The Wokwi project
  was not executed in this environment.
* SA weights and the 0.6 SAT threshold are design choices; other weights could reorder modes.

## 9. GO / NO-GO
* **GO** for continued development of the deterministic core (SPL + CPMM + ECP) and for hardware trials:
  safety (E1, E3), resource efficiency (E3, E5) and convergence (E6) held in simulation.
* **NO-GO** for any claim that the core delivers more critical messages than Utility + SPL at moderate load,
  or that it improves evidence delivery.
* **NO-GO** for claiming an ML benefit.
* **Conditional:** evidence recovery is GO only with mobile-preferring replica placement.
* Before any external claim: run more seeds, real mobility traces, and on-device energy measurements.
