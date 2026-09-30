# Phase 4A — Finite Predictive Walk-Forward Benchmark (F-E005)

**Experiment:** F-E005 — Finite Predictive Walk-Forward Benchmark
**Classification:** `predictive_research_exploratory`
**Preregistration:** `research/preregistrations/F-E005-predictive-walkforward.md`
(commit `b1bff36`, before any walk-forward performance was calculated)
**Config:** `config/experiments/F-E005.yaml` (frozen)
**Outputs:** `data/analysis/phase4a/` (manifest-hashed)

## A. QUESTION / STOPPING RULE

> Can a predeclared forecasting algorithm assign higher probability to
> future lottery outcomes than the fair-uniform model, when every
> prediction is made strictly from information available before that
> drawing?

This is the ONE bounded historical predictive-model study authorized
before the project's historical-search stopping rule applies. Exactly
five models — F-M000 through F-M004 — were frozen pre-performance. No
model may earn holdout access unless it clears all nine frozen gate
conditions. A null result is an accepted result, and no additional
algorithms may be added after seeing results.

## B. DATA FIREWALL

- Only the corrected exploration population
  (`metadata/phase3_exploration_ids_v2.csv`, 8,248 draw IDs) touched
  outcome fields.
- The loader (`fortuna.analysis.loader.load_exploration_draws`) drops
  every non-exploration row BEFORE parsing `main_numbers`/
  `special_ball`. The sealed 2,072-draw holdout was used only for
  disjointness and seal verification (v1 `6cb7c382…`, v2
  `6dc9a023…`, both verified unchanged).
- Prediction is strictly within statistical regime: training data for
  draw t = same-regime draws with date < t only. No cross-regime
  training; aggregation happens only after per-regime prediction.

## C. MODEL FAMILY (frozen)

| ID | Model |
|---|---|
| F-M000 | Fair-uniform benchmark: P(S) = 1/C(N,K), special 1/M |
| F-M001 | Shrunk expanding frequency, 100 pseudo-draws toward uniform |
| F-M002 | EWMA frequency, half-life 50 draws, shrinkage strength 25 |
| F-M003 | Single-coefficient gap model, L2 ∈ {0.1,1,10,100} nested |
| F-M004 | Six-feature penalized subset model + 5-feature softmax special-ball model, L2 ∈ {0.1,1,10,100} nested |

## D. EXACT K-OF-N PROBABILITY MODEL

All non-uniform main-ball models assign P(S) = ∏ᵢ∈S wᵢ / e_K(w) with
e_K computed by log-space dynamic programming
(`fortuna.models.wsubset`). Exact inclusion marginals
P(i∈S) = wᵢ·e_{K−1}(w_{−i})/e_K(w) via prefix/suffix DP. Both verified
against brute-force enumeration (tests/unit/test_wsubset.py):
probability mass sums to 1, marginals match enumeration, uniform
weights recover 1/C(N,K) exactly. Special balls use a proper
softmax categorical distribution, scored separately and jointly;
Florida Lotto carries none.

## E. WALK-FORWARD DESIGN

Strict chronological walk-forward per regime: features built from
draws < t; models fit/refit on draws < t only; probabilities frozen;
outcome revealed; scored; advance. No batch-fitting, no future-aware
standardization (standardizers are fair-null constants or within-state
quantities only), no future hyperparameter selection, no random
cross-validation.

## F. WARMUP / REFITS / NESTED SELECTION

- Warmup: ≥100 prior same-regime exploration draws (no backfill).
- F-M001/F-M002 update every draw (closed form).
- F-M003/F-M004: full refit every 25 scored draws per regime
  (deterministic Adam, lr 0.05, 150 iters, β init 0); between refits
  parameters persist while features update.
- L2 penalty: chronological inner split — first 80% of current training
  sample fits, last 20% validates (≥50 inner-fit draws else fallback
  λ = 100); ties break toward stronger penalty. Selection rule and
  chosen λ are logged per refit in
  `phase4a_hyperparameter_history.csv` (892 refit events).

## G. MAIN-BALL LOG-SCORE RESULTS

Pooled (6,648 scored draws; d_t = logP_model − logP_uniform):

