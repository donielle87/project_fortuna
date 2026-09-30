# PHASE 3 REPORT — EXPLORATORY HISTORICAL DEVIATION ANALYSIS (F-E002)

**Status:** COMPLETE. Exploratory analysis executed on the sealed
exploration subset; all anomalies adjudicated; zero candidate hypotheses
promoted; holdout UNTOUCHED.
**Headline:** every BH-flagged result is fully explained by verified
data-quality artifacts in the canonical store — not by the drawing
process. Two Phase 1 data defects were discovered and documented (D-006).
This is a successful scientific result.

## A. SCOPE / FIREWALL

The chronological holdout (last 20% per regime) was sealed BEFORE any
historical winning-number outcome was read: `metadata/phase3_holdout_*
seal.json` records the dataset hash, split-policy hash, manifest hashes,
and a SHA-256 over the raw canonical holdout row bytes. Phase 3 outcome
reads pass through `fortuna.analysis.loader`, which admits a row by
draw_id BEFORE parsing any winning-number field (trap-field tests).
No holdout outcome field was parsed, printed, or inspected.

## B. SPLIT

Per statistical regime (exploration / holdout, chronological):

| regime | total | expl | hold | expl end | hold start | expl segments |
|---|---|---|---|---|---|---|
| PB-S01 | 578 | 462 | 116 | 1996-09-21 | 1996-09-25 | 1 |
| PB-S02 | 514 | 411 | 103 | 2001-10-10 | 2001-10-13 | 1 |
| PB-S03 | 302 | 241 | 61 | 2005-01-26 | 2005-01-29 | 1 |
| PB-S04 | 350 | 280 | 70 | 2008-05-03 | 2008-05-07 | 1 |
| PB-S05 | 316 | 252 | 64 | 2011-06-04 | 2011-06-08 | 1 |
| PB-S06 | 389 | 311 | 78 | 2015-01-03 | 2015-01-07 | 1 |
| PB-S07 | 1414 | 1131 | 283 | 2024-12-07 | 2024-12-09 | 1 |
| MM-S01 | 171 | 136 | 35 | 1998-09-11 | 1998-09-15 | 5 |
| MM-S02 | 342 | 273 | 69 | 2001-09-07 | 2001-09-11 | 5 |
| MM-S03 | 320 | 256 | 64 | 2004-11-02 | 2004-11-05 | 4 |
| MM-S04 | 869 | 695 | 174 | 2012-02-17 | 2012-02-21 | 1 |
| MM-S05 | 426 | 340 | 86 | 2016-12-30 | 2017-01-03 | 1 |
| MM-S06 | 777 | 621 | 156 | 2023-10-06 | 2023-10-10 | 1 |
| MM-S07 | 155 | 124 | 31 | 2026-06-12 | 2026-06-16 | 1 |
| FL-S01 | 599 | 479 | 120 | 1997-07-05 | 1997-07-12 | 1 |
| FL-S02 | 2810 | 2248 | 562 | 2021-05-08 | 2021-05-12 | 1 |

8,260 exploration / 2,072 holdout draws. No holdout winning numbers are
shown anywhere in this report or its artifacts.

## C. PRIMARY FAMILY

202 regime-statistic tests (F-S001..S013 × applicability) against
exploration-matched fair nulls (20,000 replicates, 4×5,000 shared
HISTORIES streams, frozen tails). All 202 baselines CONVERGED under the
accepted v2 diagnostic.

## D. PRIMARY MULTIPLICITY

- raw p ≤ .05: 9 tests (expected ≈ 10 under the null)
- BH q ≤ .10 (exploratory flag): **1** — MM-S05 F-S006
  (consecutive-overlap aggregate; obs 155 vs null mean 112.96, z=4.22,
  p=5e-5, q=0.0101, Holm p=0.0101)
- Holm ≤ .05: 1 (same test)

## E. FREQUENCY DIAGNOSTICS

Number-level and special-ball residuals (`phase3_number_frequency_
diagnostics.csv`, `phase3_special_frequency_diagnostics.csv`) are
descriptive drill-downs only — sorted by ball number, never ranked for
play. Family-level controls F-S001/F-S002 and F-S009/F-S010 produced no
flags: no regime shows frequency dispersion beyond the null envelope.

## F. PAIR / TRIPLE STRUCTURE

Full pair matrices (`phase3_pair_counts.csv`, all C(N,2) pairs per
regime, lexicographic). F-S005 max-pair: no flags. P3-S001 max triple:
no flags; max-attaining triples recorded per regime in
`phase3_triple_diagnostics.csv`.

## G. SERIAL / RECENCY STRUCTURE

F-S006 flagged only at MM-S05 — see artifact adjudication below.
P3-S002 lag-1..5 scan flagged only at MM-S05 — same cause.
P3-S003 terminal drought: no flags; per-ball trailing runs recorded.

## H. ROLLING / TEMPORAL SCAN

P3-S004 rolling-window max |z| (windows 50/100/250, within-segment
only): no flags in any regime.

## I. STRUCTURAL DRAW DISTRIBUTIONS

P3-S005..S010 discrete-CvM discrepancies (draw sum, range,
adjacent-pair count, min/max spacing, odd count): no flags.

## J. PHYSICAL DRAW ORDER

P3-S011 ran on 13 regimes (MM-S01/S02: no physical-order records;
MM-S03: 94 < 100 minimum — INSUFFICIENT_DATA). Regimes with genuine
physical order (FL-S01, FL-S02, PB-S04..S07, verified ~uniform position
means ≈ N/2) show NO anomaly (|z| ≤ 1.6). Regimes flagged (MM-S04/05/06/
07, PB-S01/02/03) are explained by the order-semantics artifact below.

