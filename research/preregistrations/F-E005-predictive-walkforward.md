# F-E005 — Finite Predictive Walk-Forward Benchmark

**Registered:** 2026-10-07, before any walk-forward performance is
calculated.
**Classification:** `predictive_research_exploratory`
**Config:** `config/experiments/F-E005.yaml` (frozen; authoritative
machine-readable form of this preregistration)

## Scientific question

Can a predeclared forecasting algorithm assign higher probability to
future lottery outcomes than the fair-uniform model, when every
prediction is made strictly from information available before that
drawing?

Phases 3/3B found no surviving historical anomaly and positional
exploration has terminated under its stopping rule. That does not
logically rule out weak multivariate predictive structure. F-E005 is
the ONE bounded historical predictive-model study authorized before
the historical-search stopping rule applies.

## Stopping principle

One fixed model family (F-M000..F-M004) is evaluated. If no model
clears the preregistered predictive gate:

**HISTORICAL PREDICTIVE-EDGE SEARCH TERMINATES.**

No additional algorithms, hyperparameter grids, transformers, random
forests, neural networks, genetic algorithms, Fourier features,
astrology-like transforms, recency heuristics, post-hoc ensembles, or
lottery-specific tricks may be added after results are observed.
A null result is an accepted result.

## Task 0 provenance note (F-E004)

F-E004 scientific outputs are pinned to the analysis-code commit
recorded in `data/analysis/phase3b/phase3b_manifest.json`. Repository
HEAD at F-E005 start (`7de9bd9`) includes the later CSV
schema-normalization patch. Exact F-E004 reproduction uses the
manifest-pinned code state, not necessarily current HEAD. F-E004 is
not reopened.

## Pinned inputs

- Corrected Phase 1 dataset SHA-256:
  `200174427b4abcc6bcc0aa3761174db237ae52e266e88cfc88bae39f27c138ff`
- Phase 2 v4 observation-plan SHA-256:
  `8309e1dd673e339b66b1fae09d02a0f2b205a62ada2882c1590645d1bf2ac10a`
- Exploration IDs: `metadata/phase3_exploration_ids_v2.csv`
  (8,248 draw IDs)
- Holdout IDs: `metadata/phase3_holdout_ids.csv` (2,072 draw IDs,
  metadata only)
- Holdout seals (metadata-verified only): v1
  `6cb7c382924c4ad55ab0958239cb488cd95b0e0b99407ebebcfe822a4b16b91c`,
  v2 `6dc9a023b4bfd7b7fcfa321ebde9455687222eb0ef316a458d0d01effe18f2e0`

## Data firewall

Training and evaluation use ONLY the corrected exploration IDs. The
loader (`fortuna.analysis.loader.load_exploration_draws`) drops any row
whose `draw_id` is not in the exploration set BEFORE parsing any
outcome field. No holdout frequency, feature, ranking, score, log
likelihood, or candidate pool is computed. Holdout IDs are used only
for disjointness and seal-verification metadata checks. Draws after the
accepted historical cutoff are not part of F-E005.

## Regime discipline

Prediction is performed separately within each statistical regime.
For every forecast at time t, training data = draws from the SAME
statistical regime strictly before t. No cross-regime training, no
pooling of incompatible matrices; cross-regime aggregation occurs only
after each draw has been properly predicted within its own regime.

## Exact K-of-N probability model

All non-uniform main-ball models assign, for positive weights w_i,

    P(S) = prod_{i in S} w_i / e_K(w),

where e_K is the K-th elementary symmetric polynomial, computed by
dynamic programming in log space (`fortuna.models.wsubset`). Exact
inclusion marginals

    P(i in S) = w_i * e_{K-1}(w_{-i}) / e_K(w)

are computed by prefix/suffix DP. Both are tested against brute-force
enumeration on small synthetic systems (tests/unit/test_wsubset.py).
All-equal weights recover the uniform 1/C(N,K) benchmark.

## Special-ball model