| Model | n | mean d | cum d | 95% CI (mean) |
|---|---|---|---|---|
| F-M000 | 6,648 | 0.000000 | 0.00 | [0, 0] |
| F-M001 | 6,648 | −0.03783 | −251.50 | [−0.0446, −0.0311] |
| F-M002 | 6,648 | −0.09820 | −652.82 | [−0.1092, −0.0872] |
| F-M003 | 6,648 | −0.00172 | −11.43 | [−0.0033, −0.0001] |
| F-M004 | 6,648 | −0.00680 | −45.23 | [−0.0102, −0.0034] |

Every non-uniform model is *worse* than the fair-uniform benchmark on
pooled out-of-sample log score; all pooled 95% CIs exclude zero on the
negative side. Regime-level detail is in `phase4a_regime_summary.csv`
(70 model×regime rows): no model is positive in a majority of eligible
regimes — best is F-M003 at 3/14.

## H. SPECIAL-BALL RESULTS

Special-ball scores are separately tracked
(`phase4a_special_ball_metrics.csv`, 70 model×regime rows across the
14 special-ball regimes). Pooled joint log-score differences are
decisively negative for all non-uniform models (see I). Top-1 and
top-5 containment rates track the uniform 1/M and 5/M references; no
model shows reliable special-ball lift.

## I. E-VALUES

Prequential e-process E_T = ∏ P_model(Y_t|past)/P_uniform(Y_t), joint
main+special where applicable:

| Model | log E (main) | E (main) | E (joint) |
|---|---|---|---|
| F-M001 | −251.50 | 5.9e−110 | 2.9e−171 |
| F-M002 | −652.82 | ~10^−284 | 0 (underflow) |
| F-M003 | −11.43 | 1.1e−05 | 1.4e−09 |
| F-M004 | −45.23 | 2.3e−20 | 1.4e−36 |
| E_mix | — | 2.7e−06 | 3.6e−10 |

The evidence runs overwhelmingly *against* every candidate model —
e-values near zero mean the data favor the uniform null, not the
model. The family mixture is similarly far below its 20 threshold.

## J. CANDIDATE-POOL RESULTS

Evaluation-only metrics (no pools are emitted as recommendations).
m = 15 primary:

| Model | mean hits | random E[hits] | rel. lift | paired 95% CI (abs.) |
|---|---|---|---|---|
| F-M000 | 1.448 | 1.443 | +0.3% | [−0.019, +0.028] |
| F-M001 | 1.454 | 1.443 | +0.7% | [−0.013, +0.034] |
| F-M002 | 1.466 | 1.443 | +1.1% | [−0.007, +0.040] |
| F-M003 | 1.447 | 1.443 | +0.3% | [−0.020, +0.028] |
| F-M004 | 1.461 | 1.443 | +1.2% | [−0.006, +0.041] |

No model reaches the frozen ≥2% lift, and every CI includes zero.
All-but-one coverage (K=5 → ≥4 of 5; K=6 → ≥5 of 6) vs exact random:

| Model | obs ABO rate | random ABO rate |
|---|---|---|
| F-M000 | 0.0117 | 0.0112 |
| F-M001 | 0.0095 | 0.0112 |
| F-M002 | 0.0110 | 0.0112 |
| F-M003 | 0.0119 | 0.0112 |
| F-M004 | 0.0105 | 0.0112 |

All within sampling noise of the hypergeometric benchmark.

## K. STABILITY

Regimes with ≥50 scored predictions: 14. Positive-regime fraction:
F-M001 0/14, F-M002 0/14, F-M003 3/14 (0.214), F-M004 1/14 (0.071) —
all far below the 60% requirement. Concentration (single best regime /
total positive gain): all models ≥ 0.54 — moot, since total pooled
gain is negative for every model.

## L. SYNTHETIC POSITIVE CONTROLS

Pipeline detection verified (`phase4a_synthetic_controls.csv`,
matrix 35/5 + special 10, 500 draws, warmup 100, deterministic
`F-E005|SYNTH|…` streams). At strongest injected effect:

