# F-E004 Preregistration — Physical Draw-Sequence and Positional
# Dependence Exploration

**Classification:** exploratory
**Status:** FROZEN before any positional outcome statistic is computed
**Experiment ID:** F-E004 (Phase 3B)
**Commit:** this commit is `phase3b_preregistration_commit`

## 1. Scientific question

Does the actual physical extraction sequence of corrected exploration
draws contain dependence or position-specific structure beyond what is
expected under a fair sequential without-replacement draw?

A fair K-of-N physical draw is one sequential stochastic mechanism:
X1 uniform over N balls; X2 uniform over the N-1 remaining; etc.
Every physical position has a uniform marginal ball distribution, and
positions are dependent within a draw because replacement is forbidden.
The null must preserve that dependence. **No statistic in this
experiment is compared against an independent-position null.**

F-E003 found no surviving deviation in set-level statistics; F-E004 is
the narrower positional-mechanics question on physical-order records.
It is exploratory, generates candidate hypotheses only, and does not
touch the frozen holdout.

## 2. Inputs (pinned)

- Phase 1 dataset SHA-256 (corrected):
  `200174427b4abcc6bcc0aa3761174db237ae52e266e88cfc88bae39f27c138ff`
- Phase 2 v4 observation-plan SHA-256:
  `8309e1dd673e339b66b1fae09d02a0f2b205a62ada2882c1590645d1bf2ac10a`
- Exploration population: `metadata/phase3_exploration_ids_v2.csv`
  (original F-E002 exploration IDs intersect corrected eligible draws;
  8,248 draws)
- Frozen holdout: `metadata/phase3_holdout_ids.csv` (2,072 IDs,
  unchanged) under v2 seal
  `6dc9a023b4bfd7b7fcfa321ebde9455687222eb0ef316a458d0d01effe18f2e0`;
  v1 seal preserved as the immutable historical record.

## 3. Physical-order eligibility (frozen)

A draw enters Phase 3B only if ALL hold:

- `analysis_eligible == true`, `draw_stream == main`
- `draw_id` in the corrected Phase 3 exploration set
- `numbers_order == physical_draw_order`
- `number_sequence_source_id` is populated (atomic provenance; the
  stored sequence, its semantics, and the source are one unit per D-007)
- the source is order-capable under the corrected order-provenance policy
- the stored sequence is non-ascending-verified physical order

`source_sorted_order` and `unknown_order` rows are never used and never
substituted. No holdout draw may enter. Minimum regime sample size for
inferential analysis: **100** physical-order exploration draws; regimes
below are INSUFFICIENT_DATA and appear only in sufficiency tables.

## 4. Contiguous physical-order segments (frozen)

A physical-order segment breaks on: missing scheduled draw, ineligible
or excluded draw, a row lacking verified physical order (sorted or
unknown), regime change, or the exploration boundary. Serial and
rolling statistics never bridge a break. This is stricter than the
ordinary sequence segmentation.

## 5. Fair sequential null (frozen)

Replicates are uniform ordered K-permutations produced by the existing
fair engine (`draw_mains_ordered`), which is mathematically the
sequential without-replacement mechanism. Monte Carlo per qualifying
regime: 20,000 replicate ordered histories in 4 deterministic batches
of 5,000, PCG64DXSM, root seed 20260930, shared
`<game>|<regime>|P3B_HISTORIES|batch<b>` streams across all P3B
statistics within a regime. Cross-draw statistics use the observed
physical-order segment structure. Convergence: the accepted v2
diagnostic; NOT CONVERGED is reported honestly and blocks promotion.

## 6. Frozen statistic catalog (P3B-S001..S010)

All tails: upper.

| ID | Statistic | Family |
|----|-----------|--------|
| P3B-S001 | Pearson dispersion over the K x N position x ball count matrix (cells expected n/N) | primary |
| P3B-S002 | max |z| over position x ball cells, z binomial-standardized at p=1/N | primary |
| P3B-S003 | max over positions of discrete CvM discrepancy of the position's label distribution vs uniform | primary |
| P3B-S004 | omnibus adjacent-position (j,j+1) ordered-transition Pearson discrepancy vs fair WOR expectation n/(N(N-1)) | primary |
| P3B-S006 | max over adjacent pairs of empirical mutual information (bits, empirical marginals); calibrated against the null's own MI | primary |
| P3B-S007 | max |z| same-position serial equality hits, lags 1-5, within segments only | primary |
| P3B-S008 | max |z| cross-position (j,k) serial equality hits, lags 1-3, within segments only | primary |
| P3B-S005 | max |standardized ordered-pair residual| over all ordered (j,k) j!=k and (a,b) a!=b | secondary |
| P3B-S009 | max |z| rolling positional-frequency scan, windows 100/250 physical-order draws, within segments | secondary |
| P3B-S010 | equipment x position x ball Pearson chi2, machine_id/ball_set_id, sufficiency >=3 categories / >=20 per cat / >=200 total, calendar-year blocked permutation (10,000) | secondary |

Primary family = P3B-S001, S002, S003, S004, S006, S007, S008 across
all qualifying regimes. Secondary family = P3B-S005, S009, S010 across
all applicable regimes. No statistic may be added after outcomes are
read.

## 7. Multiplicity (frozen)

MC p-values: (b+1)/(B+1), upper tail. Per family: BH at q <= 0.10
(flag), Holm at alpha = 0.05 (reported). F-E004 is its own
preregistered experiment; its p-values are never pooled with F-E003's.

## 8. Promotion rule (frozen)

Candidate hypothesis requires BOTH: BH q <= 0.10 AND |z| >= 2.5 (z =
(obs - null_mean)/null_sd). A NOT CONVERGED statistic cannot be
promoted. Any maximizing identity (position, ball, pair, lag, window,
equipment category) selected by a MAX statistic is a DATA-DERIVED
IDENTITY requiring independent confirmation — never called predictive.

## 9. Sensitivity study (frozen)

Per qualifying regime, biased synthetic histories (root seed 20260930,
dedicated P3B_SENS streams; 250 replicates per cell; critical value =
null 95th percentile):

- `position1_bias` delta in {0.5,1,2,4}: position-1 boosted subset
  (floor(N/10) lowest labels), valid WOR draws
- `conditional_bias` q in {0.05,0.15,0.3,0.6}: X2 = succ(X1) w.p. q,
  marginals ~uniform
- `serial_same_pos` q in {0.05,0.1,0.2,0.4}: X1,t+1 = X1,t w.p. q
- `serial_cross_pos` q in {0.05,0.1,0.2,0.4}: X1,t+1 = XK,t w.p. q
- `temporal_position` delta in {1,2,4,8}: position-1 bias inside one
  <=250-draw window of the longest segment

Output: `phase3b_sensitivity.csv` with power estimates per
regime/scenario/effect and the ~80%-power detection threshold.

## 10. Stopping rule (frozen)

If no test satisfies the promotion rule after correction and honest
convergence handling: positional-mechanics exploration STOPS. No new
positional statistics may be added after viewing results. If any test
promotes, candidate F-H### hypotheses are registered
(candidate_for_confirmation only). The holdout stays sealed either way;
the research lead decides whether evidence earns a confirmatory test.

## 11. Prohibited

Predictive models, number rankings, candidate pools, tickets, holdout
outcome analysis, independent-position nulls, sorted/unknown-order
substitution, pooling incompatible regimes.
