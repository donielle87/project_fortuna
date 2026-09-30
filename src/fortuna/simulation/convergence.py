"""Frozen F-E001 convergence diagnostics.

For each (regime, statistic): the four 5,000-replicate batch estimates of
{mean, variance, q90, q95, q99} are compared against the pooled 20,000-
replicate estimate.

    CONVERGED iff for every metric m:
        max_b |m_b - m_pool| <= max(4 * se_pool(m), 1e-6 * max(1, |m_pool|))

A failed check is reported NOT CONVERGED — never relabeled.
"""

import math
from dataclasses import dataclass, field

import numpy as np

METRICS = ("mean", "var", "q90", "q95", "q99")
_QS = {"q90": 0.90, "q95": 0.95, "q99": 0.99}


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


def _se_quantile(pooled: np.ndarray, p: float) -> float:
    """Quantile SE via order-statistic spacing density estimate."""
    x = np.sort(pooled)
    b = x.size
    i = int(round(p * (b - 1)))
    j = max(1, int(round(b ** 0.6)))
    lo, hi = max(0, i - j), min(b - 1, i + j)
    width = x[hi] - x[lo]
    if width <= 0:
        return 0.0  # degenerate region: quantile is pinned by mass
    f_hat = (hi - lo) / (b * width)
    return math.sqrt(p * (1 - p)) / (f_hat * math.sqrt(b))


def check_convergence(
    batches: list[np.ndarray],
    sigma_factor: float = 4.0,
    atol_rel: float = 1e-6,
) -> ConvergenceResult:
    """Apply the frozen criterion to the 4 batch arrays of one statistic."""
    pooled = np.concatenate(batches)
    res = ConvergenceResult(status="CONVERGED")
    for metric in METRICS:
        m_pool = _metric_value(pooled, metric)
        bvals = [_metric_value(np.asarray(b), metric) for b in batches]
        max_dev = max(abs(v - m_pool) for v in bvals)
        if metric == "mean":
            se = _se_mean(pooled)
        elif metric == "var":
            se = _se_var(pooled)
        else:
            se = _se_quantile(pooled, _QS[metric])
        atol = atol_rel * max(1.0, abs(m_pool))
        passed = max_dev <= max(sigma_factor * se, atol)
        if not passed:
            res.status = "NOT CONVERGED"
        res.metrics.append(
            MetricResult(metric, m_pool, bvals, max_dev, se, atol, passed)
        )
    return res
