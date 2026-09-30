# Phase 1 — Historical Draw Acquisition, Normalization, Validation, and Provenance

Build command: `python scripts/build_draw_database.py` (offline rebuild from
preserved raw artifacts; `--fetch` re-pulls live sources first).
Verification: `python scripts/verify_phase1.py`.

Governing principle enforced throughout: no draw enters analysis without
source provenance, deterministic parsing, statistical-regime assignment,
structural validation, and explicit data-quality status. No statistical
pattern analysis, randomness testing, or prediction was performed.

## A. Dataset summary

| Game | Earliest verified draw | Latest verified draw | Total normalized | Analysis-eligible | Excluded / quarantined |
|---|---|---|---|---|---|
| powerball (main) | 1992-04-22 | 2026-09-28 | 3,861 | 3,861 | 0 |
| powerball (double_play) | 2021-08-23 | 2026-09-28 | 799 | 799 | 0 |
| mega_millions (main) | 1996-09-06 | 2026-09-29 | 3,064 | 3,062 | 2 conflict-affected |
| florida_lotto (main) | 1988-05-07 | 2026-09-26 | 3,409 | 3,409 | 0 |
| florida_lotto (double_play) | 2020-10-10 | 2026-09-26 | 623 | 623 | 0 |
| **Total** | | | **11,756** | **11,754** | **2** |

Staged raw records parsed from all sources: 31,593 (before multi-source
reconciliation collapsed them to canonical draws).

## B. Regime coverage (main stream)

Every statistical pool group's observed span matches its regime span; all
regimes represented in the acquired data are covered end-to-end by official
sources.

| Game | Statistical regime | Draws | Observed span |
|---|---|---|---|
| powerball | PB-S01 | 578 | 1992-04-22 .. 1997-11-01 |
| powerball | PB-S02 | 514 | 1997-11-05 .. 2002-10-05 |
| powerball | PB-S03 | 302 | 2002-10-09 .. 2005-08-27 |
| powerball | PB-S04 | 350 | 2005-08-31 .. 2009-01-03 |
| powerball | PB-S05 | 316 | 2009-01-07 .. 2012-01-14 |
| powerball | PB-S06 | 388 | 2012-01-18 .. 2015-10-03 |
| powerball | PB-S07 | 1413 | 2015-10-07 .. 2026-09-28 |
| mega_millions | MM-S01 | 172 | 1996-09-06 .. 1999-01-12 |
| mega_millions | MM-S02 | 348 | 1999-01-15 .. 2002-05-14 |
| mega_millions | MM-S03 | 324 | 2002-05-17 .. 2005-06-21 |
| mega_millions | MM-S04 | 869 | 2005-06-24 .. 2013-10-18 |
| mega_millions | MM-S05 | 420 | 2013-10-22 .. 2017-10-27 |
| mega_millions | MM-S06 | 776 | 2017-10-31 .. 2025-04-04 |
| mega_millions | MM-S07 | 155 | 2025-04-08 .. 2026-09-29 |
| florida_lotto | FL-S01 | 599 | 1988-05-07 .. 1999-10-23 |
| florida_lotto | FL-S02 | 2810 | 1999-10-27 .. 2026-09-26 |

The verified 1999 Big Game boundary holds in the data: 1999-01-12 →
MM-R002/MM-S01, 1999-01-15 → MM-R003/MM-S02. No draw is assigned inside a
quarantine window.

## C. Source coverage

All draw records derive from official lottery-operator or official
open-data sources. No secondary source contributed a canonical record.

| Source | Type | Coverage contributed |
|---|---|---|
| SRC-NY-PB-ARCHIVE | NY Lottery official year-archive HTML | Powerball main + Double Play, 1992-04-22 onward |
| SRC-NY-MM-ARCHIVE | NY Lottery official year-archive HTML | Mega Millions / Big Game, 1996-09-06 onward |
| SRC-NY-PB-DATA | NY State Open Data (Socrata) | Powerball 2010+, reconciliation + Double Play |
| SRC-NY-MM-DATA | NY State Open Data (Socrata) | Mega Millions 2002+, reconciliation |
| SRC-MO-PB-XLSX | Missouri Lottery official Excel | Powerball 1998+, physical draw order |
| SRC-TX-PB-CSV | Texas Lottery official CSV | Powerball 2010+, physical draw order |
| SRC-TX-MM-CSV | Texas Lottery official CSV | Mega Millions 2003+, physical draw order |
| SRC-FL-PB-HIST-PDF | Florida Lottery official history PDF | Powerball 2009+, incl. Double Play rows |
| SRC-FL-MM-HIST-PDF | Florida Lottery official history PDF | Mega Millions 2013+ |
| SRC-FL-LOTTO-HIST-PDF | Florida Lottery official complete-history PDF | Florida Lotto 1988-05-07 onward + Double Play |

Bounded early-gap search result: nylottery.org's official archive covers
Powerball from the first draw (1992-04-22) and Mega Millions/The Big Game
from the first draw (1996-09-06), closing both previously documented gaps
with Tier-1 operator data. Missouri's workbook adds official PB coverage
from 1998 with genuine as-drawn ordering.

