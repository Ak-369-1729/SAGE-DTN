# SAGE-DTN architecture (as implemented)

```
 human report / sensor sample
          │
          ▼
   AEIO factory ──► Utility Engine (U_i, pressure P) ──► candidate action + target fidelity
          │                                                   │
          │                                     ┌─────────────┘
          ▼                                     ▼
   EvidenceStore ◄── raw evidence        SPL: Permit(Fi→Fj)?  (registry SPL-1.0.0)
   (sealed, committed)                          │ permitted / clamped
                                                ▼
                     ┌──────────── CPMM NodeState ─────────────┐
                     │ ProtectedMap  (individual, never evicted)│
                     │ BoundedAggregateState (HLL sketches)     │
                     │ EvidenceStore (not propagated by merge)  │
                     └──────────────────┬──────────────────────┘
                                        │ delta anti-entropy at every contact
                                        ▼
                               deterministic merge (join)
                                        │
                                        ▼
                ECP (pure function of aggregate state) ──► derived protected event
                                        │
                                        ▼
         utility rises / responder request ──► authorised recovery from any replica ──► verify ──► F0
```

## 1. AEIO (`aeio/`)
`AEIO` carries every PRD field: `event_id, event_type, source_class, criticality, utility, fidelity_level,
geo_cell, freshness, confidence, corroboration, preservation_class, minimum_fidelity, semantic_invariants,
aggregation_class, evidence_locator, integrity_commitment, provenance, sensor_metadata, policy_version`, plus a
type-specific `payload` and optional raw `evidence` (F0 only). `event_id = H(observation_key)`, so duplicate
submissions of one observation share an id. The content digest excludes transport-only provenance
(`ingest_node`). `wire_bytes` = canonical-JSON header + raw evidence and is the unit of all byte accounting.

Fidelity: F0 full evidence · F1 reduced record (no raw evidence/free text) · F2 compact (geo-cell, buckets, no
precise coordinates) · F3 geo-cell aggregate contribution · F4 regional contribution. Lower number = higher
fidelity. `aeio/codec.py` is deliberately **semantics-unaware** — it is what a system without SPL would use.

## 2. Utility engine (`utility/`)
`U = C · (wF·F + wR·R + wS·S + wG·G + wQ·Q) / (1 + wK·K) · (1 − wD·D)`
* C criticality (per type, value-dependent for medication urgency, collapse risk, water/smoke bucket).
* F = exp(−age/τ_type); R responder relevance per type; S = 1/(1+similar items held in the cell);
  G geographic relevance (default 0.5 everywhere: no geographic priority map was configured); Q from
  confidence and corroboration; K = bytes/2048; D = 1 if the observation is already held.
* Rationale: criticality gates the bounded context factor (context can re-rank within a criticality band but
  cannot invert bands), the context terms form an interpretable convex combination, and cost in the
  denominator turns U into utility-per-cost for byte-budgeted scheduling. All coefficients are in
  `UtilityConfig` and overridable per scenario (`ScenarioConfig.utility`).

Pressure `P = max(Σ w_k x_k, storage_occupancy, queue_occupancy)` over queue occupancy, queue growth,
bandwidth shortfall, storage, energy deficit, contact shortfall, human report rate, sensor observation rate.

Candidate action: `target = floor(5·P·(1 − min(1, U/0.5)))` (monotone: deeper reduction with more pressure,
shallower with more utility), mapped to PRESERVE_FULL / REPLICATE / REDUCE_FIDELITY / AGGREGATE / DEFER;
`sensor_action` → INCREASE_SENSOR_AGGREGATION with a publish-period multiplier; `evidence_action` →
REQUEST_EVIDENCE. **The engine never commits a representation.**

## 3. SPL (`spl/`)
`registry_v1.json` (policy `SPL-1.0.0`, digest recorded in every manifest). Rules (min fidelity / invariants):

| Type | Class | Min | Invariants |
|---|---|---|---|
| TRAPPED_PERSON | protected | F1 | trapped_status, usable_location (≈11 m), freshness |
| MEDICATION_NEED | protected | F1 | medication label, urgency, usable_location |
| WATER_REQUEST | aggregatable | F3 | geo_cell, unique-count semantics, freshness *(registry extension)* |
| SAFE_STATUS | aggregatable | F3 | geo_cell, unique-count semantics |
| WATER_LEVEL | aggregatable | F3 | level bucket, geo_cell, freshness |
| SMOKE_DENSITY | aggregatable | F3 | density bucket, geo_cell, freshness |
| COLLAPSE_RISK | aggregatable; **protected (min F2) when ELEVATED/HIGH** | F3/F2 | risk_state, geo_cell, freshness |
| WATER_SHORTAGE, POTENTIAL_FIRE_CLUSTER | derived protected | F2 | rule_id, geo_cell, freshness |

