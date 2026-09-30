"""Single-draw structural null distributions (Task 7).

Exact distributions via DP/enumeration where practical:
    draw_sum, range, odd_count, adjacent_overlap, no-consecutive flag.

Simulated (labeled ``simulated``) where exact enumeration is impractical:
    adjacent_pair_count, min_spacing, max_spacing,
    consecutive_value_occurrence (count of adjacent runs >= 2).

No historical draws are used anywhere.
"""

import numpy as np

from fortuna.simulation import exact
from fortuna.simulation.engine import draw_mains
from fortuna.simulation.matrix import RegimeMatrix

EXACT_STRUCTURAL = ("draw_sum", "range", "odd_count", "adjacent_overlap",
                    "has_consecutive_pair")
SIMULATED_STRUCTURAL = ("adjacent_pair_count", "min_spacing", "max_spacing",
                        "consecutive_run_count")


def structural_exact(matrix: RegimeMatrix) -> dict[str, dict[float, float]]:
    """Exact pmfs (value -> probability) for the exact structural stats."""
    lo, hi, k, n = matrix.main_min, matrix.main_max, matrix.main_count, matrix.main_pool
    pmfs: dict[str, dict[float, float]] = {
        "draw_sum": {float(s): p for s, p in exact.sum_pmf(lo, hi, k).items()},
        "range": {float(r): p for r, p in exact.range_pmf(lo, hi, k).items()},
        "odd_count": {float(j): float(p) for j, p in enumerate(
            exact.odd_even_pmf(lo, hi, k))},
        "adjacent_overlap": {float(j): float(p) for j, p in enumerate(
            exact.overlap_pmf(n, k))},
        "has_consecutive_pair": {
            0.0: exact.no_consecutive_prob(n, k),
            1.0: 1 - exact.no_consecutive_prob(n, k),
        },
    }
    return pmfs


def _spacings(draw0: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-draw: (adjacent pair count, min spacing, max spacing, run count).

    ``draw0`` is (n, K) sorted values; spacing = consecutive differences.
    """
    diffs = np.diff(draw0, axis=1)
    adj_pairs = (diffs == 1).sum(axis=1)
    min_sp = diffs.min(axis=1)
    max_sp = diffs.max(axis=1)
    # number of consecutive-value runs >= 2: count starts of (diff==1) blocks
    ones = diffs == 1
    starts = ones & ~np.concatenate(
        [np.zeros((draw0.shape[0], 1), dtype=bool), ones[:, :-1]], axis=1
    )
    run_count = starts.sum(axis=1)
    return adj_pairs, min_sp, max_sp, run_count


def structural_simulated(
    rng: np.random.Generator, matrix: RegimeMatrix, n_draws: int
) -> dict[str, dict[float, float]]:
    """Simulated pmfs for spacing-type structural stats (labeled as such)."""
    draws = draw_mains(rng, matrix, n_draws)
    adj, mn, mx, runs = _spacings(draws)
    out: dict[str, dict[float, float]] = {}
    for name, arr in (
        ("adjacent_pair_count", adj),
        ("min_spacing", mn),
        ("max_spacing", mx),
        ("consecutive_run_count", runs),
    ):
        vals, cnt = np.unique(arr, return_counts=True)
        out[name] = {
            float(v): float(c) / n_draws for v, c in zip(vals, cnt, strict=True)
        }
    return out


def summarize_pmf(pmf: dict[float, float]) -> dict[str, float]:
    """Mean/variance/min/max of a value -> probability map."""
    vals = np.array(list(pmf.keys()))
    probs = np.array(list(pmf.values()))
    mu = float((vals * probs).sum())
    var = float(((vals - mu) ** 2 * probs).sum())
    return {"mean": mu, "var": var, "min": float(vals.min()), "max": float(vals.max())}
