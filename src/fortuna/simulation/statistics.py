"""History-level statistic catalog F-S001..F-S013 (frozen in F-E001).

Definitions are per replicate *fair history*. ``mains`` is an (n, K) array
of sorted main-ball labels; ``specials`` an (n,) array or None. Sequential
statistics take ``seg_starts`` — indices where a new contiguous eligible
segment begins (index 0 always included); statistics never bridge those
positions.

No statistic in the catalog is order-sensitive: all treat each draw as a
set. Order-dependent analyses are deferred to a later, separately
registered experiment.
"""

import math
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from fortuna.simulation.matrix import RegimeMatrix


@dataclass(frozen=True)
class StatisticSpec:
    statistic_id: str
    name: str
    sequential: bool       # must respect contiguous-segment boundaries
    needs_special: bool    # requires a special-ball mechanism
    description: str


CATALOG: dict[str, StatisticSpec] = {
    "F-S001": StatisticSpec("F-S001", "main_frequency_dispersion", False, False,
                            "chi-square: sum_i (c_i - n p)^2 / (n p)"),
    "F-S002": StatisticSpec("F-S002", "max_abs_standardized_main_freq", False, False,
                            "max_i |c_i - n p| / sqrt(n p (1-p))"),
    "F-S003": StatisticSpec("F-S003", "max_main_occurrence", False, False,
                            "max_i c_i"),
    "F-S004": StatisticSpec("F-S004", "min_main_occurrence", False, False,
                            "min_i c_i"),
    "F-S005": StatisticSpec("F-S005", "max_pair_cooccurrence", False, False,
                            "max over all C(N,2) fixed pairs of co-occurrence count"),
    "F-S006": StatisticSpec("F-S006", "adjacent_overlap_aggregate", True, False,
                            "sum over within-segment adjacent pairs of |D_t cap D_t+1|"),
    "F-S007": StatisticSpec("F-S007", "max_drought", True, False,
                            "longest within-segment run absent a number, max over numbers"),
    "F-S008": StatisticSpec("F-S008", "max_streak", True, False,
                            "longest within-segment run containing a number, max over numbers"),
    "F-S009": StatisticSpec("F-S009", "special_frequency_dispersion", False, True,
                            "chi-square over M special-ball counts"),
    "F-S010": StatisticSpec("F-S010", "max_abs_standardized_special_freq", False, True,
                            "max_j |s_j - n/M| / sqrt(n (1/M)(1-1/M))"),
    "F-S011": StatisticSpec("F-S011", "special_consecutive_repeats", True, True,
                            "count of within-segment adjacent equal special balls"),
    "F-S012": StatisticSpec("F-S012", "draw_sum_dispersion", False, False,
                            "sample variance (ddof=1) of per-draw main sums"),
    "F-S013": StatisticSpec("F-S013", "odd_even_dispersion", False, False,
                            "sample variance (ddof=1) of per-draw odd-ball counts"),
}


def segment_start_mask(n: int, segment_lengths: list[int]) -> np.ndarray:
    """Boolean (n,) mask, True at the first draw index of each segment."""
    if sum(segment_lengths) != n:
        raise ValueError("segment lengths must sum to n_draws")
    mask = np.zeros(n, dtype=bool)
    pos = 0
    for length in segment_lengths:
        mask[pos] = True
        pos += length
    return mask


def adjacent_pair_mask(seg_starts: np.ndarray) -> np.ndarray:
    """(n-1,) mask: True where positions t and t+1 are in one segment."""
    return ~seg_starts[1:]


def membership(mains0: np.ndarray, n_pool: int) -> np.ndarray:
    """(n, N) boolean presence matrix for zero-based main values."""
    m = np.zeros((mains0.shape[0], n_pool), dtype=bool)
    np.put_along_axis(m, mains0, True, axis=1)
    return m


def _counts(mains0: np.ndarray, n_pool: int) -> np.ndarray:
    return np.bincount(mains0.ravel(), minlength=n_pool).astype(np.int64)


