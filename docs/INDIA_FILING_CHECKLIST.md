# India patent filing checklist (draft for a registered patent agent)

Prepared 2026-10-26. Statutory basis: Patents Act 1970 and Patents Rules 2003 as amended. The Patents
(Amendment) Rules 2024 (in force 15 March 2024) changed several timelines; the 2024 points below were taken
from a law-firm summary (AZB & Partners, 28 Mar 2024), **not** from the Gazette text.
Every item marked **VERIFY** must be checked against the current IP India source
(ipindia.gov.in, Patents Rules consolidated text, official fee schedule) before filing.
No fees, inventors, applicants, ownership or legal status are asserted here.

## Parties (placeholders — do not invent)
- [ ] Inventor(s): `[INVENTOR NAME(S), NATIONALITY, ADDRESS]` — inventorship must follow actual
      conception of claimed features (SPL, CPMM, ECP, recovery, gated ML), not authorship of code/docs.
- [ ] Applicant(s): `[APPLICANT — individual / startup / small entity / university / other]`
- [ ] Ownership chain: `[EMPLOYMENT / STUDENT / FUNDING AGREEMENTS]`
- [ ] University IP policy: `[UNIVERSITY NAME]` policy reviewed; disclosure to TTO/IPR cell made?
      Revenue sharing / assignment obligations? Funding-agency (e.g. government grant) conditions?
- [ ] Assignment deed if applicant ≠ inventor (proof of right; Form 1 declaration or separate deed).
- [ ] Applicant category for fees (natural person / startup / small entity / educational institution /
      others) — **VERIFY** current definitions and documentary proof (e.g. DPIIT startup recognition).

## Forms
| Form | Purpose | When | Status |
|---|---|---|---|
| Form 1 | Application for grant (applicant, inventors, declaration of inventorship/right) | at filing | ☐ |
| Form 2 | Provisional or complete specification (title, description, claims, abstract, drawings) | at filing; complete spec within 12 months of a provisional | ☐ — draft: `PATENT_TECHNICAL_DISCLOSURE.md`, `CLAIMS_PROSECUTION_DRAFT.md` |
| Form 3 | Statement and undertaking on foreign filings (Sec. 8) | **VERIFY**: per 2024 amendment, with the application or within 6 months, and again within 3 months of the FER | ☐ |
| Form 5 | Declaration as to inventorship | with complete specification (or within the period allowed — **VERIFY**) | ☐ |
| Form 9 | Request for early publication (optional; otherwise publication at 18 months) | any time after filing | ☐ decide |
| Form 18 | Request for examination | **VERIFY**: 31 months from priority date for applications filed on/after 15 Mar 2024 (was 48 months) | ☐ |
| Form 18A | Expedited examination | only if eligible (e.g. startup, small entity, female applicant, government entity, PCT-ISA/IPEA India, etc.) — **VERIFY** current eligibility list and proof | ☐ check eligibility |
| Form 26 | Authorisation of patent agent | if filing through an agent | ☐ |
| Form 28 | Small entity / startup status proof | if claiming reduced fees as small entity/startup — **VERIFY** whether Form 28 or other proof applies to the applicant category | ☐ |
| Form 31 | Grace-period claim for prior public display (2024 amendment) | if any qualifying disclosure occurred — **VERIFY** | ☐ |
| Form 4 | Extension of time / condonation (Rule 138) | as needed — **VERIFY** limits | — |
| Form 27 | Statement of working | after grant; **VERIFY** new 3-financial-year frequency | — |

## Specification and drawings
- [ ] Decide provisional vs complete. Recommendation for agent review: a **complete** specification is
      possible now because an enabling implementation exists in this repository; a provisional secures a
      date if claims still need narrowing.
- [ ] Drawings on A4, black-and-white line drawings, sheet numbering, reference numerals consistent with
      the description (Rule 15 — **VERIFY**). Candidate figures are listed in the disclosure ("Drawing descriptions");
      generated result plots in `results/plots/` must be redrawn as line drawings if included.
- [ ] Abstract ≤150 words (**VERIFY**), with the most illustrative figure indicated.
- [ ] Claims: single inventive concept or justify unity (Sec. 10(5)); see `SIMULATED_FER.md`.
- [ ] Section 3(k) strategy: claims directed to a node/system/method producing a technical effect on
      network, storage and energy resources of physical nodes; avoid claiming algorithms "per se";
      **VERIFY** against the current CRI Guidelines (Computer Related Inventions guidelines, latest revision).
- [ ] Section 3(m)/(n) not engaged (not a mental act/presentation of information) — argue technical character.

## Priority, disclosures and timing
- [ ] **Public disclosure check**: this GitHub repository, any paper, demo, poster, thesis or hackathon
      submission. India has no general grace period beyond Sec. 29–31 exceptions — **VERIFY** before
      publishing results or making the repository public. If the repository is or becomes public before
      filing, novelty may be destroyed in India and abroad.
- [ ] Priority date = date of first filing; Paris Convention / PCT foreign filing within 12 months.
- [ ] **Foreign filing permission (Sec. 39)**: residents of India must file first in India or obtain
      permission before filing abroad (including PCT at a foreign RO) — **VERIFY** current procedure (Form 25).
- [ ] Secrecy directions check (Sec. 35) for defence-relevant subject matter — unlikely, agent to confirm.

## Fees
- [ ] Filing, specification-page/claim excess, examination, expedited examination and early-publication
      fees depend on applicant category and e-filing — **VERIFY WITH CURRENT IP INDIA FEE SCHEDULE (First
      Schedule)**. No amounts are stated here.

## Evidence package for the agent
- [ ] `docs/PATENT_TECHNICAL_DISCLOSURE.md`, `docs/CLAIMS_PROSECUTION_DRAFT.md`, `docs/SIMULATED_FER.md`
- [ ] `docs/PRIOR_ART_MATRIX.md` (preliminary; professional search needed)
- [ ] `EXPERIMENT_REPORT.md` and `results/manifests/*.json` (technical-effect evidence with seeds and git sha)
- [ ] Inventor lab notebook / commit history establishing conception dates.
