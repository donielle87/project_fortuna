# Project Fortuna

A rigorous, data-driven lottery randomness and forecasting research program.

Project Fortuna investigates whether historical lottery drawings contain persistent,
reproducible, statistically defensible departures from an independent random drawing
process. A properly operated lottery is **presumed random** unless evidence demonstrates
otherwise. Historical frequency alone is not predictive evidence; a long absence does
not make a number "due"; a recent streak does not make a number "hot."

See `docs/methodology.md` for the scientific ground rules and `docs/governance.md` for
the research process (preregistration, holdouts, prospective validation, permanent
retention of rejected hypotheses).

## Repository status

**Phase 0 — repository initialization, rule provenance, and statistical-regime
verification.** No predictive modeling, prediction generation, or exploratory
hot/cold/overdue analysis has been performed. See `reports/phase0/` for the Phase 0
verification report.

## Games covered

| Game | Current matrix |
|---|---|
| Powerball | 5/69 + Powerball 1/26 |
| Mega Millions | 5/70 + Mega Ball 1/24 |
| Florida Lotto | 6/53 (no special ball) |

Historical statistical regimes for each game are recorded in `metadata/game_regimes.csv`.
Draws are never pooled across different `statistical_regime_id` groups.

## Requirements

- Python **3.12** (3.11+ supported; 3.12 is the reference/development version)
- pip

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/Scripts/activate     # Git Bash
pip install -e ".[dev]"
```

## Commands

| Purpose | Command |
|---|---|
| Run test suite | `pytest` |
| Lint | `ruff check .` |
| Format check | `ruff format --check .` |
| Phase 0 rule/regime verification | `python scripts/verify_phase0.py` |
| Fetch & register official sources | `python scripts/fetch_sources.py` |
| Print regime inventory | `python scripts/show_regimes.py` |

## Layout

```
config/games/          per-game configuration (references regime metadata)
data/raw/              immutable retrieved source artifacts (committed, hashed)
data/staging/          intermediate parsed data
data/processed/        analysis-ready data
data/reference/        static reference data
metadata/              games, game_regimes, source_registry, rule_change_log,
                       raw_artifacts, draw_sources (schema-validated CSV)
registry/              research registries (hypotheses, experiments, models,
                       predictions, decisions)
research/              hypotheses/ preregistrations/ exploratory/ confirmatory/
src/fortuna/           Python package (see below)
tests/                 unit/ integration/ data_contracts/ regression/
scripts/               operational scripts
reports/               phase0/ audits/ experiments/ predictions/
docs/                  methodology, governance, data dictionary, source policy,
                       architecture
```

`src/fortuna/` modules:

- `schemas/` — pydantic models for games, regimes, sources, raw artifacts, draws
- `rules/` — regime registry loading, draw→regime assignment, pooling guard
- `validation/` — draw validation against regime matrices
- `provenance/` — SHA-256 hashing and the immutable raw-artifact store
- `ingestion/` — source fetching (writes artifacts + registry rows)
- `sources/` — source/draw-source registry loaders
- `reporting/` — report helpers
- `simulation/`, `statistics/`, `features/`, `models/`, `backtesting/`,
  `calibration/`, `portfolio/`, `prospective/` — reserved for later phases
  (placeholders; model training is prohibited until governance gates pass)