For games with a special ball, a proper categorical distribution is
used (uniform 1/M for F-M000; softmax-normalized positive scores for
non-uniform models). Main-ball and special-ball probabilities are
scored separately and jointly. Florida Lotto carries no special-ball
model.

## Frozen model family

- **F-M000 — uniform benchmark:** w_i = 1; P(S) = 1/C(N,K); special 1/M.
- **F-M001 — shrunk expanding frequency:** w_i ∝ c_i + 100·p,
  p = K/N; special: p_i ∝ c_i + 100/M.
- **F-M002 — EWMA frequency:** half-life 50 draws (λ = 2^(−1/50)),
  frozen; w_i ∝ ewma_i + 25·p; special analogous with A = 25.
- **F-M003 — recency/gap:** single coefficient on the standardized gap
  feature (log1p(gap) standardized against fair-geometric null
  moments); the data learn whether larger gaps raise, lower, or leave
  unchanged next-draw weight; L2 penalty from {0.1, 1, 10, 100} via
  nested chronological validation; special-ball analog uses the same
  gap feature with a softmax link.
- **F-M004 — regularized multifeature:** six per-ball features, all
  computed from draws < t:
  1. expanding-frequency z-residual;
  2. EWMA (hl=25) frequency z-residual;
  3. EWMA (hl=100) frequency z-residual;
  4. log1p gap standardized vs fair-geometric null moments;
  5. appeared-in-previous-draw indicator;
  6. smoothed historical affinity with the previous draw's main balls
     (pair counts smoothed with a0 = 50 pseudo-draws toward the fair
     pair rate, self-pairs excluded).
  score_i = β·x_i, w_i = exp(clip(score, ±8)); β fit by penalized
  conditional log-likelihood of the exact weighted-subset
  distribution; L2 penalty grid {0.1, 1, 10, 100}, nested chronological
  selection. Special-ball analog: five features (expanding z, EWMA-25 z,
  EWMA-100 z, gap z, previous-special indicator) under multinomial
  logit with the same penalty grid.

No equipment or physical-position features are used (F-E004 positional
exploration terminated without a candidate hypothesis; equipment data
are not demonstrably pre-draw available).

## Warmup, refit cadence, nested selection

- Minimum prior history before scoring: 100 eligible exploration draws
  within the same statistical regime. Below that: label WARMUP, no
  prediction, no backfill.
- F-M001/F-M002 update deterministically every draw.
- F-M003/F-M004 refit every 25 scored draws per regime; between refits
  parameters persist while features update. The first scored
  prediction uses a fit on the preceding ≥100 training draws only.
- Penalty selection: the chronological LAST 20% of the current
  training sample is inner validation; the FIRST 80% (≥50 draws) is
  inner fit. Validation log-likelihood selects the penalty; ties
  break toward the stronger penalty; if fewer than 50 inner-fit draws
  are available the frozen fallback λ = 100 applies. No random CV, no
  shuffling.
- Fitting: deterministic Adam (lr 0.05, 150 iterations, β init 0) on
  the penalized conditional log-likelihood. Frozen optimizer settings;
  not tuned on F-E005 outcomes.

## Strict walk-forward

For each scored draw t: stop at t; build state/features from draws < t;
fit/refit on draws < t only; freeze the probability distribution;
reveal the exploration outcome; score; advance. No batch-fitting on the
full exploration period; no future-aware standardization (all feature
standardization uses regime constants or fair-null moments); no global
feature scaling; no future hyperparameter tuning.

## Primary scoring

Exact set log loss per draw:

    d_t = log P_model(S_t) − log P_uniform(S_t).

Positive is better than uniform. Joint score adds the special-ball log
probability where applicable. Reported per model × {pooled, regime,
game}: mean d_t, median, cumulative, standard error, 95% CI.

## Prequential e-values

    LR_t = P_model(Y_t | past) / P_uniform(Y_t);   E_T = prod_t LR_t

