# Phase 1 — Historical Draw Acquisition, Normalization, Validation, and Provenance

Build command: `python scripts/build_draw_database.py` (offline rebuild from
preserved raw artifacts; `--fetch` re-pulls live sources first; `--release`
refuses to build when code or input metadata contains uncommitted changes).
Verification: `python scripts/verify_phase1.py`.

Governing principle enforced throughout: no draw enters analysis without
source provenance, deterministic parsing, statistical-regime assignment,
structural validation, explicit data-quality status, and at least one
authoritative (Tier 1/2) source. No statistical pattern analysis, randomness
testing, or prediction was performed.

**Corrective-gate update (2026-09-30):** this revision corrects a
source-authority defect in the initial Phase 1 build — `SRC-NY-PB-ARCHIVE`
and `SRC-NY-MM-ARCHIVE` point to nylottery.org, an independent unofficial
service not affiliated with the New York State Gaming Commission or the New
York Lottery. Both are reclassified as Tier-3 `secondary` sources; canonical
PB/MM history was rebuilt on official replacement sources, and the manifest
now records the committed build code state (`build_code_commit`).

## A. Dataset summary

| Game | Earliest verified draw | Latest verified draw | Total normalized | Analysis-eligible | Ineligible |
|---|---|---|---|---|---|
| powerball (main) | 1992-04-22 | 2026-09-28 | 3,863 | 3,863 | 0 |
| powerball (double_play) | 2021-08-23 | 2026-09-28 | 799 | 799 | 0 |
| mega_millions (main) | 1996-09-06 | 2026-09-29 | 3,074 | 3,060 | 14 |
| florida_lotto (main) | 1988-05-07 | 2026-09-26 | 3,409 | 3,409 | 0 |
| florida_lotto (double_play) | 2020-10-10 | 2026-09-26 | 623 | 623 | 0 |
| **Total** | | | **11,768** | **11,754** | **14** |

Staged raw records parsed from all sources: 62,836 (includes identical
re-retrieval artifacts; identical parsed records from the same source are
deduplicated during grouping before reconciliation).

`num_draws = num_analysis_eligible + num_analysis_ineligible`
(11,768 = 11,754 + 14) reconciles exactly in the manifest, which also carries
`analysis_ineligible_reason_counts`: `unofficial_source_only` 9,
`unresolved_conflict` 5.

## B. Regime coverage (main stream)

Every statistical pool group's observed span matches its regime span; all
regimes are covered end-to-end by authoritative sources.

| Game | Statistical regime | Draws | Observed span |
|---|---|---|---|
| powerball | PB-S01 | 578 | 1992-04-22 .. 1997-11-01 |
| powerball | PB-S02 | 514 | 1997-11-05 .. 2002-10-05 |
| powerball | PB-S03 | 302 | 2002-10-09 .. 2005-08-27 |
| powerball | PB-S04 | 350 | 2005-08-31 .. 2009-01-03 |
| powerball | PB-S05 | 316 | 2009-01-07 .. 2012-01-14 |
| powerball | PB-S06 | 389 | 2012-01-18 .. 2015-10-03 |
| powerball | PB-S07 | 1414 | 2015-10-07 .. 2026-09-28 |
| mega_millions | MM-S01 | 174 | 1996-09-06 .. 1999-01-12 |
| mega_millions | MM-S02 | 348 | 1999-01-15 .. 2002-05-14 |
| mega_millions | MM-S03 | 325 | 2002-05-17 .. 2005-06-21 |
| mega_millions | MM-S04 | 869 | 2005-06-24 .. 2013-10-18 |
| mega_millions | MM-S05 | 426 | 2013-10-22 .. 2017-10-27 |
| mega_millions | MM-S06 | 777 | 2017-10-31 .. 2025-04-04 |
| mega_millions | MM-S07 | 155 | 2025-04-08 .. 2026-09-29 |
| florida_lotto | FL-S01 | 599 | 1988-05-07 .. 1999-10-23 |
| florida_lotto | FL-S02 | 2810 | 1999-10-27 .. 2026-09-26 |

(Regime draw counts reflect total normalized draws including ineligible
rows.) The verified 1999 Big Game boundary holds: 1999-01-12 →
MM-R002/MM-S01, 1999-01-15 → MM-R003/MM-S02. No draw is assigned inside a
quarantine window.

## C. Source coverage and authority tiers

Every analysis-eligible draw is backed by at least one Tier-1 or Tier-2
source. Tier-3 unofficial sources may only corroborate — never sole-support.

### Authoritative draw sources (Tier 1/2)

