"""F-E004 Phase 3B Monte Carlo runner — fair SEQUENTIAL null.

Unlike F-E002/F-E003 (sorted-set histories), Phase 3B replicates are
uniform ORDERED K-permutations — one sequential without-replacement
mechanism per draw, position order preserved. All P3B statistics within
a regime share the same replicate ordered histories (one deterministic
``<game>|<stat_regime>|P3B_HISTORIES|batch<b>`` stream per batch), so
every statistic's null contains the exact fair within-draw dependence.

Cross-draw statistics use the same contiguous physical-order segment
lengths as the observed exploration history and never bridge a break.
"""

import hashlib

import numpy as np

from fortuna.analysis.positional import MC_STATS, p3b_mc_statistics
from fortuna.simulation.engine import draw_mains_ordered
from fortuna.simulation.matrix import RegimeMatrix
from fortuna.simulation.seeding import make_rng


def determinism_probe_p3b(
    matrix: RegimeMatrix, root_seed: int, experiment_id: str, n: int = 100
) -> str:
    """SHA-256 of the first ``n`` ordered draws on the batch-1 stream."""
    scope = (
        f"{matrix.game_id}|{matrix.statistical_regime_id}"
        "|P3B_HISTORIES|batch1"
    )
    rng = make_rng(root_seed, experiment_id, scope)
    return hashlib.sha256(draw_mains_ordered(rng, matrix, n).tobytes()).hexdigest()


_CHUNK_ELEMENTS = 30_000_000  # same memory bound as simulation.montecarlo


def _chunk_size(n_ord: int, n_pool: int) -> int:
    """Replicates per chunk; keys use n_ord*n_pool floats per replicate."""
    return max(1, _CHUNK_ELEMENTS // max(1, n_ord * n_pool))


def run_regime_p3b(
    matrix: RegimeMatrix,
    n_ord: int,
    phys_seg_lengths: list[int],
    root_seed: int,
    experiment_id: str,
    batches: int,
    reps_per_batch: int,
    lags_same: tuple[int, ...],
    lags_cross: tuple[int, ...],
    windows: tuple[int, ...],
) -> dict[str, list[np.ndarray]]:
    """20k-replicate ordered fair null for one qualifying regime.

    Returns {statistic_id: [batch arrays]} for all MC-calibrated P3B
    statistics (P3B-S010 is permutation-calibrated and excluded).
    """
    k = matrix.main_count
    results: dict[str, list[np.ndarray]] = {s: [] for s in MC_STATS}
    for b in range(1, batches + 1):
        scope = (
            f"{matrix.game_id}|{matrix.statistical_regime_id}"
            f"|P3B_HISTORIES|batch{b}"
        )
        rng = make_rng(root_seed, experiment_id, scope)
        accum = {s: np.empty(reps_per_batch) for s in MC_STATS}
        done = 0
        while done < reps_per_batch:
            c = min(_chunk_size(n_ord, matrix.main_pool), reps_per_batch - done)
            od = draw_mains_ordered(rng, matrix, c * n_ord).reshape(
                c, n_ord, k
            ) - matrix.main_min
            for r in range(c):
                stats = p3b_mc_statistics(
                    od[r], matrix.main_pool, phys_seg_lengths,
                    lags_same, lags_cross, windows,
                )
                for s in MC_STATS:
                    accum[s][done + r] = stats[s]
            done += c
        for s in MC_STATS:
            results[s].append(accum[s])
    return results
