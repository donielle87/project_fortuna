# Preregistration F-E001 — Phase 2 Fair-Random Null Model & Monte Carlo Baseline

- **Experiment ID:** F-E001
- **Registered:** 2026-09-30, before any Phase 2 simulation output exists
- **Frozen configuration:** `config/experiments/F-E001.yaml` (sha recorded in
  the simulation manifest)
- **Status:** This document is immutable once committed. Defects found later
  require a `registry/decision_log.csv` entry and a superseding
  preregistration — never silent edits.

## 1. Scientific objective

Establish what historical lottery-draw data should look like under the
fair-random null — before any comparison to observed outcomes. Produce
exact combinatorial baselines and Monte Carlo reference distributions for
the preregistered history-level statistic catalog F-S001..F-S013, per
statistical regime. This phase manufactures the reference; it does not
measure departures.

## 2. Null assumptions (frozen)

1. Every valid main-ball combination is equally likely within its
   statistical regime.
2. Main balls are sampled uniformly WITHOUT replacement.
3. A special ball, where the game mechanism has one, is uniform over its
   own pool.
4. Main-ball and special-ball selections are independent (separate pools).
5. Draws are independent through time.
6. Regimes with different matrices are never pooled.
7. Legal/schedule eras sharing one statistical pool share one null model.
8. Equipment/machine/ball-set/venue/temporal alternatives are out of scope.

## 3. Scope

- **Games:** powerball, mega_millions (incl. The Big Game), florida_lotto.
- **Statistical regimes (16):** PB-S01..PB-S07, MM-S01..MM-S07,
  FL-S01, FL-S02. Matrices loaded from `metadata/game_regimes.csv`
  (verified Phase 0 inventory) — never hard-coded.
- **Draw stream:** `main` only. Double Play is never mixed into main
  baselines; any DP validation runs live under a separate namespace.

## 4. Frozen input

- **Accepted Phase 1 dataset SHA-256:**
  `953c0701aeef6782a361146999ca43c1d4d2863d807c8e4dbe39cfa4108f3891`
- **Eligibility rule:** `analysis_eligible == true AND draw_stream == main`.
- **Observation plan:** `metadata/phase2_observation_plan.csv` — built from
  draw metadata only (game, date, regime, eligibility, stream, order
  semantics). Winning-number values are never read.
- **Sequential continuity:** replicate histories replicate the frozen
  contiguous-eligible-segment lengths. Missing, Tier-3-only,
  unresolved-conflict, and quarantined positions break segments; sequential
  statistics never bridge them.

## 5. RNG / seeding

- **Generator:** `numpy.random.Generator` wrapping `PCG64DXSM`.
- **Root seed:** `20260930` (fixed, transparent).
- **Child streams:** `SeedSequence([root_seed, H])` where
  `H = int.from_bytes(SHA-256("F-E001|<game>|<stat_regime>|<scope>")[:16])`.
  Scope = statistic/batch/validation identifier as applicable. Execution
  order and batch order cannot change the stream assigned to a unit of work.
- No Python `random`, no `np.random.seed`, no wall-clock seeding.
- NumPy version recorded in the simulation manifest.

## 6. Monte Carlo design

- **Replicates:** 20,000 fair histories per (statistic × statistical regime)
  where the statistic is simulated.
- **Batching:** 4 independent deterministic child batches × 5,000.
- **Streaming:** per-replicate statistics accumulated to histograms,
  moments, and quantiles; raw draw matrices are not persisted.
- Sample sizes inside each replicate equal the frozen eligible draw count
  (aggregate statistics) or the contiguous segment lengths (sequential
  statistics).

## 7. Exact distributions implemented (non-simulated)

- Jackpot sample space: C(N,K), and C(N,K)·M with a special ball.
- Single-ball inclusion: K/N; counts ~ Binomial(n, K/N).
- Fixed pair: C(N−2,K−2)/C(N,K); fixed triple: C(N−3,K−3)/C(N,K).
- Consecutive-draw overlap: hypergeometric C(K,j)·C(N−K,K−j)/C(N,K).
- Special-ball repeat: 1/M.
- Odd/even composition: exact hypergeometric over the regime's odd pool.
- Candidate-pool coverage: X ~ Hypergeometric(N,K,m), exact tail
  (baseline utility only — no pools are chosen or ranked).
