"""Theory-to-simulation validation for F-E001.

Per statistical regime, 200,000 fair draws are generated on a dedicated
VALIDATION child stream and compared against exact theory. Checks use the
frozen 5-sigma Monte Carlo tolerance. No historical draws are involved.
"""

import math
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np

from fortuna.simulation import exact
from fortuna.simulation.engine import draw_mains, draw_specials
from fortuna.simulation.matrix import RegimeMatrix
from fortuna.simulation.seeding import make_rng

SIGMA = 5.0


@dataclass
class Check:
    name: str
    observed: float
    expected: float
    se: float
    z: float
    passed: bool


@dataclass
class RegimeValidation:
    statistical_regime_id: str
    draws: int
    checks: list[Check] = field(default_factory=list)
    status: str = "PASS"

    def add(self, name: str, obs: float, exp: float, se: float) -> None:
        z = abs(obs - exp) / se if se > 0 else (0.0 if abs(obs - exp) == 0 else math.inf)
        ok = abs(obs - exp) <= SIGMA * se if se > 0 else abs(obs - exp) < 1e-12
        self.checks.append(Check(name, obs, exp, se, z, ok))
        if not ok:
            self.status = "FAIL"


def _z_se(p: float, b: int) -> float:
    return math.sqrt(p * (1 - p) / b)


def _subset(size: int, cap: int = 512) -> np.ndarray:
    """Deterministic evenly-spaced subset of indices 0..size-1.

    Worst-cell checks over thousands of marginally-binomial cells would
    exceed the frozen 5-sigma tolerance by chance alone; the check is
    applied to a fixed subset chosen before any simulation ran."""
    if size <= cap:
        return np.arange(size)
    step = size / cap
    return np.unique(np.floor(np.arange(cap) * step).astype(int))


def validate_regime(
    matrix: RegimeMatrix,
    root_seed: int,
    experiment_id: str,
    n_draws: int = 200_000,
) -> RegimeValidation:
    scope = f"{matrix.game_id}|{matrix.statistical_regime_id}|VALIDATION"
    rng = make_rng(root_seed, experiment_id, scope)
    mains_labels = draw_mains(rng, matrix, n_draws)
    mains = mains_labels - matrix.main_min
    n, k, n_pool = n_draws, matrix.main_count, matrix.main_pool
    res = RegimeValidation(matrix.statistical_regime_id, n)

    # --- marginal inclusion: worst main label ---
    p = k / n_pool
    counts = np.bincount(mains.ravel(), minlength=n_pool) / n
    worst = int(np.abs(counts - p).argmax())
    res.add("inclusion_prob", float(counts[worst]), p, _z_se(p, n))

    # --- fixed-pair co-occurrence: deterministic subset of all pairs ---
    p2 = exact.pair_prob(n_pool, k)
    cols = [mains[:, i] * n_pool + mains[:, j] for i, j in combinations(range(k), 2)]
    pc = np.bincount(np.concatenate(cols), minlength=n_pool * n_pool) / n
    pair_freqs = pc.reshape(n_pool, n_pool)[np.triu_indices(n_pool, 1)]
    pair_freqs = pair_freqs[_subset(pair_freqs.size)]
    worst_p = int(np.abs(pair_freqs - p2).argmax())
    res.add("pair_prob", float(pair_freqs[worst_p]), p2, _z_se(p2, n))

    # --- fixed triples: deterministic subset of all realizable triples ---
    if k >= 3:
        p3 = exact.triple_prob(n_pool, k)
        tcols = [
            mains[:, i] * n_pool * n_pool + mains[:, j] * n_pool + mains[:, t]
            for i, j, t in combinations(range(k), 3)
        ]
        tc = np.bincount(np.concatenate(tcols), minlength=n_pool**3) / n
        trip_ids = np.array(
            [a * n_pool * n_pool + b * n_pool + c
             for a, b, c in combinations(range(n_pool), 3)]
        )
        trip_freqs = tc[trip_ids[_subset(trip_ids.size)]]
        worst_t = int(np.abs(trip_freqs - p3).argmax())
        res.add("triple_prob", float(trip_freqs[worst_t]), p3, _z_se(p3, n))

    # --- overlap distribution: independent non-overlapping pairs ---
    pmf = exact.overlap_pmf(n_pool, k)
    m = np.zeros((n, n_pool), dtype=bool)
    np.put_along_axis(m, mains, True, axis=1)
    half = 2 * (n // 2)
    pairs = (m[0:half:2] & m[1:half:2]).sum(axis=1)
    obs_pmf = np.bincount(pairs, minlength=k + 1) / pairs.size
    worst_o = int(np.abs(obs_pmf - pmf).argmax())
    res.add(
        "overlap_pmf_worst_cell",
        float(obs_pmf[worst_o]),
        float(pmf[worst_o]),
        _z_se(float(pmf[worst_o]), pairs.size),
    )

    # --- odd/even composition (labels, not zero-based indices) ---
    oe = exact.odd_even_pmf(matrix.main_min, matrix.main_max, k)
    odd_counts = (mains_labels % 2 == 1).sum(axis=1)
    obs_oe = np.bincount(odd_counts, minlength=k + 1) / n
    worst_e = int(np.abs(obs_oe - oe).argmax())
    res.add(
        "odd_even_worst_cell",
        float(obs_oe[worst_e]),
        float(oe[worst_e]),
        _z_se(float(oe[worst_e]), n),
    )

    # --- special ball ---
    if matrix.has_special:
        specials = draw_specials(rng, matrix, n)
        assert specials is not None
        s0 = specials - matrix.special_min
        pool = matrix.special_pool
        sc = np.bincount(s0, minlength=pool) / n
        worst_s = int(np.abs(sc - 1 / pool).argmax())
        res.add("special_freq", float(sc[worst_s]), 1 / pool, _z_se(1 / pool, n))
        obs_rep = float((s0[0:half:2] == s0[1:half:2]).mean())
        res.add("special_repeat", obs_rep, 1 / pool, _z_se(1 / pool, n // 2))

    return res