## D. Remaining historical gaps

One expected draw date remains unrecovered from any source:

- mega_millions 1998-02-03 (MM-R002 / MM-S01) — unresolved; ledgered in
  `metadata/missing_draws.csv`. This is the partially-verified schedule-only
  boundary era; the gap is documented, not fabricated.

No other expected scheduled dates are missing. No provisional
secondary-source draw exists in the canonical population.

## E. Cross-source reconciliation

`metadata/reconciliation_registry.csv` — 20,789 field-level comparison
records across 9,218 multi-sourced draws:

- MATCH: 19,836
- FIELD_COMPLEMENT: 951 (one source supplies a field another omits —
  resolved by documented source precedence, not treated as disagreement)
- CONFLICT: 2 (both unresolved — see Section G)
- MISSING_FROM_SOURCE / UNRESOLVED: 0 beyond the two conflicts

## F. Validation results

- Structural validation failures: 0
- Duplicate canonical draw IDs: 0
- Duplicate (game, date, stream) keys: 0
- Regime assignment failures: 0 — every draw carries a regime_id resolving
  to the inventory; every eligible draw passes `assert_poolable`.
- Quarantined draws: 0 (no unresolved material boundary exists after the
  MM-R003 resolution; quarantine machinery is tested and active)
- Missing scheduled draws: 1 (Section D)
- Analysis-ineligible draws: 2 (the two conflict-affected MM draws)

## G. Unresolved official-source conflicts

Deliberately **not** resolved; both draws are `analysis_eligible=false`:

1. mega_millions 2011-09-23 — main numbers: NY archive `21;27;32;40;52`
   vs NY Socrata `27;31;32;40;52`.
2. mega_millions 2022-05-10 — Mega Ball: NY archive `9` vs NY Socrata `6`.

## H. Florida Lotto order semantics

Preserved per Phase 0 finding via `position_semantics` / `numbers_order`:

- Through 2005-01-29: physical draw order (1,149 main draws).
- From 2005-02-02: source-sorted ascending order (2,260 main draws).

Ascending order is never treated as physical draw order. For multi-state
games, physical order is claimed only where the source documents it
(TX CSVs; MO "Numbers As Drawn" only when it provably differs from sorted).

## I. Double Play handling

PB Double Play (from 2021-08-23) and FL Lotto Double Play (from 2020-10-10)
are parsed into `draw_stream=double_play` with `-DP` draw IDs. They never
enter the canonical main-draw series; both streams are validated and
eligible as separate series. NY archive rows embedding a Double Play
sub-block are split at parse time; Socrata `double_play_winning_numbers`
produces a separate staged record.

## J. Provenance

- Draw-source artifacts preserved: 77 immutable files across 10 sources
  (104 artifacts total in store including Phase 0 evidence).
- All artifacts SHA-256 hashed; hash-match check passes for all.
- Retrieval events appended to `metadata/raw_artifacts.csv`; artifacts are
  never overwritten.
- Every canonical draw carries source_id, retrieved_at,
  raw_artifact_sha256, parser_version 1.0.0, ingestion_version 1.0.0.
- Canonical dataset SHA-256:
  `9dd19bbbf51936e68e6a2529a2a3b476ad832628be50c2f03bd62dbfe2499645`
- Manifest: `data/processed/dataset_manifest.json` (dataset_version 1.0.0,
  build timestamp, code commit, per-source artifact hashes, coverage,
  counts, parser/ingestion versions, dataset hash).

## K. Outputs

- `data/processed/draws.csv` — 11,756 canonical draws
- `data/processed/draw_numbers.csv` — normalized per-ball rows with
  position semantics
- `data/processed/dataset_manifest.json`
- `data/processed/data_quality_report.csv`
- `metadata/missing_draws.csv` — missing-draw ledger (1 unresolved date)
- `metadata/reconciliation_registry.csv` — discrepancy registry

## L. Test results

- `pytest`: 119 passed (15 Phase 1 parser/pipeline unit tests, 6
  integration dataset tests, plus all Phase 0 suites incl. boundary
  regression pins for 1999-01-12 → MM-S01 and 1999-01-15 → MM-S02)
- `ruff check src scripts tests`: clean
- `scripts/verify_phase1.py`: all checks pass
- `scripts/verify_phase0.py`: PASS (Phase 0 remains green)

## M. Reproducibility

`python scripts/build_draw_database.py --offline` rebuilds the entire
canonical dataset from preserved artifacts with no network access. Two
consecutive offline builds produced the identical dataset SHA-256
`9dd19bbbf51936e6…49645`.

## N. Recommendation

Phase 1 delivers a fully provenanced, regime-assigned, validated historical
draw database covering all three games from their earliest official
records, with separated secondary streams, preserved order semantics, a
complete reconciliation registry, and exactly two documented unresolved
conflicts plus one documented missing date — none eligible for analysis.
No statistical analysis, modeling, or number generation was performed.
Phase 2 (Monte Carlo baseline) requires explicit authorization.

PHASE 1 PASS