def _frequency_stats(mains0: np.ndarray, matrix: RegimeMatrix) -> dict[str, float]:
    n = mains0.shape[0]
    n_pool, k = matrix.main_pool, matrix.main_count
    c = _counts(mains0, n_pool)
    p = k / n_pool
    mu = n * p
    chi2 = float(((c - mu) ** 2).sum() / mu)
    z = np.abs(c - mu) / math.sqrt(mu * (1 - p))
    return {
        "F-S001": chi2,
        "F-S002": float(z.max()),
        "F-S003": float(c.max()),
        "F-S004": float(c.min()),
    }


def _max_pair(mains0: np.ndarray, n_pool: int) -> float:
    k = mains0.shape[1]
    cols = [mains0[:, i] * n_pool + mains0[:, j]
            for i, j in combinations(range(k), 2)]
    pids = np.concatenate(cols)
    return float(np.bincount(pids, minlength=n_pool * n_pool).max())


def _overlaps(mains0: np.ndarray) -> np.ndarray:
    """|D_t ∩ D_t+1| for every adjacent pair, shape (n-1,)."""
    return (mains0[:-1, :, None] == mains0[1:, None, :]).any(axis=2).sum(axis=1)


def _max_false_run(m: np.ndarray, seg_starts: np.ndarray) -> int:
    """Longest absence run per column, confined to segments."""
    md = m.copy()
    md[seg_starts] = True
    n = m.shape[0]
    idx = np.arange(n)[:, None]
    last_true = np.maximum.accumulate(np.where(md, idx, -1), axis=0)
    return int((idx - last_true).max())


def _max_true_run(m: np.ndarray, seg_starts: np.ndarray) -> int:
    """Longest presence run per column, confined to segments."""
    ms = m.copy()
    ms[seg_starts] = False
    n = m.shape[0]
    idx = np.arange(n)[:, None]
    last_false = np.maximum.accumulate(np.where(~ms, idx, -1), axis=0)
    return int((idx - last_false).max())


def history_statistics(
    mains: np.ndarray,
    specials: np.ndarray | None,
    matrix: RegimeMatrix,
    segment_lengths: list[int],
) -> dict[str, float]:
    """Compute every applicable catalog statistic for one replicate history.

    ``mains`` are actual ball labels (main_min..main_max), sorted per row.
    """
    mains0 = mains - matrix.main_min
    n = mains0.shape[0]
    seg_mask = segment_start_mask(n, segment_lengths)
    seg_idx = np.flatnonzero(seg_mask)
    adj_ok = adjacent_pair_mask(seg_mask)
    out = _frequency_stats(mains0, matrix)

    out["F-S005"] = _max_pair(mains0, matrix.main_pool)

    ov = _overlaps(mains0)
    out["F-S006"] = float(ov[adj_ok].sum())

    m = membership(mains0, matrix.main_pool)
    out["F-S007"] = float(_max_false_run(m, seg_idx))
    out["F-S008"] = float(_max_true_run(m, seg_idx))

    if matrix.has_special and specials is not None:
        s0 = specials - matrix.special_min
        pool = matrix.special_pool
        mu = n / pool
        sc = np.bincount(s0, minlength=pool).astype(np.int64)
        out["F-S009"] = float(((sc - mu) ** 2).sum() / mu)
        out["F-S010"] = float(
            (np.abs(sc - mu) / math.sqrt(mu * (1 - 1 / pool))).max()
        )
        out["F-S011"] = float(((s0[:-1] == s0[1:]) & adj_ok).sum())

    out["F-S012"] = float(mains.sum(axis=1).var(ddof=1))
    odd_counts = (mains % 2 == 1).sum(axis=1)
    out["F-S013"] = float(odd_counts.var(ddof=1))
    return out


def applicable_statistics(matrix: RegimeMatrix) -> list[str]:
    """Catalog ids applicable to this regime (special stats need a special)."""
    return [
        sid for sid, spec in CATALOG.items()
        if not spec.needs_special or matrix.has_special
    ]
