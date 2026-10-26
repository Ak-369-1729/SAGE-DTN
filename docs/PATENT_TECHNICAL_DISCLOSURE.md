# Patent technical disclosure (draft for patent-agent review)

> Prepared after implementation and experiments. Applicant, inventors and ownership are placeholders.
> Measured values are quoted only from `results/` files and are identified by file. This is not legal
> advice and does not predict grant.

**Applicant:** `[APPLICANT]` · **Inventor(s):** `[INVENTOR(S)]` · **Reference:** SAGE-DTN · **Date:** `[DATE]`

## 1. Title
System and method for semantics-preserving, utility-governed management of emergency information in a
disruption-tolerant network of resource-constrained nodes, with criticality-partitioned mergeable state and
deterministic emergent-event promotion.

## 2. Technical field
Wireless and disruption-tolerant communication networks; distributed data replication in intermittently
connected networks of battery-powered nodes; Internet-of-Things sensing nodes for emergency and disaster
response. More specifically, controlling the representation, storage, replication and transmission of
information objects on nodes whose bandwidth, storage, contact time and energy are limited.

## 3. Background
During floods, earthquakes, fires and similar events, cellular, Internet and power infrastructure may fail
together. Delay/disruption-tolerant networks (e.g. the bundle protocol of RFC 9171) carry data by
store-and-forward across intermittent contacts. Replication-based routing (epidemic, spray-and-wait,
probabilistic) and utility-driven replication (e.g. RAPID, 2007) decide *which* bundle to send, copy or
drop. Priority schemes rank emergency traffic. Content-aware redundancy elimination (e.g. CARE, 2012)
drops similar disaster images. Aggregation under low bandwidth is known for emergency calls (e.g.
US8160537B2). Conflict-free replicated data types (2011) and cardinality sketches such as HyperLogLog (2007)
provide mergeable state. Threshold detection over crowd reports is known in social-media analytics.

## 4. Technical problem
A node that cannot afford to store or forward every full observation must change the *representation* of
information (drop fields, summarise, aggregate) to keep buffers, bytes and energy within limits. Known
schemes either (a) keep full objects and only reorder/drop whole objects — so buffers overflow and critical
objects are dropped under load, or (b) compress/aggregate without a machine-checkable notion of which fields
are operationally indispensable, so pressure can destroy, e.g., the location of a trapped person. In
addition, (c) aggregated counts replicated over multiple paths and replays inflate, so aggregate-based
decisions (e.g. "water shortage in cell X") become unreliable, and (d) when a source node is destroyed,
reduced records can no longer be expanded to their evidence.

## 5. Objects
1. Bound node storage and transmitted bytes for low-criticality, high-volume observations.
2. Guarantee, by a deterministic check on the concrete reduced representation, that no resource-driven
   transformation removes the mandatory semantics of an emergency event type.
3. Make aggregate state duplicate- and replay-insensitive and mergeable in any encounter order.
4. Derive new protected emergency events from aggregate state such that every node derives the same event.
5. Allow verified recovery of high-fidelity evidence after loss of the originating node.
6. Allow optional learned advisors only through deterministic gates.

## 6. Summary
Each node converts human reports and sensor readings into typed information objects (AEIOs). A utility
engine computes an information utility and a node resource pressure and **proposes** a target fidelity level.
A Semantic Preservation Lock (SPL) **disposes**: it generates the concrete candidate representation and
commits it only if (i) the target level does not exceed the event type's minimum fidelity and (ii) every
invariant listed for the event type in a versioned registry, extracted from the candidate, equals the value
extracted from the source; otherwise it clamps to the most-reduced permitted representation. Committed
objects enter a criticality-partitioned mergeable map (CPMM): a protected map of individually addressable
records that are never evicted, and a bounded aggregate state of duplicate-insensitive cardinality sketches
keyed by event type, geographic cell, time window and value bucket; raw evidence is sealed in a separate
evidence store with an integrity commitment and locator. Nodes exchange deltas at contacts and merge
deterministically (commutative, associative, idempotent). An emergent-criticality-promotion (ECP) function of
the aggregate state promotes a cell to a protected derived event (e.g. WATER_SHORTAGE) whose identifier is a
function of (rule, cell) only. Evidence replicas allow authorised, integrity-verified recovery after the
source is lost. Optional ML models only propose parameters that deterministic gates bound.

