# PHASE 2 REPORT — FAIR-RANDOM NULL MODEL AND MONTE CARLO BASELINE (F-E001)

**Status:** COMPLETE. Reference baselines generated, validated, converged.
**Scope discipline:** zero historical winning-number outcomes were read or
analyzed; the only historical input was the metadata-only observation plan
(counts, eligibility, segment structure).

## A. Null model

Within each statistical regime (matrix-identical pooling group), every
valid main-ball combination is equally likely: K balls sampled uniformly
without replacement from the regime's main pool. Special-ball games draw
one independent uniform special ball from their own pool. Draws are
independent through time. Regimes are never pooled; legal eras sharing a
statistical pool share one null. Equipment/machine/ball-set/venue/temporal
alternatives are out of scope.

## B. Preregistration

- Experiment `F-E001`, registered 2026-09-30 in `registry/experiment_registry.csv`
- Preregistration: `research/preregistrations/F-E001-phase2-fair-null-baseline.md`
- Frozen config: `config/experiments/F-E001.yaml`
- `phase2_preregistration_commit` = `2b4381a5945313ef99f00c8f8df2faeec933fce9`,
  committed before any simulation ran
- Amendment (D-003): convergence SE formula corrected post-run via
  `F-E001-amendment-01-convergence-se.md` + `config/experiments/F-E001.v2.yaml`.
  Diagnostic-only change; generated draws and statistic values unchanged
  (determinism probes re-verified identical draws).

## C. Accepted input

- Phase 1 dataset SHA-256:
  `953c0701aeef6782a361146999ca43c1d4d2863d807c8e4dbe39cfa4108f3891`
- Observation plan: `metadata/phase2_observation_plan.csv`
  (sha256 `67a24385237c0184fe252e94808141c29325b2b6fb086f0a57976242e8e6ddd6`)
- Eligible main draws by regime (sequential splits in parentheses):
  PB-S01 578; PB-S02 514; PB-S03 302; PB-S04 350; PB-S05 316; PB-S06 389;
  PB-S07 1414; MM-S01 171 (5 segments); MM-S02 342 (7); MM-S03 320 (6);
  MM-S04 869; MM-S05 426; MM-S06 777; MM-S07 155; FL-S01 599; FL-S02 2810.
- Total eligible main draws: 10,332 in 31 contiguous segments.

## D. Exact baselines

`data/reference/null_baselines/exact_baselines.csv` — for every regime:
sample space C(N,K)[×M], jackpot probability (matches registry jackpot
odds — PB-S07: 1/292,201,338; MM-S07: 1/290,472,336; FL-S02: 1/22,957,480),
inclusion K/N, pair C(K,2)/C(N,2), triple C(K,3)/C(N,3), full overlap pmf
C(K,j)C(N−K,K−j)/C(N,K), odd/even hypergeometric pmf, special repeat 1/M,
ticket-match pmf, and the negative within-draw inclusion covariance
K(K−1)/(N(N−1)) − (K/N)². `structural_distributions.csv` adds exact pmfs
for draw sum, range, odd count, overlap, and no-consecutive probability,
plus clearly-labeled simulated pmfs for spacing-type statistics.

## E. Monte Carlo engine

- RNG: `numpy.random.Generator(PCG64DXSM)`; NumPy 2.1.3
- Root seed 20260930; child streams `SeedSequence([root, H])`,
  `H = SHA-256("F-E001|<scope>")[:16]` big-endian (`sha256-scope-v1`)
- History scope: `<game>|<statistical_regime>|HISTORIES|batch<1..4>`;
  dedicated `VALIDATION` and `STRUCTURAL` streams
- 4 batches × 5,000 replicate histories = 20,000 replicates per
  (regime × applicable statistic); streaming accumulation, no raw draws
  persisted (determinism probes hash the first 100 draws per regime)

## F. History-level reference distributions

`history_baseline_summary.csv` / `history_baseline_quantiles.csv` —
202 (regime, statistic) baselines: F-S001..S008, S012, S013 for all 16
regimes; F-S009..S011 for the 14 special-ball regimes (n/a for FL Lotto).
Sequential statistics respect segment boundaries. Spot checks against
theory: PB-S07 overlap aggregate 512.09 (exact 511.96); special repeats
54.41 (exact 54.35); draw-sum variance 1866.5 (exact 1866.7); F-S001
chi-square mean 63.98 (exact E = N(1−p) = 64.0).

## G. Convergence

All 202 simulated baselines: **CONVERGED** (1,010/1,010 metric checks
pass under the v2 criterion). v1 produced 94 spurious NOT CONVERGED
flags from a ~2.3σ-effective formula and was corrected via D-003 — the
correction is documented, not silent. Failed convergence remains a valid
reported outcome; none occurred.

## H. Theory-to-simulation validation

`theory_validation.csv` — 108 checks across all 16 regimes, all PASS at
the frozen 5σ tolerance: worst-cell inclusion, pair and triple
probabilities (deterministic 512-cell subsets), overlap pmf worst cell,
odd/even worst cell, special frequency, special repeat rate.

## I. Observation segments

Segments are runs of eligible positions along the full timeline
(expected ∪ actual draw positions). Every excluded position — the missing
MM date 1998-02-03, nine Tier-3-only draws, five unresolved-conflict
draws — breaks a segment. MM-S01..S03 carry all 15 breaks; every other
regime is a single segment. Sequential statistics never bridge them.

## J. Double Play / order semantics

Plan and baselines use `draw_stream == main` only; Double Play is fully
excluded (verified against the canonical store). All catalog statistics
are order-insensitive. The plan additionally records
`order_eligible_segment_lengths` (physical-draw-order positions only) for
future order analyses — MM-S01/S02 have none (source-sorted only), so any
future order test there is structurally impossible.

## K. Multiplicity utilities

`fortuna/statistics/pvalues.py` — finite-simulation-corrected MC p-value
(b+1)/(B+1), upper/lower/two-sided. `multiple_testing.py` —
Benjamini–Hochberg and Holm, tested on known examples. Neither is applied
to historical data.

## L. Reproducibility

Outputs: `exact_baselines.csv`, `structural_distributions.csv`,
`history_baseline_summary.csv`, `history_baseline_quantiles.csv`,
`batch_convergence.csv`, `theory_validation.csv`,
`phase2_simulation_manifest.json` under `data/reference/null_baselines/`.
The manifest records experiment id, preregistration commit, code commit,
dataset/plan/config/prereg hashes, RNG + root seed + child derivation,
replicate/batch structure, per-regime determinism probes, per-output
hashes, timestamp, validation/convergence status. `verify_phase2.py`
regenerates all 16 probes and verifies every hash.

## M. Test results

- `pytest`: 162 passed
- `ruff check src scripts tests`: clean
- `verify_phase0.py`: PASS; `verify_phase1.py`: PASS; `verify_phase2.py`: PASS

## N. Git state

| field | value |
|---|---|
| phase2_preregistration_commit | `2b4381a5945313ef99f00c8f8df2faeec933fce9` |
| simulation code commit | `e43fbd8397d7f7a067dc2b0640ce07f9fc47192e` |
| outputs/report commit | (recorded at final commit) |

## O. Recommendation

The fair-random null is fully specified, exact where tractable, simulated
where not, calibrated against theory, converged, deterministic, and
isolated from historical outcomes. Phase 2 is ready for acceptance.
