# Architecture

```
config/games/*.yaml      per-game pointers into the regime inventory
data/raw/<SRC-ID>/       immutable fetched artifacts (content-addressed by hash)
docs/                    governance, methodology, data dictionary, source policy
metadata/                validated CSV registries (the "rules are data" layer)
registry/                governance ledgers (hypotheses, experiments, models,
                         predictions, decisions)
reports/phase0/          Phase 0 verification report
research/                research notes
scripts/                 fetch_sources.py, verify_phase0.py, show_regimes.py
src/fortuna/             the testable library — all logic lives here, not in
                         notebooks
  schemas/               pydantic contracts + canonical CSV I/O
  rules/                 regime registry integrity, draw->regime assignment,
                         pooling guard, rule-change log
  validation/            draw validator (fails loudly on matrix violations)
  provenance/            SHA-256 hashing + immutable artifact store
  ingestion/             HTTP fetching (requests, with curl fallback for
                         TLS-incompatible hosts)
  sources/               source-registry loader
tests/                   unit / data_contracts / integration / regression
```

## Flow

1. `scripts/fetch_sources.py` → reads `metadata/source_registry.csv`, fetches
   each URL into `data/raw/<source_id>/<timestamp>_<hash>.<ext>`, appends to
   `metadata/raw_artifacts.csv`, and stamps the registry row with the content
   hash. Re-fetching identical content deduplicates; the registry keeps the
   retrieval timestamp.
2. `metadata/game_regimes.csv` is the single source of truth for rules.
   `fortuna.rules.load_regimes` enforces inventory-wide integrity (no
   overlapping spans, pool groups must be sampling-equivalent, materiality
   classification must agree with pool-group novelty).
3. `fortuna.rules.assign_regime` maps (game, date) → regime; it raises on
   uncovered or ambiguous dates — no silent admission.
4. `fortuna.validation.validate_draws` checks a `Draw` against its claimed
   *and* actual regime: count, range, duplicates, special-ball rules, span.
5. `fortuna.rules.assert_poolable` is the hard guard: pooling draws across
   statistical regimes raises `IncompatibleMatrixError`.
6. `scripts/verify_phase0.py` runs the whole chain read-only and exits
   nonzero on any contract/provenance failure.

## Design choices

- **CSV + pydantic** for registries: diffable, appendable, validated on load.
- **No database**: Phase 0 needs auditability, not infrastructure.
- **Draw schema defined now** (`schemas/draws.py`) so Phase 1 ingestion lands
  on a stable contract; `ball_position` records source-defined order and is
  never invented.
