"""F-E005 synthetic control history generators.

Deterministic histories under a declared bias mechanism, generated with
scoped PCG64DXSM streams (fortuna.simulation.seeding.make_rng). Biased
scenarios sample main balls by sequential proportional
without-replacement draws (Efraimidis-Spirakis keys); the null uses fair
uniform without-replacement draws. Special balls are uniform in all
scenarios — controls verify main-side detection.
"""

import numpy as np

from fortuna.models.fm import draw_weighted_subset
from fortuna.simulation.seeding import make_rng


def fair_history(rng: np.random.Generator, n: int, n_pool: int, k: int,
                 m_pool: int) -> tuple[np.ndarray, np.ndarray]:
    draws = np.array(
        [sorted(rng.choice(n_pool, k, replace=False)) for _ in range(n)]
    )
    return draws, rng.integers(0, m_pool, n)


def biased_history(
    rng: np.random.Generator, n: int, n_pool: int, k: int, m_pool: int,
    scenario: str, strength: float, boosted: np.ndarray,
    rotate_every: int = 100,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate a history under the frozen control scenarios A–D."""
    draws = np.empty((n, k), dtype=int)
    gap = np.zeros(n_pool)
    prev = np.zeros(n_pool)
    base = np.ones(n_pool)
    for t in range(n):
        w = base.copy()
        if scenario == "A":           # persistent weight bias
            w[boosted] *= 1.0 + strength
        elif scenario == "B":         # recency/gap-dependent bias
            w = np.exp(strength * gap / (n_pool / k))
        elif scenario == "C":         # previous-draw-dependent bias
            w = np.exp(strength * prev)
        elif scenario == "D":         # rotating boosted subset
            rot = np.roll(boosted, t // rotate_every)
            w[rot % n_pool] *= 1.0 + strength
        else:
            raise ValueError(scenario)
        d = draw_weighted_subset(rng, w, k)
        draws[t] = sorted(d)
        gap += 1.0
        gap[d] = 0.0
        prev[:] = 0.0
        prev[d] = 1.0
    return draws, rng.integers(0, m_pool, n)


def control_rng(experiment_id: str, scenario: str, effect: float,
                rep: int) -> np.random.Generator:
    return make_rng(
        20261007, experiment_id,
        f"SYNTH|{scenario}|{effect}|rep{rep}",
    )


def boosted_set(rng: np.random.Generator, n_pool: int,
                n_boosted: int) -> np.ndarray:
    return np.sort(rng.choice(n_pool, n_boosted, replace=False))
