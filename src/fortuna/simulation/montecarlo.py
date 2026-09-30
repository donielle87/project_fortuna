"""F-E001 Monte Carlo history baseline runner.

Per statistical regime: 4 deterministic batches x 5,000 replicate fair
histories (20,000 total). Each replicate history has the frozen eligible
draw count and contiguous-segment structure from the observation plan.
Statistics accumulate; raw draws are never persisted.

One shared history stream per (regime, batch) generates the replicate
histories; all applicable catalog statistics are computed from the same
histories (they are different views of the same fair draws — simulating
13 parallel universes would be identical in distribution and 13x the
cost). Scope string: "<game>|<stat_regime>|HISTORIES|batch<1..4>".
"""

import hashlib

import numpy as np

from fortuna.simulation.engine import draw_mains, draw_specials
from fortuna.simulation.matrix import RegimeMatrix
from fortuna.simulation.seeding import make_rng
from fortuna.simulation.statistics import (
    applicable_statistics,
    history_statistics,
)

# element budget per generation chunk (~240 MB of float64 keys)
_CHUNK_ELEMENTS = 30_000_000


def _chunk_reps(n_draws: int, pool: int) -> int:
    return max(1, _CHUNK_ELEMENTS // max(1, n_draws * pool))


def _draw_chunk(
    rng: np.random.Generator, matrix: RegimeMatrix, n_draws: int, reps: int
) -> tuple[np.ndarray, np.ndarray | None]:
    """(reps, n_draws, K) sorted mains and (reps, n_draws) specials."""
    k, pool = matrix.main_count, matrix.main_pool
    keys = rng.random((reps, n_draws, pool))
    idx = np.argpartition(keys, k - 1, axis=2)[:, :, :k]
    idx.sort(axis=2)
    mains = idx + matrix.main_min
    specials = None
    if matrix.has_special:
        assert matrix.special_min is not None and matrix.special_max is not None
        specials = rng.integers(
            matrix.special_min, matrix.special_max + 1, size=(reps, n_draws)
        )
    return mains, specials


def determinism_probe(
    matrix: RegimeMatrix, root_seed: int, experiment_id: str, n: int = 100
) -> str:
    """SHA-256 of the first ``n`` draws on the batch-1 history stream.

    Re-deriving this probe reproves deterministic regeneration without
    rerunning the full baseline.
    """
    scope = f"{matrix.game_id}|{matrix.statistical_regime_id}|HISTORIES|batch1"
    rng = make_rng(root_seed, experiment_id, scope)
    mains = draw_mains(rng, matrix, n)
    specials = draw_specials(rng, matrix, n)
    h = hashlib.sha256()
    h.update(mains.tobytes())
    if specials is not None:
        h.update(specials.tobytes())
    return h.hexdigest()


def run_regime(
    matrix: RegimeMatrix,
    n_draws: int,
    segment_lengths: list[int],
    root_seed: int,
    experiment_id: str,
    batches: int = 4,
    reps_per_batch: int = 5000,
) -> dict[str, list[np.ndarray]]:
    """Run the frozen baseline for one statistical regime.

    Returns {statistic_id: [batch1_array, ..., batch4_array]}, each batch
    array shape (reps_per_batch,).
    """
    stat_ids = applicable_statistics(matrix)
    results: dict[str, list[np.ndarray]] = {s: [] for s in stat_ids}
    for b in range(1, batches + 1):
        scope = (
            f"{matrix.game_id}|{matrix.statistical_regime_id}|HISTORIES|batch{b}"
        )
        rng = make_rng(root_seed, experiment_id, scope)
        accum = {s: np.empty(reps_per_batch) for s in stat_ids}
        done = 0
        while done < reps_per_batch:
            c = min(_chunk_reps(n_draws, matrix.main_pool), reps_per_batch - done)
            mains, specials = _draw_chunk(rng, matrix, n_draws, c)
            for r in range(c):
                stats = history_statistics(
                    mains[r],
                    specials[r] if specials is not None else None,
                    matrix,
                    segment_lengths,
                )
                for s in stat_ids:
                    accum[s][done + r] = stats[s]
            done += c
        for s in stat_ids:
            results[s].append(accum[s])
    return results
