"""Frozen F-E001 convergence diagnostics (v2 — decision D-003).

For each (regime, statistic): the four 5,000-replicate batch estimates of
{mean, variance, q90, q95, q99} are compared against the pooled 20,000-
replicate estimate.

v1 defect (documented, superseded): the frozen text compared batch-pooled
deviations to ``4 * se_pool``.  Var(m_b - m_pool) = 3 * se_pool^2 for
n_b = B/4, so the v1 rule is a ~2.3-sigma test on the difference, not a
4-sigma test, and it cannot represent discrete quantile granularity at
all.  v2 corrects the SE of the batch-minus-pooled difference and moves
quantile checks into CDF space (robust to integer-valued statistics).

v2 criterion:

  - mean / variance:
        |m_b - m_pool| <= max(4 * sqrt(3) * se_pool(m), atol)
  - quantile q_p (p in {0.90, 0.95, 0.99}):
        for each batch b, let F_b be its empirical CDF at the pooled
        quantile value q_pool; pass iff
            F_b(q_pool)   >= p - T   AND   F_b(q_pool-)  <= p + T
        with T = 4 * sqrt(3) * sqrt(p(1-p) / B)
        (the bracket handles atoms/discrete quantiles correctly)

A failed check is reported NOT CONVERGED — never relabeled.
"""

import math
from dataclasses import dataclass, field

import numpy as np

METRICS = ("mean", "var", "q90", "q95", "q99")
_QS = {"q90": 0.90, "q95": 0.95, "q99": 0.99}
_SQRT3 = math.sqrt(3.0)


@dataclass
class MetricResult:
    metric: str
    pooled: float
    batch_values: list[float]
    max_dev: float
    se: float
    atol: float
    passed: bool


@dataclass
class ConvergenceResult:
    status: str                      # CONVERGED | NOT CONVERGED
    metrics: list[MetricResult] = field(default_factory=list)


def _metric_value(x: np.ndarray, metric: str) -> float:
    if metric == "mean":
        return float(x.mean())
    if metric == "var":
        return float(x.var())
    return float(np.quantile(x, _QS[metric]))


def _se_mean(pooled: np.ndarray) -> float:
    return float(pooled.std(ddof=1) / math.sqrt(pooled.size))


def _se_var(pooled: np.ndarray) -> float:
    v = float(pooled.var())
    mu4 = float(((pooled - pooled.mean()) ** 4).mean())
    return math.sqrt(max(mu4 - v * v, 0.0) / pooled.size)


def check_convergence(
    batches: list[np.ndarray],
    sigma_factor: float = 4.0,
    atol_rel: float = 1e-6,
) -> ConvergenceResult:
    """Apply the corrected (v2) criterion to the batch arrays of one stat."""
    pooled = np.concatenate(batches)
    res = ConvergenceResult(status="CONVERGED")
    for metric in METRICS:
        m_pool = _metric_value(pooled, metric)
        bvals = [_metric_value(np.asarray(b), metric) for b in batches]
        max_dev = max(abs(v - m_pool) for v in bvals)
        atol = atol_rel * max(1.0, abs(m_pool))
        if metric == "mean":
            se = _se_mean(pooled)
            tol = max(sigma_factor * _SQRT3 * se, atol)
            passed = max_dev <= tol
        elif metric == "var":
            se = _se_var(pooled)
            tol = max(sigma_factor * _SQRT3 * se, atol)
            passed = max_dev <= tol
        else:
            # CDF-space bracket test at the pooled quantile (v2)
            p = _QS[metric]
            t = sigma_factor * _SQRT3 * math.sqrt(p * (1 - p) / pooled.size)
            se = t / sigma_factor  # store the diff-space SE for reporting
            passed = True
            for b in batches:
                b_arr = np.asarray(b)
                f_le = float((b_arr <= m_pool).mean())
                f_lt = float((b_arr < m_pool).mean())
                if f_le < p - t or f_lt > p + t:
                    passed = False
            tol = t
        if not passed:
            res.status = "NOT CONVERGED"
        res.metrics.append(
            MetricResult(metric, m_pool, bvals, max_dev, se, atol, passed)
        )
    return res
