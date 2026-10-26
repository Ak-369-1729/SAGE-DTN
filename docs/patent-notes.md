# Patent notes (working notes for the patent agent)

These are engineering notes, not legal advice. Nothing here asserts patentability or grant.

## Where the material is
| Document | Purpose |
|---|---|
| `PATENT_TECHNICAL_DISCLOSURE.md` | Technical disclosure with initial claims (§13) and the measured-results appendix |
| `CLAIMS_PROSECUTION_DRAFT.md` | Narrowed claim set after self-examination (no new matter) |
| `SIMULATED_FER.md` | Self-attack in the form of an Indian First Examination Report |
| `PRIOR_ART_MATRIX.md` | Preliminary, non-exhaustive prior-art matrix (not a professional search) |
| `INDIA_FILING_CHECKLIST.md` | Forms, timelines and placeholders, all marked VERIFY |
| `../EXPERIMENT_REPORT.md` | Measured results and GO/NO-GO, with seeds and manifests |

## Claim-family map to code
| Family | Inventive core (deterministic) | Code |
|---|---|---|
| A: governed representation change | utility + pressure → proposed fidelity; registry invariants checked on the concrete candidate; clamp to least-reduced permitted level | `utility/engine.py`, `spl/lock.py`, `spl/registry_v1.json`, `aeio/codec.py` |
| A: partitioned mergeable state | protected MV-register store (never evicted) vs bounded HLL sketches keyed by (type, cell, window, bucket); delta exchange within a byte budget | `cpmm/*.py`, `simulator/cpmm_node.py` |
| B: emergent critical promotion | 4-condition rule over sketch estimates; derived id = H(rule, cell) inserted into the protected store | `ecp/engine.py` |
| C: evidence custody | ring-buffer evidence, commitment in the protected record, sealed store, replicas, authorised recovery with tag+commitment+locator verification | `sensors/virtual.py`, `evidence/*.py`, `simulator/cpmm_node.py` |
| ML embodiments (dependent only) | ML-1 threshold proposal clamped ±range, quantised, floored, and only the deterministic rule promotes; ML-2 duplicate prior can only merge into an existing key within fixed distance/time/type/cell limits; ML-3 saliency adds ≤N bytes and re-runs the SPL permit | `ml/gates.py`, `ml/runtime_gate.py` |

The deterministic core is broader than every ML embodiment: each ML claim depends on a deterministic claim and
recites its gate. The ML is never the decision-maker ("ML proposes, deterministic policy disposes").

## Rules applied to the drafts
* Claims contain no measured numbers. Measured effects appear only in the disclosure appendix and the report,
  each tied to a results file and a seed list.
* Every effect is a simulated effect in one synthetic scenario. It is not a field result.
* Where a simpler baseline matched or beat the invention (CDR at load ≤1×; evidence at responders; ML-1 vs
  the deterministic adaptive threshold), the drafts say so and do not rely on that effect.
* "Prior art does not exist" is never asserted. Distinctions are stated as candidates for a professional search.

## Open questions for the inventor(s)
1. Inventorship: who conceived SPL-on-concrete-candidate, the CPMM partition, ECP derived identity, and the
   evidence-recovery protocol? Placeholders only in the checklist.
2. What does "groundgate" in the brief refer to? Nothing relevant was found under that term.
3. Has any part of this repository, a paper, demo or poster been made public? If so, record dates before filing.
4. Should the ML embodiments be kept at all? They add 3(k) exposure and their measured value is mixed.
