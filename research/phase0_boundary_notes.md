# Phase 0 — boundary verification notes

Working notes from the official-source research session (2026-09-30). The
authoritative output is `metadata/game_regimes.csv`; this file records the
evidence trail and known ambiguities.

## Florida Lotto

- **6/49 proven, not 6/46.** The official complete-history PDF
  (`SRC-FL-LOTTO-HIST-PDF`) shows ball **49** in the very first draw
  (1988-05-07) and throughout the era. The official fact sheet's "46 to 53"
  wording for the 1999 change is a documented error — the draw archive is the
  direct record and controls.
- **Boundary**: last 6/49 draw Sat **1999-10-23**; sales resumed Sun
  1999-10-24 (no Sunday draws); first 6/53 draw Wed **1999-10-27**
  (`53ER99-36`, eff. 1999-10-22).
- **Ordering convention**: the archive reports *physical draw order* through
  2005-01-29 and *ascending-sorted* numbers from 2005-02-02. This is a
  reporting change (logged `RC-FL-008`), not a process change — Phase 1
  ingestion must set `ball_position` semantics accordingly.
- **2020-10-10**: machine id + ball-set metadata begin, and the first LOTTO
  DP (Double Play) row appears — matching `53ER20-76` (eff. 2020-10-08: $2
  play, built-in Multiplier, Double Play second drawing). DP rows are a
  separate draw stream sharing the 6/53 matrix.

## Powerball

- Matrix chain confirmed by WI Lottery official timeline + MUSL Group Rules
  amendment history + FL administrative rules:
  `5/45+1/45` (1992-04-22) → `5/49+1/42` (1997-11-05) → `5/53+1/42`
  (2002-10-09) → `5/55+1/42` (2005-08-31) → `5/59+1/39` (2009-01-07) →
  `5/59+1/35` (2012-01-18) → `5/69+1/26` (2015-10-07) → +Monday draws
  (2021-08-23, same matrix).
- Venue: MUSL studio Iowa → Universal Studios Orlando (2009-01-07) →
  FL Lottery Draw Studio Tallahassee (2012-01-04). Venue changes are recorded
  as administrative regimes — same equipment, same pool group.
- Power Play added 2001-03-07 (economic; mid-era regime row PB-R003 since the
  drawn-multiplier field begins there). Power Play became RNG-drawn with the
  Jan 2009 matrix change.
- COVID economic adjustments (2020-04-22) logged in rule_change_log; no
  regime split needed since assignment spans are unchanged.

## Mega Millions / The Big Game

- Chain: `5/50+1/25` Big Game Fri-only (1996-09-06) → +Tue (~1998-02) →
  `5/50+1/36` (1999-01) → renamed Mega Millions `5/52+1/52` (2002-05-17) →
  `5/56+1/46` (2005-06-24) → `5/75+1/15` (2013-10-22) → `5/70+1/25`
  (2017-10-31) → `5/70+1/24` (2025-04-08, $5, built-in Multiplier).
- MUSL M2G2 amendment history gives exact effective draw dates for
  2013/2017/2025. NY Open Data corroborates (e.g., MB=25 drawn 2025-04-04,
  the literal last ball of the old pool).
- **RESOLVED (corrective pass 2026-09-30)**: the 5/50+1/36 boundary is pinned
  by the official MI Lottery PR (`SRC-MM-MI-PR1999`): "Starting with wagers
  placed for the **January 15, 1999** Big Game drawing, players will choose
  between cash option or ... annuity" — the matrix change to 5/50+1/36 is
  announced in the same release for the same drawing. First new-matrix draw:
  Fri **1999-01-15**; last old-matrix draw: Tue **1999-01-12**; the "01-13"
  date in secondary sources is the Wednesday sales start (not a draw day).
  Corroborated by the secondary draw archive: all pre-01-15 bonus balls ≤ 25;
  the first > 25 bonus appears 01-26/99 (bonus 33). MM-R003 → verified.
- **Still partially verified (schedule-only, pool-neutral)**: the exact first
  Tuesday draw (~Feb 1998). Both sides of that boundary are pool MM-S01, so
  the uncertainty cannot contaminate statistical pooling.
- **Quarantine machinery added**: `GameRegime.first_unambiguous_draw` +
  `UnverifiedBoundaryError`. Any future unverified material boundary
  (baseline/matrix/mechanism) must carry a quarantine window; draws inside it
  cannot be assigned or pooled, and `verify_phase0.py` fails otherwise.

## Draw-data coverage gaps (documented as DrawSource gap rows)

- Powerball before 2010-02-03: no official machine-readable archive located.
- The Big Game era (1996–2002): no official machine-readable archive located.
  These gaps limit draw-level analysis coverage, not rule verification.

## Environment notes

- `SSLKEYLOGFILE` pointing at a sandbox path breaks Python `requests`/
  urllib3; `fortuna/__init__.py` and the fetcher defensively remove it.
- `files.floridalottery.com` rejects Python's TLS ClientHello; the fetcher
  falls back to curl (`fortuna/ingestion/fetch.py`).