## 7. Detailed description

### 7.1 Node and data model
Node roles: field (survivor reports), sensor (flood/smoke/vibration), ferry (mobile carrier), responder. An
AEIO has: event_id = H(observation_key); event_type; source_class; criticality; utility; fidelity_level
F0–F4; geo_cell; freshness {observed_at, quantum}; confidence; corroboration; preservation_class;
minimum_fidelity; semantic_invariants; aggregation_class; evidence_locator; integrity_commitment;
provenance; sensor_metadata; policy_version; payload. Fidelity levels: F0 full evidence; F1 reduced record
(no raw evidence, no free text); F2 compact (geo-cell, buckets); F3 geo-cell aggregate contribution; F4
regional contribution. (`aeio/model.py`, `aeio/codec.py`)

### 7.2 Human AEIO
TRAPPED_PERSON (trapped_status, persons, coordinates, free text, raw evidence), MEDICATION_NEED (label,
urgency, coordinates, notes), WATER_REQUEST, SAFE_STATUS. Re-submissions keep the observation key.

### 7.3 IoT AEIO
FloodGaugeSensor → WATER_LEVEL (level, bucket edges 50/100/150/200 cm, rate); SmokeSensor → SMOKE_DENSITY
(ppm, buckets 50/150/300/600); VibrationSensor → COLLAPSE_RISK (LOW/ELEVATED/HIGH at 0.05/0.2 g). Sampling
at a configured frequency into a fixed ring buffer; publication at a period scaled by an adaptation
multiplier, but **always immediately on bucket/state change**; on a rising bucket or a transition to HIGH the
ring buffer is frozen as evidence and committed (SHA-256). Sensor failure time and energy budget are modelled.
(`sensors/virtual.py`, `firmware/sensor-node/`)

### 7.4 Utility engine
U = C·(wF·F + wR·R + wS·S + wG·G + wQ·Q)/(1 + wK·K)·(1 − wD·D) with F = exp(−age/τ_type), S = 1/(1+similar),
K = bytes/2048, D = duplicate flag; pressure P = max(Σ w·x, storage occupancy, queue occupancy) over queue
occupancy, queue growth, bandwidth shortfall, storage, energy deficit, contact shortfall, human report rate,
sensor rate. Proposed fidelity = floor(5·P·(1 − min(1, U/0.5))). Actions: PRESERVE_FULL, REDUCE_FIDELITY,
AGGREGATE, DEFER, REPLICATE, INCREASE_SENSOR_AGGREGATION (publish-period multiplier 2^k), REQUEST_EVIDENCE.
All coefficients are configuration. (`utility/`)

### 7.5 SPL
Registry SPL-1.0.0 (table in `docs/architecture.md`) with a digest recorded in every result manifest.
Invariant extractors: trapped_status; usable_location = coordinates rounded to 1e-4° (~11 m);
freshness = floor(observed_at/300 s); medication label; urgency; level/density bucket; risk_state; geo_cell;
unique-count semantics = presence of a duplicate-resistant sketch key derived from the observation key (a
naive counter fails); rule_id. Permit compares concrete values, so adversarial edits (perturbing a field,
shifting a timestamp, dropping a cell, relabelling fidelity, changing type or policy version) are rejected.
The same check is implemented for microcontrollers (`firmware/common/sage_core.h`). (`spl/`)

### 7.6 CPMM
ProtectedMap: per event id the set of maximal versions under (logical_ts, fidelity); merge = union of maximal
sets; concurrent different versions retained and reported as explicit conflicts. BoundedAggregateState:
HyperLogLog (p=8) per (type, cell, 5-min window, bucket), plus device and ingest-node sketches; retention of
W windows relative to the max window; merge = register-wise max then deterministic pruning. EvidenceStore:
sealed evidence + salted SHA-256 commitment + locator; not merged. (`cpmm/`)

### 7.7 Merge and exchange
At a contact, each node offers keys changed since its last sync with that peer (8 B each), sends protected
entries in descending utility at the SPL-permitted representation chosen by its own pressure, then sketches
by type priority, then evidence and recovery traffic. Sensor nodes are producer-only.
(`simulator/cpmm_node.py`)

