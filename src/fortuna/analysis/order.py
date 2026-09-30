"""P3-S011 physical draw-order omnibus and P3-S012 equipment association.

P3-S011: for draws with physical_draw_order semantics, position x label
count matrix; omnibus = max_{j,l} |z_{j,l}| with per-position marginal
uniform expectation n_ord/N. Calibrated under the ordered-draw fair null
(without-replacement within-draw dependence preserved by simulation).

P3-S012: chi-square association between an equipment category
(machine_id or ball_set_id) and main-ball labels on the populated
exploration subset, calibrated by calendar-year-blocked permutation of
equipment labels (time confounding acknowledged; no causal claim).
"""

import math
from collections import defaultdict

import numpy as np

from fortuna.simulation.engine import draw_mains_ordered
from fortuna.simulation.seeding import make_rng


def position_omnibus(ordered0: np.ndarray, n_pool: int) -> float:
    """Max |z| over (position, label) cells. ordered0 is (n_ord, K)."""
    n_ord, k = ordered0.shape
    mu = n_ord / n_pool
    sd = math.sqrt(n_ord * (1 / n_pool) * (1 - 1 / n_pool))
    if sd <= 0:
        return 0.0
    zmax = 0.0
    for j in range(k):
        c = np.bincount(ordered0[:, j], minlength=n_pool)
        zmax = max(zmax, float(np.abs(c - mu).max() / sd))
    return zmax


def order_null_replicates(
    matrix,
    n_ord: int,
    root_seed: int,
    experiment_id: str,
    batches: int,
    reps_per_batch: int,
) -> list[np.ndarray]:
    """P3-S011 null: ordered-draw replicates via dedicated ORDER streams."""
    out = []
    for b in range(1, batches + 1):
        rng = make_rng(
            root_seed, experiment_id,
            f"{matrix.game_id}|{matrix.statistical_regime_id}|ORDER|batch{b}",
        )
        vals = np.empty(reps_per_batch)
        done = 0
        while done < reps_per_batch:
            c = min(64, reps_per_batch - done)
            od = draw_mains_ordered(rng, matrix, c * n_ord).reshape(
                c, n_ord, matrix.main_count
            )
            for r in range(c):
                vals[done + r] = position_omnibus(
                    od[r] - matrix.main_min, matrix.main_pool
                )
            done += c
        out.append(vals)
    return out


# ---------------------------------------------------------------- P3-S012


def equipment_sufficiency(
    labels: list[str], min_categories: int, min_per_cat: int, min_total: int
) -> dict:
    """Sufficiency table for one equipment field on exploration draws."""
    counts: dict[str, int] = defaultdict(int)
    for lab in labels:
        if lab:
            counts[lab] += 1
    eligible = {c: n for c, n in counts.items() if n >= min_per_cat}
    n_incl = sum(eligible.values())
    return {
        "n_populated": sum(counts.values()),
        "n_categories": len(counts),
        "n_eligible_categories": len(eligible),
        "n_included_draws": n_incl,
        "categories": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "sufficient": len(eligible) >= min_categories and n_incl >= min_total,
        "included": eligible,
    }


def equipment_chi2(
    mains0: np.ndarray, labels: np.ndarray, n_pool: int, k: int
) -> float:
    """Category x label contingency chi-square (P3-S012 statistic)."""
    cats = np.unique(labels)
    n_pool_f = float(n_pool)
    t = 0.0
    for cat in cats:
        sel = mains0[labels == cat]
        n_cat = sel.shape[0]
        expected = n_cat * k / n_pool_f
        if expected <= 0:
            continue
        c = np.bincount(sel.ravel(), minlength=n_pool)
        t += float(((c - expected) ** 2 / expected).sum())
    return t


def equipment_permutation_null(
    mains0: np.ndarray,
    labels: np.ndarray,
    year_blocks: np.ndarray,
    n_pool: int,
    k: int,
    rng: np.random.Generator,
    n_perm: int,
) -> np.ndarray:
    """Time-blocked permutation null: shuffle equipment labels within
    each calendar-year block; recompute the chi-square statistic."""
    out = np.empty(n_perm)
    lab = labels.copy()
    for i in range(n_perm):
        perm = lab.copy()
        for y in np.unique(year_blocks):
            idx = np.flatnonzero(year_blocks == y)
            perm[idx] = lab[idx][rng.permutation(idx.size)]
        out[i] = equipment_chi2(mains0, perm, n_pool, k)
    return out
