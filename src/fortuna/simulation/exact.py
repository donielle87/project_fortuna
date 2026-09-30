"""Exact combinatorial baselines for the F-E001 fair-random null.

All probabilities are computed with exact integer combinatorics
(``math.comb``) and returned as floats. No Monte Carlo approximation is
used anywhere in this module.
"""

from math import comb

import numpy as np

from fortuna.simulation.matrix import RegimeMatrix


def main_sample_space(n_pool: int, k: int) -> int:
    """C(N, K) — number of valid main-ball combinations."""
    return comb(n_pool, k)


def jackpot_sample_space(matrix: RegimeMatrix) -> int:
    """C(N, K) * M for special-ball games, else C(N, K)."""
    base = main_sample_space(matrix.main_pool, matrix.main_count)
    return base * matrix.special_pool if matrix.has_special else base


def inclusion_prob(n_pool: int, k: int) -> float:
    """P(a fixed main ball is drawn) = K/N."""
    return k / n_pool


def pair_prob(n_pool: int, k: int) -> float:
    """P(a fixed pair both appear) = C(K,2)/C(N,2)."""
    return comb(k, 2) / comb(n_pool, 2)


def triple_prob(n_pool: int, k: int) -> float:
    """P(a fixed triple all appear) = C(K,3)/C(N,3); 0 when K < 3."""
    if k < 3 or n_pool < 3:
        return 0.0
    return comb(k, 3) / comb(n_pool, 3)


def overlap_pmf(n_pool: int, k: int) -> np.ndarray:
    """Exact pmf of |A ∩ B| for two independent K-of-N draws.

    P(overlap = j) = C(K,j) * C(N-K, K-j) / C(N,K), j = 0..K.
    """
    denom = comb(n_pool, k)
    pmf = np.zeros(k + 1)
    for j in range(k + 1):
        pmf[j] = comb(k, j) * comb(n_pool - k, k - j) / denom
    return pmf


def odd_even_pmf(main_min: int, main_max: int, k: int) -> np.ndarray:
    """Exact pmf of the number of ODD balls in one draw (hypergeometric).

    P(j odd) = C(O, j) * C(E, K-j) / C(N, K), where O = count of odd
    labels in [main_min, main_max].
    """
    n_pool = main_max - main_min + 1
    first_odd = main_min if main_min % 2 == 1 else main_min + 1
    n_odd = (main_max - first_odd) // 2 + 1
    n_even = n_pool - n_odd
    denom = comb(n_pool, k)
    pmf = np.zeros(k + 1)
    for j in range(k + 1):
        if j <= n_odd and (k - j) <= n_even:
            pmf[j] = comb(n_odd, j) * comb(n_even, k - j) / denom
    return pmf


def special_repeat_prob(matrix: RegimeMatrix) -> float | None:
    """P(two consecutive special-ball draws match) = 1/M; None if no special."""
    if not matrix.has_special:
        return None
    return 1.0 / matrix.special_pool


def candidate_pool_pmf(n_pool: int, k: int, pool_size: int) -> np.ndarray:
    """Exact pmf of X ~ Hypergeometric(N, K, m).

    X = number of the K winning balls covered by a fixed candidate pool of
    size m: P(X = x) = C(K,x) * C(N-K, m-x) / C(N,m).

    Baseline utility only — this module never selects or ranks pools.
    """
    denom = comb(n_pool, pool_size)
    pmf = np.zeros(min(k, pool_size) + 1)
    for x in range(len(pmf)):
        pmf[x] = comb(k, x) * comb(n_pool - k, pool_size - x) / denom
    return pmf


def candidate_pool_tail(n_pool: int, k: int, pool_size: int, r: int) -> float:
    """P(X >= r) for X ~ Hypergeometric(N, K, m). Exact."""
    return float(candidate_pool_pmf(n_pool, k, pool_size)[r:].sum())


def ticket_match_pmf(matrix: RegimeMatrix) -> np.ndarray:
    """P(a uniform random ticket matches exactly j main balls of an
    independent uniform winning draw) = C(K,j)*C(N-K,K-j)/C(N,K)."""
    return overlap_pmf(matrix.main_pool, matrix.main_count)


def ticket_joint_match_pmf(matrix: RegimeMatrix) -> np.ndarray:
    """Joint pmf over (main matches j, special hit h), shape (K+1, 2).

    Special-ball games: independent factor 1/M vs (M-1)/M.
    Without a special ball the h=1 column is empty.
    """
    main_pmf = ticket_match_pmf(matrix)
    out = np.zeros((matrix.main_count + 1, 2))
    if matrix.has_special:
        m = matrix.special_pool
        out[:, 1] = main_pmf / m
        out[:, 0] = main_pmf * (m - 1) / m
    else:
        out[:, 0] = main_pmf
    return out


def jackpot_prob(matrix: RegimeMatrix) -> float:
    """P(uniform ticket matches all K mains and the special ball)."""
    return 1.0 / jackpot_sample_space(matrix)


def inclusion_moments(n_pool: int, k: int) -> dict[str, float]:
    """First/second moments of main-ball inclusion indicators I_i.

    p       = E[I_i]        = K/N
    var     = Var(I_i)      = p(1-p)
    cov_ij  = Cov(I_i, I_j) = K(K-1)/(N(N-1)) - p^2   (i != j, NEGATIVE)
    """
    p = k / n_pool
    p_ij = k * (k - 1) / (n_pool * (n_pool - 1))
    return {
        "p": p,
        "var": p * (1 - p),
        "p_pair": p_ij,
        "cov": p_ij - p * p,
    }


def sum_pmf(main_min: int, main_max: int, k: int) -> dict[int, float]:
    """Exact pmf of the main-ball sum, by DP over distinct labels.

    Returns {sum_value: probability}.
    """
    n_pool = main_max - main_min + 1
    # dp[c][s] = number of ways to pick c distinct labels with sum s
    dp: list[dict[int, int]] = [{0: 1}] + [{} for _ in range(k)]
    for v in range(main_min, main_max + 1):
        for c in range(min(k, v - main_min + 1), 0, -1):
            for s, cnt in dp[c - 1].items():
                dp[c][s + v] = dp[c].get(s + v, 0) + cnt
    total = comb(n_pool, k)
    return {s: cnt / total for s, cnt in sorted(dp[k].items())}


def range_pmf(main_min: int, main_max: int, k: int) -> dict[int, float]:
    """Exact pmf of the main-ball range (max - min) for one draw.

    For span r: (N - r) positions of the min element, and the other K-2
    balls inside the open interval of width r: count = (N-r)*C(r-1, K-2).
    """
    n_pool = main_max - main_min + 1
    total = comb(n_pool, k)
    pmf: dict[int, float] = {}
    for r in range(k - 1, n_pool):
        count = (n_pool - r) * comb(r - 1, k - 2) if k >= 2 else 0
        if count:
            pmf[r] = count / total
    return pmf


def no_consecutive_prob(n_pool: int, k: int) -> float:
    """P(no two drawn main balls are consecutive) = C(N-K+1, K)/C(N,K)."""
    return comb(n_pool - k + 1, k) / comb(n_pool, k)
