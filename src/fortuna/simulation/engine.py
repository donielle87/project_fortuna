"""Fair-draw engine for the F-E001 null model.

Draws follow each statistical regime's verified matrix:

- main balls: uniform WITHOUT replacement over [main_min, main_max]
- special ball (if the mechanism has one): uniform over its own pool,
  independent of the main selection
- no cross-regime pooling is possible: a draw is generated strictly from
  one RegimeMatrix

Sampling method: uniform random keys per main-ball label; the K smallest
keys are the selected labels — a uniform K-subset. For ordered draws the
labels are emitted in key order, i.e. a uniform ordered K-permutation.
"""

import numpy as np

from fortuna.simulation.matrix import RegimeMatrix


def draw_mains(rng: np.random.Generator, matrix: RegimeMatrix, n: int) -> np.ndarray:
    """``n`` fair main-ball draws, shape (n, K), each row sorted ascending.

    Values are actual ball labels in [main_min, main_max].
    """
    k, pool = matrix.main_count, matrix.main_pool
    keys = rng.random((n, pool))
    idx = np.argpartition(keys, k - 1, axis=1)[:, :k]
    idx.sort(axis=1)
    return idx + matrix.main_min


def draw_mains_ordered(
    rng: np.random.Generator, matrix: RegimeMatrix, n: int
) -> np.ndarray:
    """``n`` fair draws in physical draw order, shape (n, K).

    Row order is the order of selection (uniform ordered K-permutation).
    This is for the engine's order-capable interface only; Phase 2
    statistics are all order-insensitive.
    """
    k, pool = matrix.main_count, matrix.main_pool
    keys = rng.random((n, pool))
    idx = np.argpartition(keys, k - 1, axis=1)[:, :k]
    key_sel = np.take_along_axis(keys, idx, axis=1)
    order = np.argsort(key_sel, axis=1)
    ordered = np.take_along_axis(idx, order, axis=1)
    return ordered + matrix.main_min


def draw_specials(
    rng: np.random.Generator, matrix: RegimeMatrix, n: int
) -> np.ndarray | None:
    """``n`` fair special-ball draws, or None when the game has none."""
    if not matrix.has_special:
        return None
    assert matrix.special_min is not None and matrix.special_max is not None
    return rng.integers(matrix.special_min, matrix.special_max + 1, size=n)


def simulate_history(
    rng: np.random.Generator, matrix: RegimeMatrix, n_draws: int
) -> tuple[np.ndarray, np.ndarray | None]:
    """A fair replicate history of ``n_draws`` independent draws.

    Returns (mains (n, K) sorted ascending, specials (n,) or None).
    """
    mains = draw_mains(rng, matrix, n_draws)
    specials = draw_specials(rng, matrix, n_draws)
    return mains, specials
