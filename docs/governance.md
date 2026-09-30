# Governance

Project Fortuna assumes a properly operated lottery is random unless evidence
demonstrates otherwise. Governance exists to keep the research honest.

## Phase gates

- **Phase 0 (this phase)**: rule/regime reconstruction, provenance, contracts.
  No modeling, no predictions, no number analysis.
- **Phase 1+**: requires explicit research-lead authorization. Nothing in this
  repository may be used to generate ticket suggestions.

## Registries

| Registry | Path | Purpose |
|---|---|---|
| Source registry | `metadata/source_registry.csv` | Every authority consulted, with authority tier, URL, retrieval time, SHA-256 |
| Raw artifact manifest | `metadata/raw_artifacts.csv` | Immutable artifacts: hash, path, retrieval event |
| Rule-change log | `metadata/rule_change_log.csv` | Every legal/statistical event, classified by materiality |
| Hypothesis registry | `registry/hypothesis_registry.csv` | Hypotheses must be registered *before* the analysis they describe |
| Experiment registry | `registry/experiment_registry.csv` | Each analysis run, linked to hypotheses and code version |
| Model registry | `registry/model_registry.csv` | Phase 1+ models only |
| Prediction ledger | `registry/prediction_ledger.csv` | Prospective predictions logged *before* the covered draw |
| Decision log | `registry/decision_log.csv` | Append-only record of material research decisions |

## Discovery vs. confirmation

Findings from exploratory analysis on a data slice are *discovery* and may not
be reported as evidence. Confirmation requires either a pre-registered
hypothesis tested on out-of-sample draws, or a prospective prediction logged
before the draw.

## What does not count as evidence

- Hot/cold/overdue number patterns in historical data alone
- Streaks, gaps, or "due" numbers
- In-sample fit of any model
- Any comparison pooled across statistical pool groups (forbidden by
  `fortuna.rules.assign.assert_poolable`)

## Conflict of authority

Official operator records outrank secondary sources. When two official sources
conflict, the discrepancy is recorded (not silently resolved) — see
`SRC-FL-FACTSHEET` vs. the official draw archive on the 1988 matrix (46 vs. 49).
