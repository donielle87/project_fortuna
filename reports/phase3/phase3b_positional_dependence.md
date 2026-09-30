# Phase 3B — Physical Draw-Sequence and Positional Dependence
# Exploration (F-E004)

**Classification:** exploratory. **Status:** complete, no anomaly
survives multiplicity correction; zero candidate hypotheses.
**Holdout:** UNTOUCHED (2,072 frozen IDs; seal re-verified).
Preregistration commit `36679847845a4e9dbef07eff75b0d2ab9e1758c4`
predates all outputs.

## A. SCIENTIFIC QUESTION

Does the actual physical extraction sequence of corrected exploration
draws contain dependence or position-specific structure beyond the fair
sequential without-replacement null? Phase 3 (F-E003) tested set-level
deviations; Phase 3B tests the ordered stream itself — but only where
physical-order provenance is verified (D-007 atomic rule).

## B. PHYSICAL-ORDER DATA AVAILABILITY

| Regime | Physical-order exploration draws | Segments | Status |
|--------|------|------|--------|
| FL-S01 | 477 | 3 (279/1/197) | RUN |
| FL-S02 | 546 | 5 (160/315/65/4/2) | RUN |
| MM-S01 | 0 | 0 | INSUFFICIENT_DATA |
| MM-S02 | 0 | 0 | INSUFFICIENT_DATA |
| MM-S03 | 94 | 3 | INSUFFICIENT_DATA |
| MM-S04 | 688 | 6 | RUN |
| MM-S05 | 328 | 12 | RUN |
| MM-S06 | 613 | 9 | RUN |
| MM-S07 | 122 | 3 | RUN |
| PB-S01 | 0 | 0 | INSUFFICIENT_DATA |
| PB-S02 | 0 | 0 | INSUFFICIENT_DATA |
| PB-S03 | 99 | 1 | INSUFFICIENT_DATA |
| PB-S04 | 277 | 4 | RUN |
| PB-S05 | 249 | 4 | RUN |
| PB-S06 | 308 | 4 | RUN |
| PB-S07 | 1123 | 9 | RUN |

10 qualifying regimes (n ≥ 100), 4,827 physical-order exploration
draws. Segments break on any missing/ineligible/excluded or
non-physical-order timeline position; serial statistics never bridge.

## C. FAIR SEQUENTIAL NULL

Null replicates are uniform ordered K-permutations
(`draw_mains_ordered`) — the sequential mechanism X1~U(N),
X2~U(N-1|X1), ... — so every calibrated null already contains the
within-draw no-replacement dependence. 20,000 replicates per regime in
4 deterministic batches of 5,000, PCG64DXSM, root seed 20260930, shared
`P3B_HISTORIES` streams across all statistics. All 88 inferential
baselines CONVERGED under the v2 diagnostic.

## D. P3B-S001 — POSITION x BALL OMNIBUS

Pearson dispersion of the K x N count matrix vs n/N expected. No flag.
Largest z: FL-S02 z = 1.48 (raw p = 0.073).

## E. P3B-S002 — MAX POSITION-SPECIFIC BALL DEVIATION

Max |z| over position x ball cells, binomial-standardized at p = 1/N.
No flag in any regime (max z ≈ 1.9 across regimes — well within the
MC-calibrated max-null range).

## F. P3B-S003 — POSITIONAL DISTRIBUTION SHAPE

Max over positions of the discrete CvM discrepancy vs uniform. No flag;
closest MM-S06 raw p = 0.052 (not significant after BH q = 0.998).

## G. P3B-S004 — ADJACENT POSITION CONDITIONAL DEPENDENCE

Omnibus adjacent-transition discrepancy against the fair
without-replacement transition expectation n/(N(N-1)). No flag in any
regime — the observed within-draw dependence is indistinguishable from
pure no-replacement dependence.

## H. P3B-S005 — ORDERED POSITION-PAIR EXTREME

Max |standardized residual| over all ordered (j,k), (a,b) cells.
No flag (raw p range 0.37–1.0 across regimes).

## I. P3B-S006 — WITHIN-DRAW CONDITIONAL INFORMATION EXCESS

Max adjacent-pair empirical MI (bits), calibrated against the null's
own sparse-contingency MI distribution — the null's MI is nonzero both
from no-replacement dependence and finite-sample bias (~1–2 bits at
these n/N). FL-S01 raw p = 0.043 (z = 1.79) is the single raw-p <= .05
result in the primary family — below the multiplicity floor (BH q =
0.998) and the |z| >= 2.5 promotion gate; NOT flagged.

