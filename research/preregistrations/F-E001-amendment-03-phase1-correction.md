# Amendment 03 to F-E001 — Phase 2 null refresh for the Phase 1
# data-integrity correction (D-007 / D-008)

- **Amends:** `config/experiments/F-E001.v3.yaml` (superseded by
  `F-E001.v4.yaml` as the effective configuration)
- **Decisions:** D-007, D-008
- **Date:** 2026-09-30
- **Scope:** input refresh only. No scientific-design change.

## Why

The Phase 3 research-lead review found two Phase 1 defects:

1. **Order-semantics provenance (D-007).** A canonical row could claim
   `physical_draw_order` while storing a sequence supplied by a
   different, sorted source. The corrected schema carries
   `number_sequence_source_id`; sequence, semantics, and source are now
   atomic. The source audit reclassified Wisconsin's backfilled
   1992-2004 `dir=drawn` output and demoted all literally-ascending
   "physical" rows.
2. **Phantom source records (D-008).** Twelve `SRC-MD-*-ARCHIVE`
   records were shown by independent schedule/source evidence to be
   non-draw artifacts and are excluded via
   `metadata/draw_exclusions.csv`.

Both corrections change the Phase 2 scientific inputs: eligible draw
counts (11,754 -> 11,742), contiguous segment structure, and the
order-eligible segment structure. The fair-random null is
sample-size-matched to the observation plan, so the plan and all
affected baselines must be regenerated before any corrected historical
analysis.

## What changes

- `accepted_phase1_dataset_sha256` ->
  `200174427b4abcc6bcc0aa3761174db237ae52e266e88cfc88bae39f27c138ff`
- `metadata/phase2_observation_plan.csv` regenerated ->
  plan sha256 `8309e1dd673e339b66b1fae09d02a0f2b205a62ada2882c1590645d1bf2ac10a`
- `data/reference/null_baselines/` regenerated under v4; only regimes
  whose corrected plan rows changed may produce changed baseline values
  (per-regime streams are dataset-independent otherwise).

## What does NOT change

Fair-random assumptions; PCG64DXSM; root seed 20260930;
`sha256-scope-v1` child derivation; F-S001..F-S013 definitions and
catalog version 1.0; the v2 convergence diagnostic; shared HISTORIES
stream scope (D-004); 20,000 replicates / 4x5,000 batches; validation
draws and sigma factor; eligibility rules; segment-break rules.

## Governance

F-E001.yaml, F-E001.v2.yaml, F-E001.v3.yaml, the original F-E001
preregistration, and Amendments 01-02 are preserved unedited. The
v3-era baseline outputs remain retrievable from git history. This
amendment is committed before the v4 baselines are generated.
No holdout outcome is read anywhere in the refresh.