`permit(source, candidate)` checks: type and policy unchanged; no upgrade; `level ≤ min`; every invariant
extracted from the *concrete candidate* equals the source's. `SemanticPreservationLock.transition` commits a
permitted candidate or clamps to the most-reduced permitted level. Consequence (measured, E3): with a naive
counter aggregator, unique-count and freshness invariants fail, so Utility+SPL **without** CPMM cannot
aggregate at all and falls back to F1/F2 records.

`spl/oracle.py` is an independently written legality oracle used by E1 and the property tests.

## 4. CPMM (`cpmm/`)
* **ProtectedMap** — per event id, the set of maximal versions under order (logical_ts, fidelity). Union of
  maximal sets is a join-semilattice: commutative, associative, idempotent. Concurrent different versions are
  kept and reported by `conflicts()` (contradictions are explicit, never averaged). Entries are never evicted.
* **BoundedAggregateState** — HyperLogLog (default p=8, 256 registers, RSE≈1.04/√m≈6.5 %; linear counting
  for small n) per (type, cell, 5-min window, bucket); extra sketches of distinct devices and ingest nodes for
  ECP confidence. Only the last `windows_kept` windows (relative to the max window seen) are retained, so
  size ≤ |types|·|cells|·W·(|buckets|+3)·2^p bytes. Merge = register max + deterministic pruning.
  Estimator assumptions: hash uniformity of BLAKE2b-64 over observation keys; independence of keys; error
  bound is statistical, not worst-case (E2 measured max |error| ≈ 11 % at p=8 for populations ≤150).
* **EvidenceStore** — sealed evidence (HMAC-SHA256-CTR + HMAC tag; *simulated* AEAD), salted SHA-256
  commitment, locator. Not propagated by merge.
* Storage accounting uses encoded sizes (sparse HLL when smaller).

## 5. Exchange and merge (`simulator/cpmm_node.py`)
Delta anti-entropy per peer: offer ids/keys modified since last sync (8 B each), send protected entries by
utility order, then sketches by type priority, then (I/J) evidence replication and recovery traffic. A
protected entry is sent at the representation chosen by sender utility/pressure through SPL (≥F1; raw
evidence stays in the EvidenceStore unless eager evidence forwarding is permitted by low pressure and high
utility). Sensor nodes are producer-only in **every** mode.

## 6. ECP (`ecp/`)
Fire for cell c iff UniqueDemand ≥ T1, unique arrivals per window over the last L windows ≥ T2,
confidence = ½min(1,devices/dev_ref)+½min(1,ingest/ing_ref) ≥ T3, and the latest data window is fresh.
All inputs are sketch estimates, so replays do not move them. The derived AEIO id is H(rule_id, cell) and the
origin is the constant "ECP", so independent nodes promote the same logical event.

## 7. Evidence recovery (`evidence/`, mode I)
Origin seals evidence and places it on up to R peers (preference FERRY > FIELD > SENSOR, then free space).
After source loss the responder issues capability-token requests that propagate epidemically; holders
verify the token and return sealed records; the requester verifies tag + commitment + locator before
promoting the record to F0. Corrupted replicas are detected and the requester waits for another replica.

## 8. Sensors (`sensors/`)
10 Hz sampling, Gaussian noise, publish period (×adaptation multiplier), immediate publish on bucket/state
change (threshold-adjacent preservation), 30 s ring buffer, ring freeze + commitment on rising bucket / HIGH
risk, failure time and energy budget. Sensor AEIOs follow the same utility/SPL/CPMM path as human reports.

## 9. Optional ML (`ml/`)
Threshold calibrator, independence estimator and saliency proposer, each followed by a pure deterministic gate
(`ml/gates.py`). Gates can only: bound/quantise thresholds; *reduce* counts by merging sketch keys for
aggregatable types within distance/time limits; *add* bounded preserved fields. They cannot write state,
override SPL, delete protected events, fire ECP or authorise evidence access. The system runs with ML off.
