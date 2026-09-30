"""Synthetic biased-history generators for F-E004 power/sensitivity tests.

Each generator produces ordered (n, K) histories that are VALID
without-replacement draws but carry a controlled injected defect. Used
only for engineering sensitivity tests and the preregistered
phase3b_sensitivity.csv power study — never for historical inference.

Effect parameters:

  delta  — position-1 (or target position) per-ball probability shift:
           boosted balls get p = (1+delta)/N at the biased position,
           remaining balls get (1 - delta*B/(N-B))/N so the marginal
           stays normalized. delta in [0, ~N/B).
  q      — probability that an injected conditional/serial dependency
           fires for a given draw/pair.
"""

import numpy as np

from fortuna.analysis.positional import _seg_bounds
from fortuna.simulation.engine import draw_mains_ordered


def _weighted_first(rng, n: int, pool: int, weights: np.ndarray) -> np.ndarray:
    """Sample position values from an arbitrary per-label weight vector."""
    cdf = np.cumsum(weights / weights.sum())
    return np.searchsorted(cdf, rng.random(n))


def inject_position_bias(
    ord_hist: np.ndarray,
    rng: np.random.Generator,
    n_pool: int,
    pos: int,
    n_boosted: int,
    delta: float,
    rows: np.ndarray | None = None,
) -> np.ndarray:
    """Scenario A/E: bias one physical position toward ``n_boosted``
    low-label balls while preserving valid without-replacement draws.

    Rows are drawn as: biased position gets a weighted sample; remaining
    positions are filled by a uniform ordered (K-1)-permutation of the
    remaining labels (columns other than ``pos`` are overwritten in a
    consistent way — the row is rebuilt entirely).
    """
    n, k = ord_hist.shape
    rows = np.arange(n) if rows is None else rows
    w = np.full(n_pool, (1.0 - delta * n_boosted / (n_pool - n_boosted))
                / n_pool)
    w[:n_boosted] = (1.0 + delta) / n_pool
    biased = _weighted_first(rng, len(rows), n_pool, w)
    # remaining positions: uniform ordered subset of the leftover labels
    keys = rng.random((len(rows), n_pool))
    keys[np.arange(len(rows)), biased] = np.inf
    rest = np.argsort(keys, axis=1)[:, : k - 1]  # labels in draw order
    out = ord_hist.copy()
    cols = [c for c in range(k) if c != pos]
    out[np.ix_(rows, cols)] = rest
    out[rows, pos] = biased
    return out


def inject_conditional_bias(
    ord_hist: np.ndarray,
    rng: np.random.Generator,
    n_pool: int,
    q: float,
    src_pos: int = 0,
    dst_pos: int = 1,
) -> np.ndarray:
    """Scenario B: with prob q set X_dst = successor of X_src (within
    the same draw), swap-restoring validity if the label already occurs
    at another position of that draw. Keeps per-position marginals
    approximately uniform while adding within-draw dependence beyond
    the fair no-replacement relationship.
    """
    out = ord_hist.copy()
    n, k = out.shape
    fire = rng.random(n) < q
    tgt = (out[fire, src_pos] + 1) % n_pool
    rows = np.flatnonzero(fire)
    for r, v in zip(rows, tgt, strict=True):
        row = out[r]
        if row[dst_pos] == v:
            continue
        m = int(np.argmax(row == v)) if (row == v).any() else -1
        if m >= 0:                        # swap to keep the same set
            row[dst_pos], row[m] = v, row[dst_pos]
        else:                             # label absent: replace dst
            row[dst_pos] = v
    return out


def inject_serial_bias(
    ord_hist: np.ndarray,
    rng: np.random.Generator,
    n_pool: int,
    seg_lengths: list[int],
    lag: int,
    src_pos: int,
    dst_pos: int,
    q: float,
) -> np.ndarray:
    """Scenarios C/D: with prob q set X_dst,t+lag = X_src,t for
    within-segment pairs (swap-restoring validity within the target
    draw). Source values are read from the ORIGINAL history.
    """
    out = ord_hist.copy()
    for s, e in _seg_bounds(seg_lengths):
        if e - s <= lag:
            continue
        t = np.arange(s, e - lag)
        fire = rng.random(t.size) < q
        src_t, dst_t = t[fire], t[fire] + lag
        vals = out[src_t, src_pos].copy()
        for tt, v in zip(dst_t, vals, strict=True):
            row = out[tt]
            if row[dst_pos] == v:
                continue
            m = int(np.argmax(row == v)) if (row == v).any() else -1
            if m >= 0:
                row[dst_pos], row[m] = v, row[dst_pos]
            else:
                row[dst_pos] = v
    return out


def make_history(
    rng: np.random.Generator,
    matrix,
    n_ord: int,
    seg_lengths: list[int],
    scenario: str,
    effect: float,
) -> np.ndarray:
    """One biased ordered history for a named scenario.

    Scenarios (frozen in F-E004):
      A position1_bias       — delta shift on position 1
      B conditional_bias     — q: X2 = succ(X1) within draw
      C serial_same_pos      — q: X1,t+1 = X1,t
      D serial_cross_pos     — q: X1,t+1 = XK,t
      E temporal_position    — delta on position 1 inside one window
      F fair                 — no injection (effect ignored)
    """
    k = matrix.main_count
    hist = draw_mains_ordered(rng, matrix, n_ord) - matrix.main_min
    if scenario == "fair":
        return hist
    if scenario == "position1_bias":
        n_boosted = max(1, matrix.main_pool // 10)
        return inject_position_bias(
            hist, rng, matrix.main_pool, 0, n_boosted, effect
        )
    if scenario == "conditional_bias":
        return inject_conditional_bias(hist, rng, matrix.main_pool, effect)
    if scenario == "serial_same_pos":
        return inject_serial_bias(
            hist, rng, matrix.main_pool, seg_lengths, 1, 0, 0, effect
        )
    if scenario == "serial_cross_pos":
        return inject_serial_bias(
            hist, rng, matrix.main_pool, seg_lengths, 1, k - 1, 0, effect
        )
    if scenario == "temporal_position":
        bounds = _seg_bounds(seg_lengths)
        s, e = max(bounds, key=lambda be: be[1] - be[0])
        w = min(250, e - s)
        rows = np.arange(s, s + w)
        n_boosted = max(1, matrix.main_pool // 10)
        return inject_position_bias(
            hist, rng, matrix.main_pool, 0, n_boosted, effect, rows
        )
    raise ValueError(f"unknown scenario {scenario}")


SCENARIO_STATS = {
    "position1_bias": ("P3B-S001", "P3B-S002"),
    "conditional_bias": ("P3B-S004", "P3B-S006"),
    "serial_same_pos": ("P3B-S007",),
    "serial_cross_pos": ("P3B-S008",),
    "temporal_position": ("P3B-S009",),
}
