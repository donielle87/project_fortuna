# Preregistration F-E002 — Phase 3 Historical Deviation Exploration

- **Experiment ID:** F-E002
- **Classification:** EXPLORATORY — hypothesis generation only. This is
  explicitly NOT confirmatory, NOT predictive, and NOT a validated edge.
- **Registered:** 2026-09-30, before any historical winning-number outcome
  has been read by Phase 3 code.
- **Frozen configuration:** `config/experiments/F-E002.yaml`
- **Status:** Immutable once committed. Later defects require a
  `registry/decision_log.csv` entry and superseding documents — never
  silent edits.

## 1. Scientific objective

Compare a predeclared exploration subset of historical draws against the
accepted Phase 2 fair-random null; identify anomalies worth further
investigation; generate rigorously defined candidate hypotheses for later
confirmation; preserve an untouched chronological holdout for Phase 4.

Exploratory findings are NOT predictive evidence. A small p-value in this
experiment does not decide whether an observation is chance, artifact, or
signal.

## 2. Accepted inputs (frozen)

- Phase 1 dataset SHA-256:
  `953c0701aeef6782a361146999ca43c1d4d2863d807c8e4dbe39cfa4108f3891`
- Phase 2 final commit `0497462993759e7bcbe236f47f7df5d7c27baa8d`
- Phase 2 observation-plan SHA-256:
  `67a24385237c0184fe252e94808141c29325b2b6fb086f0a57976242e8e6ddd6`
- Eligibility: `analysis_eligible == true AND draw_stream == main`.

## 3. Chronological holdout (locked metadata-only)

- Split independently inside each of the 16 statistical regimes.
- `holdout_count = ceil(0.20 * n_eligible)`; the LAST `holdout_count`
  chronological eligible draws form the holdout; the earlier 80% form the
  exploration set.
- The split is never randomized, never outcome-optimized, and is built
  from metadata columns only (draw_id, game, regime, date, stream,
  eligibility, order semantics).
- A SHA-256 seal is computed over the ordered canonical holdout rows'
  raw bytes. Phase 3 code never parses holdout outcome fields; the only
  permitted holdout operations are metadata assignment, counting, date
  boundaries, draw IDs, and cryptographic hashing.
- Holdout manifests expose no winning numbers.

## 4. Exploration-only outcome access (structural firewall)

Phase 3 outcome reads are routed through an exploration-only loader that
admits a draw row by `draw_id` BEFORE parsing any winning-number field.
A holdout row is skipped prior to outcome parsing; trap data in holdout
outcome fields cannot be triggered. If a holdout draw_id were ever
included in the exploration set, the loader's outcome parser fails on
the trap and the test suite fails.

## 5. Exploration segments

Sequential statistics use exploration segments built under the Phase 2
rule: a segment breaks at a missing scheduled draw, an analysis-ineligible
draw, an unresolved-conflict draw, a Tier-3-only draw, a quarantined draw,
and — additionally — at the exploration/holdout boundary. No sequential
statistic bridges any of these positions.

## 6. Primary test family (frozen)

The F-S001..F-S013 catalog (unchanged definitions from F-E001 v3),
evaluated on the exploration subset only — 202 applicable
regime-statistic tests. Frozen tails: F-S001/S002/S003/S005/S007/S008/
S009/S010 upper; F-S004 lower; F-S006/S011/S012/S013 two-sided. Monte
Carlo p-values use the finite-simulation correction p = (b+1)/(B+1).
The 202 tests form ONE primary multiplicity family: BH q = 0.10
exploratory flag; Holm-adjusted values reported at alpha = 0.05.

## 7. Exploration-matched null

20,000 replicate fair histories per statistical regime (4 deterministic
batches x 5,000) matched exactly to exploration draw count, exploration
segment lengths, and regime matrix. RNG: PCG64DXSM, root seed 20260930,
`sha256-scope-v1` child streams under experiment ID F-E002. Shared
history scope `<game>|<stat_regime>|HISTORIES|batch<1..4>` is deliberate
and frozen from the start for F-E002 (each statistic still receives
20,000 iid replicates; joint null dependence preserved). The accepted
F-E001 v2 convergence diagnostic runs unchanged; a failed baseline is
reported NOT CONVERGED, never relabeled.

## 8. Secondary test family (frozen definitions)

P3-S001 max main-ball triple co-occurrence (upper).
P3-S002 max |z| of lagged-overlap aggregates over lags 1..5; z_L uses the
exact overlap mean/variance; pairs never cross segment boundaries (upper).
P3-S003 max terminal main-ball drought at the end of the final
exploration segment (upper) — a recency diagnostic only; a long absence
does NOT imply a number is "due".
P3-S004 max |standardized rolling-window frequency deviation| over
windows {50, 100, 250} x within-segment positions x labels; a window is
used only when it fits inside a contiguous segment (upper).
P3-S005..S010 discrete Cramer-von Mises discrepancy
`T = sum_x p0(x) (F_emp(x) - F0(x))^2` of per-draw {draw sum, range,
adjacent-pair count, min spacing, max spacing, odd count} against
exact/simulated reference pmfs (upper each). The CvM weighting choice is
frozen here; no post-hoc selection among discrepancy measures.
P3-S011 physical-position frequency omnibus `max_{j,l} |z_{j,l}|` on
`numbers_order == physical_draw_order` records only (upper); N/A below
100 ordered exploration draws; sorted/unknown order never substituted.
P3-S012 equipment (machine_id, ball_set_id separately) chi-square
association with main-ball outcomes, calibrated by calendar-year-blocked
label permutation (10,000 permutations); N/A when the populated subset
has <3 categories with >=20 draws or <200 draws total. Confounding with
time is acknowledged; no causal claim is made.

All P3-S statistics take values under the SAME fair replicate histories
(same HISTORIES streams) where they are history-level; P3-S011 uses a
dedicated ORDER stream; P3-S012 uses deterministic EQUIP permutation
streams. All applicable P3-S tests form ONE secondary multiplicity
family (BH q <= 0.10 exploratory flag; Holm reported at 0.05).

## 9. Anomaly flags and hypothesis promotion

- Raw-anomaly count: p <= 0.05 (descriptive only).
- Exploratory flag: BH q <= 0.10 within the relevant family.
- Candidate-hypothesis promotion requires BOTH BH q <= 0.10 AND
  |observed - null_mean| / null_sd >= 2.5 (null_sd > 0). For bounded or
  discrete statistics the same standardized-null-deviation z is the
  predeclared effect-size criterion; no alternate threshold may be
  substituted after outcomes are seen.
- If nothing satisfies promotion, the correct output is "no candidate
  hypothesis" — never manufactured findings.
- Data-derived identities (specific ball, pair, triple, window, position,
  equipment category) may be named only as candidate hypotheses evaluable
  on untouched holdout/prospective data; a global anomaly does not
  license a per-identity inferential claim.

## 10. Prohibited in Phase 3

Predictive models of any kind; future-number ranking; candidate pools;
ticket generation; holdout outcome analysis of any kind (frequencies,
pairs, triples, sums, ranges, spacings, odd/even, droughts, streaks,
overlaps, rolling statistics, equipment association, position
statistics, p-values, plots, or summaries of winning numbers); pooling
incompatible statistical regimes; hot/cold/due/lucky/best/worst labels;
any terminology implying prediction.

## 11. Outputs

`data/analysis/phase3/` products enumerated in the task order plus
`phase3_analysis_manifest.json` (full provenance incl. preregistration
commit, seals, hashes). `reports/phase3/phase3_exploratory_analysis.md`.
`scripts/verify_phase3.py` enforces the firewall and provenance gates.
