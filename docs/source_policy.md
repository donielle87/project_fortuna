# Source Policy

## Authority tiers

| Tier | Definition | Use |
|---|---|---|
| 1 | Official lottery operator docs, official game rules, government registers, official archives | Final authority; required for `verified` status |
| 2 | Official publications supporting Tier 1 (annual reports, official data portals) | Corroboration; draw-data acquisition |
| 3 | Secondary sources (news, aggregators, wikis) | Gap identification and reconciliation only — never the sole basis for a `verified` claim |

## Rules

1. Every claim about a regime boundary must cite a `source_id` registered in
   `metadata/source_registry.csv`.
2. Every fetched source is stored immutably under `data/raw/` and hashed
   (SHA-256); the hash is recorded in `metadata/raw_artifacts.csv` and linked
   back to the source registry row. Unchanged re-fetches deduplicate by hash;
   the retrieval event is still recorded in the registry.
3. Florida Administrative Register/Code rules (`53ERxx-yy`) are cited via
   `flrules.elaws.us` (official Dept. of State mirror). Where a rule body is
   not digitized (e.g., `53ER99-36`), the metadata record plus the official
   draw archive jointly support the regime.
4. When official sources conflict, the draw archive (the direct record of what
   was actually drawn) controls the statistical claim, and the discrepancy is
   documented. Example: the FL Lotto fact sheet says "46 to 53" for 1999; the
   official archive shows ball 49 in draws from 1988-05-07 — the archive is
   authoritative and the fact sheet is flagged in its registry notes.
5. No scraping of non-official number databases for Tier-1 claims.
6. Secrets are never committed; `.env` is git-ignored (see `.env.example`).

## Known coverage gaps (documented, not hidden)

- `DS-PB-EARLY-GAP`: no official machine-readable Powerball archive located
  for draws before 2010-02-03 (NY Open Data) / Jan 2009 (FL archive).
- `DS-MM-BIGGAME-GAP`: no official machine-readable archive of The Big Game
  era (1996-09-06 .. 2002-05-14).
