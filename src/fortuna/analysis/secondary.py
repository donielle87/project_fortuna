"""Phase 3 secondary history-level statistics P3-S001..P3-S010.

Frozen definitions live in config/experiments/F-E002.yaml and the F-E002
preregistration. Every statistic is evaluated per replicate fair history
(and once on the observed exploration history); sequential quantities
never bridge exploration-segment boundaries.

Notation: ``mains0`` is (n, K) zero-based sorted main-ball labels;
``seg_slices`` is a list of (start, end) index pairs from
``fortuna.simulation.statistics._segment_slices``.
"""

import math
from itertools import combinations

import numpy as np

from fortuna.simulation.statistics import _segment_slices

# ---------------------------------------------------------------- P3-S001


def max_triple_cooccurrence(mains0: np.ndarray, n_pool: int) -> float:
    """Maximum over all C(N,3) triples of co-occurrence count (P3-S001)."""
    k = mains0.shape[1]
    cols = [
        mains0[:, i] * n_pool * n_pool + mains0[:, j] * n_pool + mains0[:, t]
        for i, j, t in combinations(range(k), 3)
    ]
    ids = np.concatenate(cols)
    return float(np.bincount(ids, minlength=n_pool**3).max())


def argmax_triples(mains0: np.ndarray, n_pool: int) -> tuple[int, list]:
    """Observed max triple count and the (1-based) triples attaining it."""
    k = mains0.shape[1]
    cols = [
        mains0[:, i] * n_pool * n_pool + mains0[:, j] * n_pool + mains0[:, t]
        for i, j, t in combinations(range(k), 3)
    ]
    ids = np.concatenate(cols)
    cnt = np.bincount(ids, minlength=n_pool**3)
    mx = int(cnt.max())
    triples = []
    for t in np.flatnonzero(cnt == mx):
        a, rem = divmod(int(t), n_pool * n_pool)
        b, c = divmod(rem, n_pool)
        triples.append((a + 1, b + 1, c + 1))
    return mx, sorted(triples)


# ---------------------------------------------------------------- P3-S002


def lagged_overlap_scan(
    mains0: np.ndarray,
    segment_lengths: list[int],
    lags: tuple[int, ...],
    overlap_mean: float,
    overlap_var: float,
) -> dict[int, dict[str, float]]:
    """Per-lag standardized overlap aggregate (P3-S002 components).

    For lag L: S_L = sum of |D_t cap D_{t+L}| over within-segment pairs;
    z_L = (S_L - n_L * mu) / sqrt(n_L * var). Pairs never cross segment
    boundaries.
    """
    n = mains0.shape[0]
    seg_idx = np.concatenate([[0], np.cumsum(segment_lengths)[:-1]])
    slices = _segment_slices(n, seg_idx)
    out: dict[int, dict[str, float]] = {}
    for lag in lags:
        s_total, n_pairs = 0, 0
        for s, e in slices:
            if e - s > lag:
                ov = (
                    mains0[s : e - lag, :, None] == mains0[s + lag : e, None, :]
                ).any(axis=2).sum(axis=1)
                s_total += int(ov.sum())
                n_pairs += int(ov.size)
        if n_pairs > 0 and overlap_var > 0:
            z = (s_total - n_pairs * overlap_mean) / math.sqrt(
                n_pairs * overlap_var
            )
        else:
            z = 0.0
        out[lag] = {"aggregate": float(s_total), "n_pairs": n_pairs, "z": z}
    return out


def p3s002(
    mains0: np.ndarray,
    segment_lengths: list[int],
    lags: tuple[int, ...],
    overlap_mean: float,
    overlap_var: float,
) -> float:
    """Max |z| over the lag aggregates (P3-S002)."""
    res = lagged_overlap_scan(
        mains0, segment_lengths, lags, overlap_mean, overlap_var
    )
    return float(max(abs(v["z"]) for v in res.values()))


# ---------------------------------------------------------------- P3-S003


def terminal_drought(m: np.ndarray, segment_lengths: list[int]) -> float:
    """Max trailing absence run at the end of the LAST exploration segment.

    ``m`` is the (n, N) boolean membership matrix. The run counts
    consecutive absent draws at the segment end per ball (0 when the ball
    appeared in the final draw); max over balls.
    """
    n = m.shape[0]
    seg_idx = np.concatenate([[0], np.cumsum(segment_lengths)[:-1]])
    s, e = _segment_slices(n, seg_idx)[-1]
    seg = m[s:e]
    n_seg = e - s
    idx = np.arange(n_seg)[:, None]
    last_true = np.maximum.accumulate(np.where(seg, idx, -1), axis=0)
    trailing = (n_seg - 1) - last_true[-1]
    return float(trailing.max())