| Scenario | Best model | cum d | m15 lift |
|---|---|---|---|
| A persistent weight bias (δ=2) | F-M004 | +220.5 | +36.2% |
| B recency/gap bias (β=2) | F-M004 | +727.0 | +76.5% |
| C previous-draw bias (β=2) | F-M004 | +856.7 | +55.1% |
| D rotating time-varying bias (δ=4) | F-M004 | +542.5 | +52.3% |

Every scenario is detected — the pipeline demonstrably *can* find
predictive structure when it exists.

## M. SYNTHETIC NULL CONTROLS

10 fair-history replicates (same matrix/design): mean pooled cum
d_main = −10.1 (F-M001), −22.9 (F-M002), −0.67 (F-M003), −4.05
(F-M004); all replicate×model combinations are negative or noise-level
positive; **zero** null replicates produced a gate pass. Nested
penalty selection confers no spurious edge.

## N. PREDICTIVE GATE

`phase4a_model_gate.csv` — all nine frozen conditions per model:

| Condition | M001 | M002 | M003 | M004 |
|---|---|---|---|---|
| 1. pooled cum d_main > 0 | FAIL | FAIL | FAIL | FAIL |
| 2. E_model ≥ 80 | FAIL | FAIL | FAIL | FAIL |
| 3. E_mix ≥ 20 | FAIL | FAIL | FAIL | FAIL |
| 4. ≥60% eligible regimes positive | FAIL | FAIL | FAIL | FAIL |
| 5. no regime >50% of gain | FAIL | FAIL | FAIL | FAIL |
| 6. m15 lift ≥ 0.02 | FAIL | FAIL | FAIL | FAIL |
| 7. m15 CI excludes zero | FAIL | FAIL | FAIL | FAIL |
| 8. no leakage/provenance defect | PASS | PASS | PASS | PASS |
| 9. synthetic controls pass | PASS | PASS | PASS | PASS |

The machinery-related conditions (8, 9) pass; every evidence condition
fails for every model. The gate was evaluated exactly as frozen.

## O. HOLDOUT DECISION

**NO MODEL EARNS HOLDOUT ACCESS.** `phase4a_candidate_models.csv`
contains no candidate. The sealed holdout was never opened.

## P. HISTORICAL SEARCH STOPPING STATUS

**HISTORICAL PREDICTIVE-EDGE SEARCH TERMINATED.**

Per the preregistered stopping rule, no further historical
predictive-model search may be initiated. No additional algorithms,
grids, or heuristics may be added in response to this result.

## Q. HOLDOUT STATUS

**UNTOUCHED.** v1 and v2 seals verified unchanged; no holdout draw_id
appears in any output; no holdout outcome field was parsed (loader
filters on draw_id before outcome parsing).

## R. TESTS / REPRODUCIBILITY

- `verify_phase4a.py`: 84/84 checks pass (upstream verifiers, prereg
  ancestry, firewall, model family, enumeration re-verification,
  warmup/chronology, nested-selection audit, outputs, benchmarks,
  e-values, gate, candidate table, manifest hashes, artifact ban).
- pytest: full suite green (incl. enumeration tests and walk-forward
  leakage tests — predictions at t proven invariant to outcomes ≥ t).
- ruff: clean.
- Reproduction: `.venv/Scripts/python scripts/run_phase4a_analysis.py`
  is fully deterministic (no RNG on the historical path; controls use
  pinned scoped streams).
- Manifest `phase4a_manifest.json` pins dataset/exploration/holdout
  hashes, both seals, the preregistration commit, model specs, feature
  schema hash, per-regime prediction counts, and all output hashes.

## S. GIT STATE

`main` == `origin/main`, working tree clean at the final commit (see
verification report header). Upstream phases remain green.

## T. RECOMMENDATION

Phase 4A is complete and decisively negative: no frozen model beats the
fair-uniform benchmark under strict walk-forward evaluation — the
models instead underperform it, consistent with fitting noise. This is
the scientifically valid outcome. The historical predictive-edge
search is TERMINATED per the frozen stopping rule. The sealed holdout
remains unopened; holdout confirmation is moot since no candidate
exists. No further phase should begin without explicit research-lead
authorization.

PHASE 4A PASS
