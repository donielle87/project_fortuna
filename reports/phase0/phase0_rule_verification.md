# PROJECT FORTUNA — PHASE 0 RULE & REGIME VERIFICATION REPORT

Date: 2026-09-30
Scope: Powerball, Mega Millions (incl. The Big Game), Florida Lotto — full
game history. Principle: RULES ARE DATA.

---

## A. Executive summary

Phase 0 reconstructed the complete rule history of all three games into a
two-level model — 22 legal regimes (`regime_id`) grouped into 16 statistical
pool groups (`statistical_regime_id`) — every row sourced, dated, and
verification-stamped. 21 of 22 regimes are `verified`; the sole exception is
`MM-R002` (early Big Game Tuesday-schedule addition), which is
`partially_verified` but pool-neutral — both sides of that boundary share
pool group MM-S01, so the residual date uncertainty cannot contaminate
statistical pooling.

30 official sources were fetched and immutably preserved (SHA-256). 98 tests
pass; the provenance and pooling-guard chain verifies end-to-end.

**Corrective update (same date)**: the MM-R003 boundary was resolved to
verified — the official MI Lottery press release states the 5/50+1/36 change
applies to "wagers placed for the January 15, 1999 Big Game drawing" (first
new-matrix draw Fri 1999-01-15; last old-matrix draw Tue 1999-01-12). A
generic `first_unambiguous_draw` quarantine mechanism plus
`UnverifiedBoundaryError` now makes silent assignment/pooling across any
future unresolved material boundary impossible, and `verify_phase0.py` fails
if an unverified material boundary lacks a quarantine window.

## B. Current verified game rules

| Game | Matrix | Price | Days | Venue | Rule of record |
|---|---|---|---|---|---|
| Powerball | 5/69 + 1/26 | $2 | Mon/Wed/Sat ~10:59 ET | FL Lottery Draw Studio, Tallahassee | MUSL Group Rules; FL 53ER25-13 |
| Mega Millions | 5/70 + 1/24 | $5 (incl. built-in Multiplier 2X–10X) | Tue/Fri ~11:00 ET | WSB-TV studio, Atlanta | MUSL M2G2 Rules (eff. 2025-04-08); FL 53ER25-12 |
| Florida Lotto | 6/53 | $2 (incl. terminal-RNG Multiplier) | Wed/Sat ~11:15 ET | FL Lottery Draw Studio, Tallahassee | FL 53ER25-14 / current 53ER26-9 |

All three draw without replacement from physical ball machines. Drawn/per-play
multipliers (Power Play, MM Multiplier, FL Multiplier) are documented but are
not part of the number-sampling process.

## C. Historical statistical regimes

Pool groups (statistically pooling is legal ONLY within one group):

- **Powerball — 7 pools**: S01 5/45+1/45 (1992); S02 5/49+1/42 (1997); S03
  5/53+1/42 (2002); S04 5/55+1/42 (2005); S05 5/59+1/39 (2009, incl. the
  Orlando→Tallahassee venue era); S06 5/59+1/35 (2012, $2); S07 5/69+1/26
  (2015, incl. 2021 Monday/Double Play era).
- **Mega Millions — 7 pools**: S01 5/50+1/25 (Big Game 1996, incl. 1998
  Tuesday addition); S02 5/50+1/36 (1999); S03 5/52+1/52 (MM relaunch 2002);
  S04 5/56+1/46 (2005, incl. FL 2013 entry); S05 5/75+1/15 (2013); S06
  5/70+1/25 (2017, $2); S07 5/70+1/24 (2025, $5).
- **Florida Lotto — 2 pools**: S01 6/49 (1988–1999-10-23); S02 6/53
  (1999-10-27–present, incl. XTRA era and $2/Double Play era).

Schedule, price, venue, and reporting changes are recorded as distinct legal
regimes that share a pool group; matrix changes always split the group. The
registry integrity check enforces both directions.

## D. Official source inventory

30 registered sources, all fetched and hash-preserved under `data/raw/`:

- **Tier 1 (operator rules / government registers / official archives)**:
  MUSL Powerball Group Rules (amendment history), MUSL M2G2 Product Group
  Rules (amendment history), VT/NJ official rule PDFs, Powerball and Mega
  Millions official announcements, WI Lottery official timeline, Mega Millions
  About page, Florida Lottery rules/fact sheet/overview/complete history PDF,
  FL winning-numbers archive, and ten Florida Administrative rules
  (53ER08-84, 53ER12-6, 2015 FAR entry, 53ER25-13, 53ER13-32, 53ER17-70,
  53ER25-12, 53ER99-36, 53ER09-54, 53ER20-76, 53ER26-9).