computed in log space over all scored draws (joint outcome for
special-ball games, main-only for Florida Lotto). Per-model gate
E_model ≥ 80 (= 4/0.05 for the four-model family). Equal-weight
mixture E_mix = (E_001 + E_002 + E_003 + E_004)/4 with diagnostic
threshold E_mix ≥ 20. Both are reported; the final gate below governs.

## Candidate-pool metrics (evaluation only)

Main balls ranked by model marginal inclusion probability (pre-draw
information only — never post-outcome). Pool sizes m ∈ {10, 15, 20}
where m < N. Per model × m: mean hits, P(≥3), P(≥4), P(≥5) for K = 6
games, exact random hypergeometric expectation, observed/random lift,
95% CI. All-but-one targets: X ≥ 4 (K = 5), X ≥ 5 (K = 6). The m = 15
relative mean-hit lift must be ≥ 0.02 AND the paired 95% CI for the
absolute hit improvement must exclude zero. No pool is emitted as a
recommendation or ticket; no user-facing number output is produced.

Special-ball metrics: top-1 probability/rank of the actual special vs
1/M; top-5 containment vs 5/M.

## Stability

Per regime: mean d_main. A model must show positive mean d_main in at
least 60% of regimes with ≥50 scored predictions, and no single regime
may contribute >50% of the total positive pooled log-score gain.

## Predictive gate (frozen)

A model EARNS CONSIDERATION FOR SEALED-HOLDOUT CONFIRMATION only if ALL
nine conditions hold:

1. pooled cumulative log-score improvement over F-M000 > 0;
2. model e-value E_model ≥ 80;
3. equal-weight family mixture E_mix ≥ 20;
4. positive mean d_main in ≥60% of regimes with ≥50 scored
   predictions;
5. no single regime contributes >50% of total positive log-score gain;
6. m = 15 candidate-pool relative mean-hit lift ≥ 0.02 over the exact
   hypergeometric expectation;
7. paired 95% CI for the m = 15 absolute hit improvement excludes zero;
8. no identified leakage/provenance defect;
9. implementation passes synthetic positive and null controls.

If multiple models pass all nine, ONE candidate is selected by:
(i) highest cumulative out-of-sample main-set log-score improvement;
(ii) higher m = 15 mean-hit lift; (iii) simpler lower-numbered model.
If no model passes all nine: no holdout access; the historical
predictive-edge search terminates.

## Synthetic controls

Positive controls (matrix N = 35, K = 5, M = 10; 500 draws; warmup
100; deterministic PCG64DXSM streams under scope `F-E005`):

- A: persistent ball-weight bias (7 boosted balls × (1+δ),
  δ ∈ {0.5, 1, 2});
- B: recency/gap-dependent bias (w ∝ exp(β·gap_z), β ∈ {0.5, 1, 2});
- C: previous-draw-dependent bias (w ∝ exp(β·1{i∈S_{t−1}}),
  β ∈ {0.5, 1, 2});
- D: time-varying bias (boosted 7-ball subset rotates every 100 draws,
  δ ∈ {1, 2, 4}).

Pass criterion: at least one frozen model produces positive pooled
walk-forward log-score lift AND m = 15 lift ≥ 0.02 at the strongest
injected effect, per scenario.

Null controls: 10 fair without-replacement replicate histories under
the same matrix. Pass criterion: no model clears the full predictive
gate in any replicate; pooled mean d_main does not systematically
exceed a sampling-noise band.

## Outputs

`data/analysis/phase4a/` — walk-forward predictions (probability
summaries and model diagnostics for exploration draws only), log-score
by-draw/summary/regime tables, candidate-pool metrics, special-ball
metrics, e-values, hyperparameter history, synthetic controls, gate
table, candidate table, manifest. No ticket, recommendation, or
number-ranking artifacts.

## Model registry

F-M000..F-M004 registered with status `specified` before execution;
post-execution statuses limited to `benchmark`, `evaluated`,
`candidate_for_holdout_confirmation`, or `rejected_no_predictive_edge`.