## K. MACHINE / BALL-SET ANALYSIS

P3-S012 evaluable only on FL-S02 (machine_id 6 categories, ball_set_id
6 categories on the populated post-2009 subset; all other regimes have
no populated equipment metadata — INSUFFICIENT_DATA). Calendar-year-
blocked permutation (10,000 perms): machine χ² z=1.00 (p=0.159);
ball-set χ² z=0.42 (p=0.329). No exploratory flag; no causal claim.

## L. SECONDARY MULTIPLICITY

- raw p ≤ .05: 15 of 175 applicable tests
- BH q ≤ .10: 8 flags — P3-S011 at MM-S04/05/06/07, PB-S01/02/03 and
  P3-S002 at MM-S05
- Holm ≤ .05: 6

## M. ARTIFACT ADJUDICATION (the decisive step)

Mechanically, 9 flags satisfied the frozen promotion rule
(BH q ≤ .10 AND |z| ≥ 2.5). Deterministic verification shows ALL are
explained by two Phase 1 data defects (`phase3_artifact_diagnostics.csv`,
D-006):

1. **Position-semantics mislabeling.** "physical_draw_order" populations
   that are literally ascending-sorted: 100% MM-S05/S06/S07, 99–100%
   MM-S03/S04, 100% PB-S01/S02, 59% PB-S03. A fair physical sequence is
   ascending with probability ~1/K! ≈ 0.8–2.7% — so a majority-sorted
   population is provably mislabeled. The flag magnitude (up to z=25) is
   exactly what sorted order produces. Genuine physical-order regimes
   (FL-S01/S02, PB-S04..S07) show no anomaly.
2. **Phantom duplicate records.** Nine consecutive draws in the
   canonical store repeat an identical main set on dates that are not
   draw days for the legal era (e.g. MM-D-2014-01-15 Wed duplicating
   2014-01-14 Tue; chance probability ~1/C(75,5) ≈ 6e-8 per pair):
   1 in MM-S03, 5 in MM-S05, 1 in MM-S06, 1 in PB-S06, 1 in PB-S07.
   Removing each phantom pair's overlap contribution (replaced by its
   expected value) drops MM-S05 F-S006 to z=1.88 and MM-S05 P3-S002
   to z=0.54 — below the effect threshold.

## N. CANDIDATE HYPOTHESES

**NONE.** All nine mechanically-promoted flags are artifact-explained;
promoting them would consume the sealed holdout to "confirm" known data
defects. `phase3_candidate_hypotheses.csv` is empty (headers only).
Correct statement: no exploratory anomaly survived adjudication against
the preregistered promotion criteria.

## O. EFFECT SIZES

Standardized null deviations are reported for all 202 primary and 175
secondary tests (`z` columns). The only extreme standardized deviations
(|z| up to 25.2) arise in the mislabeled-order populations — data-layer
effects, not lottery effects.

## P. DATA QUALITY / LIMITATIONS

- Two verified Phase 1 defects documented for research-lead disposition
  (D-006): `position_semantics` mislabeling for affected sources, and
  nine phantom records marked `analysis_eligible`. Canonical data is
  deliberately NOT modified; these findings may warrant a Phase 1
  corrective decision before Phase 4.
- Equipment metadata exists only for post-2009 FL Lotto; machine/ball-set
  analysis is structurally impossible elsewhere.
- Physical-order analysis is structurally impossible where sources
  provide only sorted numbers (all of MM-S01/S02).
- 15 missing/ineligible positions still break segments inside the
  exploration window; sequential statistics never bridge them.
- 12 eligible draws fall on non-scheduled weekdays (9 are the phantom
  records; 3 others are distinct-number special drawings — included).

## Q. SCIENTIFIC INTERPRETATION

Observed: frequency, pair, triple, drought, rolling, structural, and
equipment analyses show NO exploratory anomaly surviving adjudication.
What remains unexplained vs the fair-random null: nothing at the
preregistered thresholds. Possible explanations for the raw flags were
enumerated a priori (chance / multiple-testing / artifact / regime /
mechanical / temporal); direct verification resolved every flag as
artifact — the outcome exploration exists to distinguish.

## R. HOLDOUT STATUS

**UNTOUCHED.** Seal `6cb7c382924c…b91c` re-verified post-analysis
(identical SHA-256 over canonical holdout rows). 2,072 draws reserved
for Phase 4; post-cutoff draws remain additional prospective evidence.

## S. REPRODUCIBILITY

F-E002 config `config/experiments/F-E002.yaml`; seed 20260930,
PCG64DXSM, `sha256-scope-v1` children under experiment ID F-E002;
deterministic split/seal/manifests; `phase3_analysis_manifest.json`
records all hashes and provenance. `scripts/verify_phase3.py` enforces
upstream verifiers, seal integrity, split correctness, no holdout
leakage, frozen tails, family completeness, adjudication consistency,
and prohibited-product absence.

## T. TEST RESULTS

- pytest: 195 passed
- ruff check src scripts tests: clean
- verify_phase0/1/2/3: PASS

## U. GIT STATE

| field | value |
|---|---|
| phase3_preregistration_commit | `2657501db7e3d8ba5f7953ac3ba02d8082db16e7` |
| analysis code commits | `7c2e34c`, `be2ab08` |
| outputs/report commit | HEAD (see git log) |

## V. RECOMMENDATION

Phase 3 is complete: the exploratory sweep ran to specification, the
holdout remains sealed, and the only discoveries are two verified
data-quality defects — which are exactly the kind of finding a rigorous
exploration is for. Recommend the research lead adjudicate the Phase 1
defects (phantom records; position semantics) before authorizing
Phase 4. No predictive edge was found or claimed.

**PHASE 3 PASS**