## J. P3B-S007 — SAME-POSITION SERIAL DEPENDENCE

Lags 1–5, within physical-order segments only (pairs never bridge
missing/ineligible/sorted rows). No flag; closest FL-S01 raw p = 0.081.

## K. P3B-S008 — CROSS-POSITION SERIAL DEPENDENCE

All ordered (source j, dest k) pairs, lags 1–3, within segments.
No flag in any regime.

## L. P3B-S009 — TIME-VARYING POSITIONAL DEVIATION

Rolling windows 100/250 physical-order draws within segments. RUN in 8
regimes (MM-S05 and MM-S07 have no physical segment >= 100 — correctly
INSUFFICIENT, not tested). No flag.

## M. P3B-S010 — EQUIPMENT x POSITION

INSUFFICIENT_DATA in all 20 regime x field evaluations — no regime
meets >=3 categories / >=20 per category / >=200 physical-order draws
with populated equipment metadata. Not tested; not forced.

## N. MULTIPLICITY RESULTS

**Primary family** (P3B-S001/2/3/4/6/7/8 across 10 regimes):
- 70 tests, raw p <= .05: **1** (≈3.5 expected under the null)
- BH flags at q <= 0.10: **0**; Holm flags at alpha = 0.05: **0**
- min BH q = 0.998

**Secondary family** (S005 all regimes, S009 where windows fit, S010
where sufficient):
- 18 tests, raw p <= .05: **0**
- BH flags: **0**; Holm flags: **0**

## O. SENSITIVITY / POWER

`phase3b_sensitivity.csv`: 272 rows, 250 biased replicates per
(regime, scenario, effect) cell, critical value = null 95th percentile.
Approximate 80%-power detection thresholds:

- Position-1 per-ball probability shift delta ~ **1–4x** baseline
  (regime-dependent; PB-S07 most sensitive, delta = 1)
- Within-draw conditional override X2 = succ(X1) with q ~ **0.15–0.6**
- Same-position serial copy prob q ~ **0.05–0.10** (very sensitive)
- Cross-position serial copy prob q ~ **0.05–0.10**
- Localized position-1 bias in a <=250-draw window: delta ~ **2–4**

Interpretation: the data could have detected moderate-to-strong
positional defects; sub-percent per-position shifts and very weak
conditional dependence remain below detectability at current n.

## P. CANDIDATE HYPOTHESES

**NONE.** `phase3b_candidate_hypotheses.csv` is empty — no test met the
frozen promotion rule (BH q <= 0.10 AND |z| >= 2.5 AND converged).

## Q. HOLDOUT STATUS

**UNTOUCHED.** The loader admits rows by draw_id before parsing any
outcome field; no holdout draw_id appears in any Phase 3B output; v1
and v2 seals re-verified unchanged.

## R. SCIENTIFIC INTERPRETATION

No detectable positional structure beyond fair sequential sampling —
in marginals, position-specific frequencies, adjacent-pair transitions,
information excess, or serial position dependence. This is "no signal
detected", not "proof of randomness": the sensitivity study bounds what
could have been seen. Physical-order coverage is itself thin for
MM-S01..S03 and PB-S01..S03 (sorted/backfilled source data, per D-007).

## S. STOPPING RULE STATUS

No test satisfied the promotion rule. Per the frozen rule:
**positional-mechanics exploration STOPS.** No new positional
statistics may be added post hoc. The holdout remains sealed.

## T. TESTS / REPRODUCIBILITY

- `verify_phase3b.py`: 58 checks PASS (upstream verifiers re-run green)
- 22 Phase 3B unit/synthetic-power tests; synthetic scenarios A–E all
  detected at expected strengths
- `phase3b_manifest.json` pins dataset/plan/manifest seals, regime
  counts, segments, RNG, thresholds, all output hashes
- Determinism: identical reruns produce byte-identical statistic arrays

## U. GIT STATE

Machinery commit `a2ad462`; preregistration `3667984`; outputs +
verifier + this report committed on `main`.

## V. RECOMMENDATION

Positional exploration is complete and negative within detection
limits. The project may proceed to one finite predictive-model study if
the research lead authorizes it; the sealed holdout is reserved for
that decision, not for exploratory fishing.

PHASE 3B PASS
