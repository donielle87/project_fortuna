# Amendment 01 to F-E001 — Convergence SE correction (D-003)

**Status:** supersedes ONLY the convergence criterion in
`research/preregistrations/F-E001-phase2-fair-null-baseline.md` §9 and the
`convergence:` block of `config/experiments/F-E001.yaml`.
Effective config: `config/experiments/F-E001.v2.yaml`.

## Defect

The frozen v1 criterion compared per-batch metric deviations
`|m_b − m_pool|` against `4·SE_pool(m)`. Because each batch is a subset of
the pooled sample (n_b = B/4),

    Var(m_b − m_pool) = Var(m_b)·(1 − n_b/B) = 3·SE_pool(m)²

so the v1 rule was a ≈2.3σ test on the difference, not 4σ. It also asked
integer-valued quantiles (e.g. a drought length) to match within fractions
of a count, which is impossible. Result: 129 spurious metric failures
(94 statistics NOT CONVERGED) under a perfectly converged simulation.

## Correction

- **mean / variance:** `|m_b − m_pool| ≤ max(4·√3·SE_pool, atol)`
- **quantile q_p:** CDF-space bracket at the pooled quantile — pass iff
  `F_b(q_pool) ≥ p − T` and `F_b(q_pool⁻) ≤ p + T` with
  `T = 4·√3·√(p(1−p)/B)`. Robust to atoms/discrete quantiles.

## Scientific impact

None on generated output. The fair-draw streams, replicate histories,
statistic values, exact baselines, and theory-validation draws are all
unchanged — determinism probes confirm identical draws. Only the
convergence *diagnostic* is recomputed. The v1 outputs are preserved in
git history; this amendment + decision log D-003 make the change explicit.