### 7.8 ECP
Fire for (rule, cell) iff unique ≥ T1, unique arrivals per window over L windows ≥ T2, confidence =
½min(1, devices/d) + ½min(1, ingest nodes/i) ≥ T3, and latest data window is fresh. Inputs are sketch
estimates. Output: DERIVED_PROTECTED AEIO with id H(rule_id, cell), origin "ECP", logical_ts = latest data
window, payload {rule_id, magnitude bucket, confidence bucket}; it enters the ProtectedMap and propagates.
(`ecp/`)

### 7.9 Evidence recovery
Origin places sealed evidence on up to R peers (placement policies: first-contact; prefer-mobile). Reduced
protected records carry locator and commitment. On source loss, an authorised responder issues capability-token
requests propagated epidemically; holders verify the token and return sealed evidence; the requester verifies
MAC, commitment and locator digest before promoting the record to F0; failed verification is counted and the
requester waits for another replica. (`evidence/`, `simulator/cpmm_node.py::_evidence_phase`)

### 7.10 ML-dependent embodiments
(a) Threshold calibrator → ΔT → gate: clamp to [−50 %, +150 %] of T_base, quantise to 5, floor 10; ECP
evaluates only T*. (b) Independence estimator → P(duplicate) → gate: merge sketch keys only for aggregatable
types, same cell, P ≥ 0.9, distance ≤ 50 m, Δt ≤ 1800 s (can only reduce counts). (c) Saliency proposer →
gate: may only *add* a truncated (≤64 B) field to a reduced record, which must still pass SPL. No model can
write state, override SPL, delete protected events, increase counts, fire ECP or authorise evidence access.
(`ml/`)

### 7.11 Physical node (best present implementation)
ESP32 node with Li-ion battery and voltage sense, optional LoRa (865–867 MHz) or ESP-NOW, SD storage, field
buttons/LEDs, sensor-node analog inputs (water level, MQ-2 smoke, vibration/MPU-6050), responder OLED.
Firmware in `firmware/`; BOM and pin map in `firmware/BOM.md`, `firmware/PINMAP.md`.

### 7.12 Online simulator
FastAPI + browser canvas: configure topology, resources, workload, evidence, seed and mode; visualise
nodes, contacts, storage, protected/aggregate counts, SPL decisions, ECP events, source loss, replicas,
recovery and metrics; export scenario/results. (`web/`, `app.py`)

## 8. Best mode
Mode "I" with defaults in `simulator/scenario.py` and `utility/config.py`, registry SPL-1.0.0, HLL p=8,
5-min windows, 48 windows retained, R=3 evidence replicas with prefer-mobile placement.

## 9. Technical effects and experimental results
See §9 appendix (`EXPERIMENT_RESULTS` section at the end of this file), generated after execution.

## 10. Alternative embodiments
Other sketches (KMV, Theta, HLL++ sparse); other merge orders (vector-clock versions); other geo indexing
(H3/S2); signed AEIOs; asymmetric capability tokens; erasure-coded evidence instead of full replicas;
other radios (BLE mesh, Wi-Fi Direct, satellite burst); registry distribution by signed policy updates;
gateway re-hashing between MCU and edge sketches.

## 11. Drawing descriptions
Fig. 1 node hardware block diagram. Fig. 2 information pipeline (utility → SPL → CPMM → merge → ECP →
recovery). Fig. 3 fidelity ladder F0–F4 with per-type permitted region. Fig. 4 SPL permit flowchart.
Fig. 5 CPMM structure and merge. Fig. 6 ECP decision flow. Fig. 7 evidence recovery sequence after source
loss. Fig. 8 gated-ML flow. Fig. 9 CDR vs TBT. Fig. 10 false ECP vs replay multiplier. Fig. 11 recovery vs
replicas. Fig. 12 responder sensor state vs observations. (Figs. 9–12 from `results/plots/`, to be redrawn.)