| Source | Tier | Type | Coverage contributed |
|---|---|---|---|
| SRC-WI-PB-CSV | 1 | Wisconsin Lottery CSV export (`dir=drawn`) | Powerball full history from 1992-04-22, physical draw order — **primary early-PB replacement** |
| SRC-MD-MM-ARCHIVE | 1 | Maryland Lottery archive (founding Big Game member) | Mega Millions / Big Game full history from 1996-09-06 — **primary early-MM replacement** |
| SRC-MM-COM-API | 1 | Mega Millions operator draw-data service | Mega Millions 2010-02-05+; highest MM precedence |
| SRC-MD-PB-ARCHIVE | 1 | Maryland Lottery archive | Powerball 2010-01-30+, supplemental |
| SRC-PB-COM-DRAWRESULT | 1 | powerball.com operator draw-result page | Point verification (fetched for 2010-09-15) |
| SRC-MO-PB-XLSX | 1 | Missouri Lottery Excel | Powerball 1998+, physical draw order where provable |
| SRC-TX-PB-CSV | 1 | Texas Lottery CSV | Powerball 2010+, physical draw order |
| SRC-TX-MM-CSV | 1 | Texas Lottery CSV | Mega Millions 2003+, physical draw order |
| SRC-FL-PB-HIST-PDF | 1 | Florida Lottery history PDF | Powerball 2009+, incl. Double Play rows |
| SRC-FL-MM-HIST-PDF | 1 | Florida Lottery history PDF | Mega Millions 2013+ |
| SRC-FL-LOTTO-HIST-PDF | 1 | Florida Lottery history PDF | Florida Lotto 1988-05-07 onward + Double Play |
| SRC-NY-PB-DATA | 2 | NY State Open Data (Socrata) | Powerball 2010+, reconciliation + Double Play |
| SRC-NY-MM-DATA | 2 | NY State Open Data (Socrata) | Mega Millions 2002+, reconciliation |
| SRC-MM-2022-CORRECTION | 1 | Mega Millions official press statement | Resolution evidence for 2022-05-10 (not a draw feed) |

### Reclassified unofficial sources (Tier 3 — reconciliation only)

| Source | Tier | Note |
|---|---|---|
| SRC-NY-PB-ARCHIVE | 3 | nylottery.org — self-identifies as independent, unofficial, not affiliated with NY Lottery/NYSGC. Reclassified 2026-09-30; artifacts preserved. |
| SRC-NY-MM-ARCHIVE | 3 | Same reclassification. |

Decision recorded in `registry/decision_log.csv` (D-002). All nylottery.org
raw artifacts remain preserved under `data/raw/` for audit history; zero
additional fetches were made from that domain.

## D. Remaining historical gaps

- **mega_millions 1998-02-03** (MM-R002 / MM-S01) — still unrecovered from
  any source; ledgered in `metadata/missing_draws.csv`.
- **9 MM draws supported only by nylottery.org** (no official source covers
  them): 1996-11-29, 1998-01-23, 1998-06-09, 2000-03-17, 2000-12-19,
  2001-01-26, 2001-06-15, 2001-10-05, 2002-03-15. These dates are absent
  from the MD archive's Big Game era; they remain canonical-but-ineligible
  (`unofficial_source_only`), not fabricated into eligibility.

## E. Cross-source reconciliation

`metadata/reconciliation_registry.csv` — 28,134 field-level comparison
records:

- MATCH: 26,434
- FIELD_COMPLEMENT: 1,670
- CONFLICT: 30 — 19 resolved by documented authoritative precedence or
  recorded official resolution; 11 unresolved field-level disagreements
  concentrated in 5 draws (Section G).

A Tier-3 divergence from an authoritative primary is logged as a resolved
CONFLICT (secondary-source error, noted for audit); only
authoritative-vs-authoritative disagreements stay `unresolved` and block
eligibility.

## F. Validation results

- Structural validation failures: 0
- Duplicate canonical draw IDs: 0; duplicate (game, date, stream) keys: 0
- Regime assignment failures: 0
- Quarantined draws: 0
- Missing scheduled draws: 1 (Section D)
- Analysis-ineligible draws: 14 (9 `unofficial_source_only`,
  5 `unresolved_conflict`)

## G. Conflict status

### Officially resolved (in `metadata/draw_resolutions.csv`)

1. **mega_millions 2011-09-23** — RESOLVED `21;27;32;40;52` + MB 36.
   Official Mega Millions draw data (SRC-MM-COM-API) reports that exact
   result; MD archive corroborates. NY Socrata `27;31;32;40;52` is a
   state-portal transcription error.
2. **mega_millions 2022-05-10** — RESOLVED Mega Ball `9`. Official Mega
   Millions statement (SRC-MM-2022-CORRECTION) documents the host's
   announced 6 as an error; the drawn 9 was audited and is official.
   megamillions.com draw data agrees.
3. **powerball 2010-09-15** — RESOLVED `7;20;21;34;43`. powerball.com
   operator page (SRC-PB-COM-DRAWRESULT) plus WI/MO/TX/FL/NY corroborate;
   MD archive alone reads `1;20;21;34;43`.