- Random-ticket match distribution: exact, main pool and joint with the
  special ball.
- Within-draw inclusion covariance: Cov(I_i,I_j) = K(K−1)/(N(N−1)) − (K/N)²
  (negative dependence; independence between main-ball labels is wrong).
- Exact DP/enumeration for single-draw structural statistics where
  practical (sum, odd-count); spacing/range statistics may be computed by
  simulation and are then clearly labeled `simulated`.

## 8. Statistic catalog F-S001..F-S013 (frozen definitions)

Per statistical regime; `c_i` = count of main number i in the replicate
history; `p = K/N`; `n` = eligible draw count.

| ID | Statistic | Definition |
|---|---|---|
| F-S001 | main-frequency dispersion | chi-square Σ(c_i − np)²/(np) |
| F-S002 | max |z_i| | max_i |c_i − np| / √(np(1−p)) |
| F-S003 | max occurrence count | max_i c_i |
| F-S004 | min occurrence count | min_i c_i |
| F-S005 | max pair co-occurrence | max over all C(N,2) pairs of co-count |
| F-S006 | consecutive-draw overlap aggregate | Σ_t |D_t ∩ D_{t+1}| within segments |
| F-S007 | max drought | longest run of draws where a main number is absent; max over numbers, within segments |
| F-S008 | max appearance streak | longest run where a main number appears; max over numbers, within segments |
| F-S009 | special-ball dispersion | chi-square over M special balls (n/a for FL Lotto) |
| F-S010 | max special-ball |z| | (n/a for FL Lotto) |
| F-S011 | special-ball repeats | count of adjacent equal special balls within segments |
| F-S012 | draw-sum dispersion | sample variance of per-draw main sums |
| F-S013 | odd/even dispersion | sample variance of per-draw odd count |

No statistics may be added to F-E001 after simulation begins; later
statistics require a new experiment registration.

## 9. Convergence criteria (frozen)

For every simulated (regime, statistic): compute mean, variance, q90, q95,
q99 per 5,000-replicate batch and pooled over 20,000. CONVERGED iff for all
five metrics:

  max_b |m_b − m_pool| ≤ max(4·SE_pool(m), 1e-6·max(1,|m_pool|))

with `SE_pool` from the pooled distribution (mean: σ/√B; variance:
√((μ4−σ⁴)/B); quantile p: √(p(1−p))/(f̂(q_p)·√B), f̂ via spacing
estimate). Failure → `NOT CONVERGED`, never renamed PASS. A follow-on
preregistered run may be proposed if needed.

## 10. Theory-to-simulation validation

Per regime, 200,000 independent fair draws under child scope `VALIDATION`
are checked against exact theory: inclusion probability, pair/triple
probability, overlap distribution, odd/even distribution, special-ball
frequency and repeat rate. Tolerance: |sim − exact| ≤ 5·SE (binomial/normal
SE). No historical draws are used in these checks.

## 11. Outputs

Under `data/reference/null_baselines/`:

- `exact_baselines.csv`
- `history_baseline_summary.csv`
- `history_baseline_quantiles.csv`
- `batch_convergence.csv`
- `phase2_simulation_manifest.json` (phase, experiment_id,
  preregistration commit, simulation code commit, dataset sha256,
  root seed, RNG, NumPy version, replicate/batch structure, catalog
  version, regimes, observation-plan hash, config hash, output hashes,
  timestamp)

## 12. Prohibited analysis in this experiment

No reading of historical winning-number values; no historical frequencies,
pairs, sums, gaps, streaks, overlaps, correlations, entropy, randomness
tests, p-values, rankings, candidate pools, models, or tickets. Phase 2 may
read only metadata needed to size and segment the null references.

## 13. Success / failure criteria

PASS requires: all 16 regimes represented; engine correctness proven by
tests and theory-validation; all catalog statistics computed or documented
as inapplicable; convergence status reported honestly (NOT CONVERGED is a
valid outcome); deterministic offline regeneration; manifest provenance
complete; `verify_phase2.py` green alongside Phase 0/1 verifiers.