def terminal_drought_by_ball(
    m: np.ndarray, segment_lengths: list[int]
) -> np.ndarray:
    """Per-ball trailing absence run at the last exploration segment end."""
    n = m.shape[0]
    seg_idx = np.concatenate([[0], np.cumsum(segment_lengths)[:-1]])
    s, e = _segment_slices(n, seg_idx)[-1]
    seg = m[s:e]
    n_seg = e - s
    idx = np.arange(n_seg)[:, None]
    last_true = np.maximum.accumulate(np.where(seg, idx, -1), axis=0)
    return (n_seg - 1) - last_true[-1]


# ---------------------------------------------------------------- P3-S004


def rolling_scan(
    m: np.ndarray,
    segment_lengths: list[int],
    windows: tuple[int, ...],
    inclusion_p: float,
) -> float:
    """Max |standardized rolling-window frequency deviation| (P3-S004).

    For each window length w, each within-segment window position, and
    each main-ball label: z = (c - w*p) / sqrt(w*p*(1-p)). A window is
    used only when w <= segment length.
    """
    n = m.shape[0]
    seg_idx = np.concatenate([[0], np.cumsum(segment_lengths)[:-1]])
    p = inclusion_p
    zmax = 0.0
    for s, e in _segment_slices(n, seg_idx):
        n_seg = e - s
        mem = m[s:e].astype(np.float64)
        cs = np.vstack([np.zeros((1, mem.shape[1])), np.cumsum(mem, axis=0)])
        for w in windows:
            if w > n_seg:
                continue
            sums = cs[w:] - cs[:-w]
            z = np.abs(sums - w * p) / math.sqrt(w * p * (1 - p))
            zmax = max(zmax, float(z.max()))
    return zmax


# -------------------------------------------------------- P3-S005..S010


def cvm_discrepancy(empirical: np.ndarray, ref_pmf: dict[float, float]) -> float:
    """Frozen discrete Cramer-von Mises discrepancy (P3-S005..S010).

    T = sum_x p0(x) * (F_emp(x) - F0(x))^2 over the reference support x.
    """
    xs = np.array(sorted(ref_pmf), dtype=float)
    p0 = np.array([ref_pmf[x] for x in xs], dtype=float)
    f0 = np.cumsum(p0)
    emp = np.sort(np.asarray(empirical, dtype=float))
    f_emp = np.searchsorted(emp, xs, side="right") / emp.size
    return float((p0 * (f_emp - f0) ** 2).sum())


def per_draw_quantities(mains: np.ndarray) -> dict[str, np.ndarray]:
    """Per-draw structural quantities for the discrepancy tests."""
    diffs = np.diff(mains, axis=1)
    return {
        "draw_sum": mains.sum(axis=1).astype(float),
        "range": (mains[:, -1] - mains[:, 0]).astype(float),
        "adjacent_pair_count": (diffs == 1).sum(axis=1).astype(float),
        "min_spacing": diffs.min(axis=1).astype(float),
        "max_spacing": diffs.max(axis=1).astype(float),
        "odd_count": (mains % 2 == 1).sum(axis=1).astype(float),
    }


STRUCTURAL_TESTS = {
    "P3-S005": "draw_sum",
    "P3-S006": "range",
    "P3-S007": "adjacent_pair_count",
    "P3-S008": "min_spacing",
    "P3-S009": "max_spacing",
    "P3-S010": "odd_count",
}


def p3_history_statistics(
    mains: np.ndarray,
    matrix,
    segment_lengths: list[int],
    lags: tuple[int, ...],
    overlap_mean: float,
    overlap_var: float,
    windows: tuple[int, ...],
    ref_pmfs: dict[str, dict[float, float]],
) -> dict[str, float]:
    """All history-level secondary statistics for one history.

    ``mains`` are actual ball labels (sorted per row). ``ref_pmfs`` maps
    quantity name -> reference null pmf (exact or simulated reference).
    """
    mains0 = mains - matrix.main_min
    n = mains0.shape[0]
    m = np.zeros((n, matrix.main_pool), dtype=bool)
    np.put_along_axis(m, mains0, True, axis=1)

    out = {
        "P3-S001": max_triple_cooccurrence(mains0, matrix.main_pool),
        "P3-S002": p3s002(
            mains0, segment_lengths, lags, overlap_mean, overlap_var
        ),
        "P3-S003": terminal_drought(m, segment_lengths),
        "P3-S004": rolling_scan(
            m, segment_lengths, windows, matrix.main_count / matrix.main_pool
        ),
    }
    quants = per_draw_quantities(mains)
    for sid, qname in STRUCTURAL_TESTS.items():
        out[sid] = cvm_discrepancy(quants[qname], ref_pmfs[qname])
    return out


HISTORY_SECONDARY = (
    "P3-S001", "P3-S002", "P3-S003", "P3-S004",
    "P3-S005", "P3-S006", "P3-S007", "P3-S008", "P3-S009", "P3-S010",
)