4. **mega_millions 2018-06-26** — RESOLVED Mega Ball `19`. Operator record
   (SRC-MM-COM-API) + TX + FL + NY corroborate; MD archive alone reads 13.
5. **mega_millions 2018-12-28** — RESOLVED `9;10;25;37;38`. Operator record
   + TX + FL + NY corroborate; MD archive alone reads `3;10;25;37;38`.

### Genuinely unresolved (analysis-ineligible)

All are MD-archive-vs-multiple-official-sources disagreements with no
operator-level adjudicating record located:

1. mega_millions 2003-03-18 — main numbers (MD `13;14;15;29;49` vs
   NY `13;14;16;29;49`).
2. mega_millions 2004-06-15 — main numbers + Mega Ball (MD `7;10;14;24;25`
   +38 vs TX/NY `18;23;27;29;44` +24).
3. mega_millions 2004-07-16 — main numbers (MD `3;21;22;35;47` vs
   TX/NY `3;21;22;35;44`).
4. mega_millions 2004-12-07 — Mega Ball (MD 22 vs TX/NY 29).
5. mega_millions 2005-04-29 — main numbers (MD `2;5;6;28;46` vs
   TX/NY `2;5;7;28;46`).

Each retains full reconciliation evidence; none is analysis-eligible.

## H. Florida Lotto order semantics

Preserved per Phase 0 finding via `numbers_order`:

- Through 2005-01-29: physical draw order (1,149 main draws).
- From 2005-02-02: source-sorted ascending order (2,260 main draws).

Ascending order is never treated as physical draw order. For multi-state
games, physical order is claimed only where the source documents it
(WI `dir=drawn` export; TX CSVs; MO "Numbers As Drawn" only when it
provably differs from sorted).

## I. Double Play handling

PB Double Play (from 2021-08-23) and FL Lotto Double Play (from 2020-10-10)
are parsed into `draw_stream=double_play` with `-DP` draw IDs. They never
enter the canonical main-draw series.

## J. Provenance and build-code accounting

- 126 immutable artifacts across 43 registered sources (includes Phase 0
  evidence artifacts and the corrective-gate operator/correction pulls).
- All artifacts SHA-256 hashed; hash-match check passes for all.
- `dataset_manifest.json` now records `build_code_commit`: the committed
  code state that produced the dataset, verified by `verify_phase1.py`
  (commit resolvable in the object store AND containing
  `src/fortuna/ingestion/pipeline.py` + `scripts/build_draw_database.py`).
  It may differ from the final data-output commit; the forbidden case —
  a commit predating the builder — is now structurally excluded.
- `python scripts/build_draw_database.py --release` refuses to produce
  release output while `src/`, `scripts/`, `config/`, `tests/`, or input
  metadata (`source_registry`, `draw_sources`, `draw_resolutions`,
  `game_regimes`, `raw_artifacts`) carry uncommitted changes.
- Canonical dataset SHA-256:
  `953c0701aeef6782a361146999ca43c1d4d2863d807c8e4dbe39cfa4108f3891`

## K. Outputs

- `data/processed/draws.csv` — 11,768 canonical draws
- `data/processed/draw_numbers.csv` — normalized per-ball rows with
  position semantics
- `data/processed/dataset_manifest.json` — provenance + counts +
  `analysis_ineligible_reason_counts`
- `data/processed/data_quality_report.csv`
- `metadata/missing_draws.csv` — missing-draw ledger (1 unresolved date)
- `metadata/reconciliation_registry.csv` — discrepancy registry
- `metadata/draw_resolutions.csv` — authoritative conflict resolutions

## L. Test results

- `pytest`: 126 passed (includes new authority-gate tests: tier-3-only
  ineligibility, tier-3 divergence not blocking, authoritative conflict
  blocking, official resolution application, new-source parsers)
- `ruff check src scripts tests`: clean
- `scripts/verify_phase1.py`: all checks pass — including the new
  source-authority gates (no tier-3-only eligible draw, no tier-1
  secondary source, precedence sanity, manifest reconciliation,
  build_code_commit resolvability)
- `scripts/verify_phase0.py`: PASS (Phase 0 remains green)

## M. Reproducibility

`python scripts/build_draw_database.py --offline` rebuilds the entire
canonical dataset from preserved artifacts with no network access; repeated
offline builds produce identical dataset SHA-256.

## N. Recommendation

Phase 1 now delivers a provenance-correct historical draw database:
unofficial sources reclassified and fenced off from eligibility, early PB
and Big Game coverage replaced with true official data, both mandated
conflicts resolved by operator evidence, manifest build provenance made
honest, and exclusion accounting explicit. The corrected population is
slightly different from the prior build (11,768 draws / 11,754 eligible)
because scientific provenance takes priority over maximum row count. No
statistical analysis, modeling, or number generation was performed. Phase 2
(Monte Carlo baseline) requires explicit authorization.
