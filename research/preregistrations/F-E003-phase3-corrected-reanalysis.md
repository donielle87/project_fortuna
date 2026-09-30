# Preregistration F-E003 — Corrected Phase 3 Historical Deviation
# Reanalysis

- **Experiment ID:** F-E003
- **Classification:** EXPLORATORY — hypothesis generation only. This is
  explicitly NOT confirmatory, NOT predictive, and NOT a validated edge.
- **Registered:** 2026-09-30, AFTER the corrected Phase 1/2 inputs exist
  and BEFORE any corrected historical outcome is recomputed.
- **Frozen configuration:** `config/experiments/F-E003.yaml`
- **Relationship to F-E002:** F-E002 (`7463bdb`) remains the immutable
  record of the first exploratory analysis. F-E003 is a NEW experiment
  correcting for the D-007 (order/sequence provenance) and D-008
  (evidence-based draw exclusion) Phase 1 defects. F-E002 outputs,
  preregistration, config, manifest, and D-006 are preserved unedited.
- **Status:** Immutable once committed. Later defects require a
  `registry/decision_log.csv` entry and superseding documents — never
  silent edits.

## 1. Scientific objective

Identical to F-E002: compare the exploration subset of historical draws
against the fair-random null; identify anomalies worth investigation;
generate candidate hypotheses for later confirmation; preserve the
frozen holdout. F-E003 repeats the F-E002 exploratory sweep on the
corrected dataset to determine whether any F-E002 finding survives
honest data, and whether correcting the data reveals anything the
corrupted inputs masked.

## 2. Accepted inputs (frozen)

- Corrected Phase 1 dataset SHA-256:
  `200174427b4abcc6bcc0aa3761174db237ae52e266e88cfc88bae39f27c138ff`
- Phase 2 effective config: `F-E001.v4.yaml`; observation plan SHA-256:
  `8309e1dd673e339b66b1fae09d02a0f2b205a62ada2882c1590645d1bf2ac10a`
- Exclusion ledger: `metadata/draw_exclusions.csv` (D-008) —
  `decision_status=excluded` rows are the ONLY basis on which canonical
  draws were withheld from eligibility.
- Eligibility: `analysis_eligible == true AND draw_stream == main`.

## 3. Holdout preservation (frozen population, versioned seal)

- The holdout population is the ORIGINAL F-E002 set: 2,072 draw IDs in
  `metadata/phase3_holdout_ids.csv`. It is NOT recomputed, resized, or
  reshuffled. No original holdout ID moves into exploration.
- `metadata/phase3_holdout_seal.json` (v1) is the preserved historical
  seal over the original canonical rows:
  `6cb7c382924c4ad55ab0958239cb488cd95b0e0b99407ebebcfe822a4b16b91c`.
- `metadata/phase3_holdout_seal_v2.json` seals the SAME frozen IDs
  against the corrected canonical rows (row bytes differ because the
  schema gained atomic sequence provenance).
- Corrected exploration population:
  `original exploration IDs INTERSECT corrected analysis-eligible draws`
  = 8,248 draws (12 removed by evidence-based exclusions).
- No holdout winning-number outcome is parsed, printed, or summarized
  anywhere in F-E003.

## 4. Exploration-only outcome access (structural firewall)

Unchanged from F-E002: outcome reads go through the exploration-only
loader, which admits a row by `draw_id` BEFORE parsing any
winning-number field. A physical-order label is additionally admissible
only when the row carries atomic sequence provenance
(`number_sequence_source_id` naming the staged source that supplied the
stored sequence).

## 5. Exploration segments

Recomputed on the corrected dataset under the same Phase 2 rule
(documented in `metadata/phase3_split_summary_v2.csv`).

## 6-8. Test families (frozen, identical to F-E002)

- Primary: F-S001..F-S013 applicable per regime — 202 tests, frozen
  tails, one BH family q=0.10, Holm alpha=0.05.
- Exploration-matched null: 20,000 replicates (4x5,000), PCG64DXSM,
  root seed 20260930, sha256-scope-v1, experiment scope F-E003; shared
  HISTORIES streams; ORDER stream for P3-S011; EQUIP permutation for
  P3-S012; v2 convergence diagnostic.
- Secondary: P3-S001..P3-S012 definitions identical to F-E002. P3-S011
  uses only canonical `physical_draw_order` records whose sequence
  provenance is atomic (post-D-007 this is enforced by construction and
  asserted by the loader). P3-S012 unchanged.

## 9. Artifact adjudication standard (corrected)

The F-E002 heuristic "consecutive identical sets imply a phantom record;
replace the overlap contribution by its expectation" is REMOVED and is
prohibited in F-E003. Corrupt records are excluded upstream by
independent evidence (schedule violation plus authoritative-source
evidence, per the ledger). A qualifying exploratory flag can be withheld
from promotion ONLY by independently documented data-quality evidence
(a ledger row or a decision-log record) - never because the event is
improbable under the fair null.

## 10. Anomaly flags and promotion (frozen, identical to F-E002)

- Raw-anomaly count: p <= 0.05 (descriptive).
- Exploratory flag: BH q <= 0.10 within family.
- Promotion requires BOTH BH q <= 0.10 AND |z| >= 2.5.
- If nothing qualifies, the correct output is "no candidate hypothesis".
- No statistic is added, removed, or retailed because of anything
  observed in F-E002.

## 11. Prohibited in F-E003

Identical to F-E002: no predictive models, rankings, candidate pools,
tickets, holdout outcome analysis, incompatible pooling, or predictive
terminology.

## 12. Outputs

`data/analysis/phase3_corrected/` (versioned; F-E002 outputs under
`data/analysis/phase3/` are untouched) plus
`phase3_corrected_manifest.json` with full provenance.
`scripts/verify_phase3_corrected.py` enforces the firewall, ledger,
seal-versioning, and promotion gates.
