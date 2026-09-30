"""F-E002 exploration-matched Monte Carlo runner.

Same stream discipline as the governed F-E001 implementation: one shared
fair-history stream per "<game>|<stat_regime>|HISTORIES|batch<1..4>"
(frozen for F-E002 from the start). All primary (F-S) and history-level
secondary (P3-S001..S010) statistics are computed from the same replicate
histories; raw draws are never persisted.
"""

import hashlib

import numpy as np

from fortuna.analysis.secondary import (
    HISTORY_SECONDARY,
    p3_history_statistics,
)
from fortuna.simulation.engine import draw_mains, draw_specials
from fortuna.simulation.matrix import RegimeMatrix
from fortuna.simulation.montecarlo import _chunk_reps, _draw_chunk
from fortuna.simulation.seeding import make_rng
from fortuna.simulation.statistics import (
    applicable_statistics,
    history_statistics,
)


def determinism_probe(
    matrix: RegimeMatrix, root_seed: int, experiment_id: str, n: int = 100
) -> str:
    """SHA-256 of the first ``n`` draws on the batch-1 F-E002 stream."""
    scope = f"{matrix.game_id}|{matrix.statistical_regime_id}|HISTORIES|batch1"
    rng = make_rng(root_seed, experiment_id, scope)
    mains = draw_mains(rng, matrix, n)
    specials = draw_specials(rng, matrix, n)
    h = hashlib.sha256()
    h.update(mains.tobytes())
    if specials is not None:
        h.update(specials.tobytes())
    return h.hexdigest()


def run_regime_p3(
    matrix: RegimeMatrix,
    n_draws: int,
    segment_lengths: list[int],
    root_seed: int,
    experiment_id: str,
    batches: int,
    reps_per_batch: int,
    lags: tuple[int, ...],
    overlap_mean: float,
    overlap_var: float,
    windows: tuple[int, ...],
    ref_pmfs: dict[str, dict[float, float]],
) -> dict[str, list[np.ndarray]]:
    """Run the frozen F-E002 baseline for one statistical regime.

    Returns {statistic_id: [batch arrays]} for all applicable primary
    F-S statistics plus the ten history-level secondary statistics.
    """
    stat_ids = applicable_statistics(matrix) + list(HISTORY_SECONDARY)
    results: dict[str, list[np.ndarray]] = {s: [] for s in stat_ids}
    for b in range(1, batches + 1):
        scope = (
            f"{matrix.game_id}|{matrix.statistical_regime_id}|HISTORIES|batch{b}"
        )
        rng = make_rng(root_seed, experiment_id, scope)
        accum = {s: np.empty(reps_per_batch) for s in stat_ids}
        done = 0
        while done < reps_per_batch:
            c = min(
                _chunk_reps(n_draws, matrix.main_pool), reps_per_batch - done
            )
            mains, specials = _draw_chunk(rng, matrix, n_draws, c)
            for r in range(c):
                stats = history_statistics(
                    mains[r],
                    specials[r] if specials is not None else None,
                    matrix,
                    segment_lengths,
                )
                stats.update(
                    p3_history_statistics(
                        mains[r], matrix, segment_lengths, lags,
                        overlap_mean, overlap_var, windows, ref_pmfs,
                    )
                )
                for s in stat_ids:
                    accum[s][done + r] = stats[s]
            done += c
        for s in stat_ids:
            results[s].append(accum[s])
    return results
