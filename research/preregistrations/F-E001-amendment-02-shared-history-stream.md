# Amendment 02 to F-E001 — Shared-history Monte Carlo stream scope (D-004)

**Status:** supersedes ONLY the child-stream scope-string description in
`research/preregistrations/F-E001-phase2-fair-null-baseline.md` §5 and the
`rng:` comments of `config/experiments/F-E001.yaml` / `F-E001.v2.yaml`.
Effective config: `config/experiments/F-E001.v3.yaml`.

## Frozen wording

The registered scope string was
`"<game>|<statistical_regime>|<statistic_id>|<batch>"`, implying an
independent child stream per (regime, statistic, batch).

## Implemented behavior

One shared history stream per (game, statistical regime, batch):
`"<game>|<statistical_regime>|HISTORIES|batch<1..4>"`. Each replicate
history is generated once and all applicable catalog statistics are
computed from it. Dedicated `VALIDATION` and `STRUCTURAL` streams are
unchanged.

## Why this is scientifically valid — and preferable

- Every statistic still receives 20,000 iid fair replicate histories in
  4 independent batches; each marginal null distribution is identical in
  distribution to per-statistic streams.
- Shared histories preserve the natural JOINT dependence among
  F-S001..F-S013 under the null, which later multi-statistic analyses
  need. Thirteen independent universes would destroy it.
- It avoids ~13x redundant draw generation.
- No marginal statistic value depends on this choice; nothing was
  selected to produce a desired result.

## Provenance note

The discrepancy between frozen text and implementation was found in the
research-lead audit of commit f7ccf64, before any historical
winning-number outcome had been analyzed. No historical deviation work
had begun.
