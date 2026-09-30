# Methodology

## Core principle

**RULES ARE DATA.** A draw is only comparable to draws conducted under the
same sampling process. Historical matrices are not constant across a game's
archive, so every draw must be assigned to a regime before any analysis.

## Two-level model

- `regime_id` — a legal/rule era. Created for every documented change:
  matrix, mechanism, schedule, economic, administrative.
- `statistical_regime_id` — a *pool group*. Regimes sharing a pool group are
  sampling-equivalent and may be pooled. A matrix or mechanism change always
  creates a new pool group; schedule/economic/administrative changes do not.

Example: Powerball's Monday-drawing addition (2021-08-23) created regime
`PB-R010` but stayed in pool group `PB-S07` — same 5/69+1/26 sampling process.

## What defines the sampling process

`GameRegime.matrix_key()` = (main count, min, max, special count, min, max,
sampling-without-replacement). Two regimes with identical keys are
statistically pooled; different keys are forbidden from pooling.

## Boundary discipline

- `first_affected_draw` / `last_affected_draw` are **draw dates**, not sales
  or legal-effective dates (which are recorded separately). Sales transitions
  on non-draw days (e.g., Florida Lotto 1999-10-24, a Sunday) do not create
  draw boundaries.
- If a boundary cannot be proven from authoritative evidence, the regime is
  marked `partially_verified` or `unresolved` — false precision is worse than
  an honest gap (see `MM-R002`).

## Boundary-uncertainty quarantine

A **material** boundary (baseline/matrix/mechanism) that is not `verified`
cannot be allowed to silently misassign draws. Such a regime carries
`first_unambiguous_draw`: the earliest draw date provably governed by it.
`first_affected_draw` then records the earliest *candidate*. Draws in
`[first_affected_draw, first_unambiguous_draw)` are quarantined:

- `assign_regime` raises `UnverifiedBoundaryError`
- `statistical_groups` / `assert_poolable` raise `UnverifiedBoundaryError` —
  a quarantined draw can never enter a pool
- `validate_draws` records the quarantine as a rejection reason
- `verify_phase0.py` FAILs if any unverified material boundary lacks a
  quarantine window, and probes each window at runtime

Non-material partials (schedule/economic/administrative) are exempt: their
pool group is unchanged, so the uncertainty cannot contaminate statistical
pooling (e.g. `MM-R002`'s exact first-Tuesday date).

## Reporting-convention vs. process changes

Changes in how results are *reported* (e.g., Florida Lotto physical draw order
→ sorted order on 2005-02-02; machine/ball-set metadata appearing 2020-10-10)
are logged as `administrative` rule changes, not regime splits — they are
data-normalization issues handled at ingestion.

## Verification standard

Each regime row carries `verification_status` and `source_id`. Tier-1 official
sources (operator rules, government registers, official archives) are required
for `verified`. Secondary sources may identify an event but cannot be the sole
basis for `verified`.