## 12. Abstract
A disruption-tolerant emergency node converts human reports and sensor readings into typed information
objects. A utility engine proposes, from information utility and node resource pressure, a target fidelity
for each object; a semantic preservation lock commits the concrete reduced representation only if it meets
the event type's minimum fidelity and preserves every registered invariant, otherwise clamping to a
permitted level. Committed objects are held in a criticality-partitioned state comprising a never-evicted
protected map, bounded duplicate-insensitive sketches per cell and time window, and a sealed evidence store,
merged deterministically between nodes at contacts. A deterministic promotion function converts sketch-derived
aggregates into protected derived events with node-independent identifiers. Sealed evidence replicated to
peers is recoverable with authorisation and integrity verification after the source node fails. Optional
learned advisors act only through deterministic gates.

## 13. Draft claims (initial set; see `CLAIMS_PROSECUTION_DRAFT.md` for the revised set)

**Independent A (system/method — utility + SPL + partitioned state + merge).**
1. A method performed by a node of a disruption-tolerant network, comprising: receiving an observation and
   forming an information object having an event type, a fidelity level and a payload; computing a utility of
   the object and a resource pressure of the node from at least storage occupancy and one of bandwidth,
   energy, contact opportunity and observation arrival rate; determining from the utility and the pressure a
   proposed reduced fidelity level; generating a candidate representation of the object at the proposed
   level; extracting, for each invariant listed for the event type in a versioned invariant registry, a value
   from the candidate and from the object; committing the candidate only if the proposed level does not
   exceed a minimum fidelity of the event type and all extracted values are equal, and otherwise committing a
   less-reduced representation for which the condition holds; storing committed objects of protected event
   types as individually addressable records that are not evicted and inserting committed objects of
   aggregatable event types into a bounded duplicate-insensitive sketch keyed by event type, geographic cell
   and time window; and, upon contact with a peer node, merging the records and sketches by an operation that
   is commutative, associative and idempotent.
2–16. Dependent claims: human AEIO types; IoT AEIO types; flood sensor; smoke sensor; vibration sensor with
   conditional protection; freshness quantum invariant; sensor publish-rate adaptation with immediate
   publication on bucket change; ring buffer freeze on trigger; evidence locator; integrity commitment;
   replica placement; recovery after source loss; utility-ordered byte-budgeted transmission; storage/energy
   pressure terms; explicit retention of conflicting maximal versions.

**Independent B (duplicate-resistant aggregate → deterministic ECP → protected state).**
17. A method comprising: maintaining, at each of a plurality of intermittently connected nodes, mergeable
   duplicate-insensitive cardinality sketches of observation keys per event type, geographic cell and time
   window, and sketches of distinct reporting devices; merging sketches at contacts by register-wise maximum;
   evaluating, at a node, a deterministic rule that fires for a cell when the sketch estimate of unique
   observations over retained windows, the estimate over a recent window span, a confidence derived from the
   device sketch and a freshness of the latest window each satisfy thresholds; and upon firing, creating a
   protected derived event whose identifier is a deterministic function of the rule and the cell, and
   inserting it into a protected record store that is merged between nodes; whereby replayed copies of an
   observation do not change the estimate and independently evaluating nodes create the same derived event.
18–22. Dependents: WATER_REQUEST→WATER_SHORTAGE; SMOKE_DENSITY elevated buckets→POTENTIAL_FIRE_CLUSTER;
   ingest-node corroboration; magnitude bucketing; evidence request upon promotion.

**Independent C (gated ML).**
23. The method of claim 1 or 17, further comprising: obtaining from a trained model a proposed adjustment of
   at least one of an ECP threshold, a duplicate relation between two observations, and a set of additional
   fields to preserve; and applying a deterministic gate that (i) bounds and quantises a threshold
   adjustment, (ii) permits a duplicate relation only for aggregatable event types within a distance and time
   limit and only so as to reduce a count, or (iii) permits only the addition of a size-bounded field to a
   representation that still satisfies the invariant check; wherein the model output never directly writes
   records, fires a promotion, removes an invariant, increases a count or authorises evidence access.
24–26. Dependents: gated threshold calibration; gated duplicate prior; gated saliency.

**Apparatus.** 27. A node comprising a processor, a radio, storage and a battery configured to perform the
method of claim 1. 28. A computer-readable medium storing instructions which when executed perform claim 1.
