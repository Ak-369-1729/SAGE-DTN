# Simulated First Examination Report (self-attack, not an IP India document)

Application: SAGE-DTN draft claims in `PATENT_TECHNICAL_DISCLOSURE.md` §13. Examined as an Indian examiner
might, against the preliminary references in `PRIOR_ART_MATRIX.md` (D-numbers below = matrix rows).

## 1. Novelty (Sec. 2(1)(j), 13)
* **Claim 1:** No single reference located discloses all of: utility+pressure proposed fidelity, a per-type
  invariant registry checked on the concrete candidate with clamping, protected/never-evicted records plus
  bounded duplicate-insensitive sketches, and lattice merge at contacts. Novelty **likely** over the located
  documents, subject to a professional search. **Objection not raised**, but D4 (RAPID), D6 (CARE), D7
  (US8160537B2) and D9 (CRDTs) each disclose parts.
* **Claim 17:** D11 (HLL) + D19 (threshold event detection over aggregated reports) disclose the elements
  separately. The combination in a DTN with a node-independent derived identifier was not located.
  Novelty **likely**, inventive step contested (below).
* **Claim 23:** D17 (ResQNet) discloses ML prioritisation in disaster meshes; gated bounding of ML output
  before a deterministic protected-state rule not located. Novelty likely.

## 2. Inventive step (Sec. 2(1)(ja))
* **Objection IS-1 (Claim 1):** A person skilled in the art starting from D4 (utility allocation of
  bandwidth/storage in DTN) would, facing buffer limits, look to D7 (aggregate emergency information when
  bandwidth is below a threshold) and to schema-based field filtering; ensuring essential fields survive is
  an obvious design requirement; merging replicated state with CRDTs (D9) is routine. *Applicant's likely
  response:* (a) D7 aggregates calls without any per-type invariant check on the produced representation and
  without the clamp-to-permitted-level behaviour; (b) the claimed check yields a measured effect not present
  in the combination: in E3, the same utility-driven reduction without the lock (mode E) lost 2.8–22.6 % of
  critical events to semantic destruction across loads 0.5×–8× while the locked modes (F–I) lost 0 %
  (`results/tables/e3_network_load_summary.csv`, column `critical_info_loss`); (c) a further measured effect
  arises only from the coupling with CPMM: Utility+SPL with naive counters cannot aggregate at all (the
  unique-count and freshness invariants fail), whereas with sketches it can, giving lower bytes and
  storage than F at equal or better CDR (E3). **Risk: medium-high.** Strengthen by claiming the concrete
  invariant extraction (equality of extracted values from the reduced representation, quantised freshness,
  ~11 m location) and the dependency that aggregation is permitted only into a duplicate-insensitive sketch.
* **Objection IS-2 (Claim 17):** HLL is designed for duplicate-insensitive counting (D11); applying it to
  replayed messages is its intended purpose; thresholding counts to raise alerts is known (D19).
  *Response:* the claim's contribution is the *derived event identity* H(rule, cell) inserted into a merged
  protected store so that independently evaluating nodes converge to one event (E6: one distinct final digest
  across all permutations and 0 ECP disagreement — see `e6_convergence_summary.csv`), together with the
  device/ingest confidence sketches. **Risk: high.** Consider making claim 17 dependent on claim 1, or adding
  the freshness condition and the conflict-explicit protected store as features.
* **Objection IS-3 (Claim 23):** bounding/clamping model outputs is common engineering practice.
  *Response:* claim 23 is drafted as dependent-style embodiments only; acceptable to lose.

## 3. Section 3(k) (mathematical method / algorithm / computer programme per se)
* **Objection 3k-1:** Claims 1 and 17 recite computations (utility formula, sketch estimate, thresholds) and
  may be characterised as an algorithm. *Response strategy:* claims are directed to a node of a wireless DTN
  controlling storage occupancy, transmitted bytes and energy of physical nodes; measured technical effects
  on bytes transmitted, peak node storage and delivered critical information are documented (E3, E5).
  Recite the radio, storage and battery, the byte-budgeted contact exchange and the pressure terms derived
  from physical resources in the independent claims. Avoid claiming the utility formula itself.
  **VERIFY** against the current CRI Guidelines.
* Claim 23 (ML) is most exposed; keep it dependent on a technical independent claim.

## 4. Clarity (Sec. 10(4)(c))
* "utility", "pressure", "semantic invariant", "usable location", "fresh" are relative terms → define in
  claims or by reference to measurable quantities (e.g. coordinates rounded to a stated precision; freshness
  as the observation time quantised to a stated interval).
* "bounded duplicate-insensitive sketch" → specify fixed register count and register-wise-max merge.
* "most-reduced permitted representation" is clear only if fidelity levels are ordered → define the order.

## 5. Support / sufficiency (Sec. 10(4)(a),(b))
* Supported for the event types, fidelity ladder, registry, HLL, ECP rules and recovery implemented in the
  repository. **Not supported** for: other sketches, arbitrary event types without a registry entry,
  real radios, physical deployment, numeric performance claims beyond the simulated scenario.
* Enablement: code and parameters disclosed; ESP32 firmware not built for target (host-compiled only).

## 6. Unity (Sec. 10(5))
* Claims 1, 17 and 23 may be held to define more than one invention (state governance vs aggregate
  promotion vs ML gating). Common special technical feature candidate: *the criticality-partitioned
  mergeable state whose aggregatable part is a duplicate-insensitive sketch admitted only through the
  invariant check*. Recommend making 17 depend on that state, or prepare a divisional.

## 7. Overbreadth
* Claim 1 as drafted covers any field-filtering scheme with a whitelist (e.g. message schema minimisation).
  Narrow by requiring (a) the value-equality check on extracted invariants of the concrete candidate,
  (b) the clamp fallback, and (c) the protected/never-evicted vs sketch partition.

## 8. Unsupported effects
* Draft language about "preserving critical information with lower resource cost" must be limited to the
  simulated scenario. E3 shows that at offered load ≤1× Store-and-forward and Utility-only achieve CDR
  within ~0.03 of the full core; the full core's advantage there is in bytes, storage and SA, not CDR.
  Evidence availability at responders is **lower** for the CPMM modes than for record modes (column
  `critical_evidence_at_responder`) — any claim implying better evidence delivery is unsupported.
* No effect of sensor-rate adaptation (INCREASE_SENSOR_AGGREGATION) on bytes was measured in CPMM modes
  (sensor data is already sketched); do not claim it as a bandwidth effect.

## 9. Outcome of self-examination
Proceed only with the narrowed claim set in `CLAIMS_PROSECUTION_DRAFT.md`. No new matter was added there:
every feature appears in the disclosure and the code.
