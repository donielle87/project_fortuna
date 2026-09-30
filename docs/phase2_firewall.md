# Phase 2 Scientific Firewall — F-E001

Phase 2 constructs the fair-random null reference only. This document
records the software boundaries that prevent accidental historical-outcome
analysis during this phase.

## What Phase 2 may read from the historical record

Metadata only, and only through `src/fortuna/simulation/observation.py`:

- `game_id`, `regime_id`, `draw_date`, `draw_stream`
- `analysis_eligible`, `numbers_order`, `validation_status`, `provisional`

`ALLOWED_DRAW_FIELDS` in that module is a hard whitelist — the CSV reader
projects only those columns. Winning-number values (`main_numbers`,
`special_ball`, `multiplier`, `jackpot`, ...) are never loaded anywhere in
the simulation layer.

## What Phase 2 must never compute from historical outcomes

- frequencies, pair/triple counts, sums, gaps, streaks, droughts
- overlaps between real consecutive draws
- odd/even patterns, correlations, serial statistics, entropy
- randomness-test statistics, historical p-values, rankings
- candidate pools, predictive models, lottery tickets

## Where the boundaries live

- `simulation/observation.py` — sole reader of `draws.csv`, whitelisted
  columns, produces `metadata/phase2_observation_plan.csv`
- `simulation/engine.py`, `montecarlo.py` — consume only `RegimeMatrix`
  objects and the observation plan's counts/segment lengths
- `verify_phase2.py` — statically checks that no simulation module except
  `observation.py` references the canonical outcome columns/files
- `fortuna/statistics/pvalues.py`, `multiple_testing.py` — utilities exist
  for later phases; Phase 2 tests them on synthetic data only

## Sequential continuity rule

Any timeline position that is not analysis-eligible — missing expected
draw, ineligible draw, Tier-3-only draw, unresolved-conflict draw —
breaks the contiguous segment. Sequential statistics (F-S006, F-S007,
F-S008, F-S011) are confined within segments and never bridge those
positions.

## Double Play

`draw_stream=main` only. The engine could model Double Play matrices, but
Phase 2 generates no Double Play baselines in the reference namespace.

## Order semantics

The engine can produce physical draw order, but every F-S statistic is
order-insensitive by design. Future order-dependent analyses may only use
records with `numbers_order == physical_draw_order`; the observation plan
exposes `order_eligible_segment_lengths` for that purpose.