- **Tier 2**: NY Open Data draw datasets (PB d6yy-54nr from 2010-02-03; MM
  5xaw-6ayf from 2002-05-17), MI Lottery 2001 annual report.

Every boundary in `game_regimes.csv` carries its `source_id`; `verify_phase0`
confirms all citations resolve.

## E. Empirical cross-checks

Regime boundaries were additionally verified against actual draw data:

- Official FL Lotto archive: ball 49 appears in the first draw (1988-05-07)
  proving the launch matrix was 6/49 — the fact sheet's "46 to 53" wording is
  a documented official-source error. Last 6/49 draw 1999-10-23; first 6/53
  draw 1999-10-27.
- NY Open Data corroborates: PB 5/59→5/69 at 2015-10-07; MM Mega Ball 25
  drawn 2025-04-04 (last old-matrix draw) then 1/24 from 2025-04-08.
- FL archive reporting conventions: physical draw order through 2005-01-29,
  sorted ascending from 2005-02-02; machine/ball-set IDs and Double Play rows
  begin 2020-10-10. Both logged as administrative events, not regime splits.

## F. Validation infrastructure

- `fortuna.rules.assign_regime` — raises on uncovered/ambiguous dates; no
  silent admission.
- `fortuna.validation.validate_draws` — checks count, range, duplicates,
  special-ball rules, span, and that the claimed regime equals the regime
  actually governing the draw date.
- `fortuna.rules.assert_poolable` — raises `IncompatibleMatrixError` on any
  cross-pool-group pooling. Regression tests pin every verified boundary date
  and prove (e.g.) a white-68 draw fails under the 5/59 regime and a
  Mega-Ball-25 draw fails under the 1/24 regime.
- `UnverifiedBoundaryError` + `GameRegime.first_unambiguous_draw` — a generic
  quarantine for unresolved *material* boundaries: draws in the uncertain
  window can neither be assigned nor pooled.
- `fortuna.provenance.ArtifactStore` — immutable content-addressed artifacts;
  never overwrites; dedupes by hash while recording retrieval events.

## G. Unresolved issues (honest gaps — no false precision)

1. `MM-R002` (`partially_verified`, schedule-only): the Big Game's exact
   first Tuesday draw (~Feb 1998) is not pinned by a primary source. Both
   sides are pool MM-S01, so the uncertainty cannot contaminate pooling — it
   is exempt from quarantine by design.
   (`MM-R003` was resolved to verified during the corrective pass: the MI
   Lottery PR pins the 5/50+1/36 change to the 1999-01-15 drawing.)
2. `DS-PB-EARLY-GAP`: no official machine-readable Powerball draw archive
   located before 2010-02-03 (NY) / 2009-01 (FL). Pre-2010 PB regimes are
   verified as *rules* but currently have no official draw-data source.
3. `DS-MM-BIGGAME-GAP`: no official machine-readable archive for The Big Game
   era (1996–2002).
4. `53ER99-36` body text is not digitized; the 6/49→6/53 boundary is proven by
   rule metadata + the official draw archive.
5. FL Lotto fact-sheet "46 to 53" wording conflicts with the archive —
   documented, resolved in favor of the archive.
6. Exact 1992-era PB drawing-day schedule is adopted from official timelines;
   a first-edition rule text would strengthen it further.

## H. Governance / provenance status

All governance registries exist and validate: hypothesis, experiment, model,
prediction-ledger (all empty — nothing has been asserted), and decision log
(D-001 records the two-level model decision). Source policy is documented;
discovery/confirmation separation is enforced procedurally. No secrets are
present; `.env` is ignored.

## I. Test / verification results

- `pytest`: 98 passed (unit: schemas/rules/provenance/validation;
  data-contracts: all CSVs + cross-references + on-disk hash verification;
  integration: end-to-end chain; regression: historical boundaries +
  generic boundary-quarantine protection).
- `ruff check src scripts tests`: clean.
- `scripts/verify_phase0.py`: **PASS — 0 failures, 0 warnings**; all 30
  artifacts hash-verified against the manifest; all cross-references resolve.

## J. Definition-of-done & recommendation

Done when: regimes verified for all three games, sources preserved with
provenance, pooling guard enforced by code, unresolved items documented rather
than guessed — all met.

**Recommendation: the Phase 0 foundation is sound.** The project may proceed
to the next phase *only after* explicit project-owner/research-lead
authorization. Do not begin Phase 1 (draw ingestion/analysis) on the basis of
this report alone. Priority follow-ups if authorized: close the Big Game and
pre-2010 Powerball draw-data gaps, and (optionally) pin `MM-R002`'s exact
first-Tuesday date — schedule-only and pool-neutral, so non-blocking.
