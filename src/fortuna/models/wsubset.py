"""Exact weighted fixed-size subset model (F-E005 Task 4).

For positive ball weights ``w`` over labels 0..N-1 the model assigns a
valid K-subset S the probability

    P(S) = prod_{i in S} w_i / e_K(w)

where e_K is the K-th elementary symmetric polynomial. This is a proper
distribution over exactly-K distinct labels (no replacement); all-equal
weights recover the uniform 1/C(N,K) lottery model.

All functions operate in LOG space and are vectorized over a leading
"draw" axis: ``logw`` is (n, N) and results are per-row.
"""

import numpy as np

NEG = -np.inf


def log_e_k(logw: np.ndarray, k: int) -> np.ndarray:
    """log e_k(w) per row of ``logw`` (n, N); returns (n,)."""
    logw = np.atleast_2d(logw)
    n, n_pool = logw.shape
    dp = np.full((n, k + 1), NEG)
    dp[:, 0] = 0.0
    for i in range(n_pool):
        lw = logw[:, i]
        for j in range(min(i + 1, k), 0, -1):
            dp[:, j] = np.logaddexp(dp[:, j], dp[:, j - 1] + lw)
    return dp[:, k]


def log_p_subset(logw: np.ndarray, subsets0: np.ndarray, k: int) -> np.ndarray:
    """log P(S) per row. ``subsets0`` is (n, K) zero-based label indices."""
    logw = np.atleast_2d(logw)
    num = np.take_along_axis(logw, subsets0, axis=1).sum(axis=1)
    return num - log_e_k(logw, k)


def inclusion_probs(logw: np.ndarray, k: int) -> np.ndarray:
    """Exact model marginals P(i in S) per row, shape (n, N).

    P(i in S) = w_i * e_{K-1}(w_{-i}) / e_K(w).  e_{K-1}(w_{-i}) is
    computed for all i by prefix/suffix DP:

        e_{K-1}(w_{-i}) = sum_a e_a(w_{<i}) * e_{K-1-a}(w_{>i})
    """
    logw = np.atleast_2d(logw)
    n, n_pool = logw.shape
    # pre[:, i, a] = log e_a over labels < i
    pre = np.full((n, n_pool + 1, k + 1), NEG)
    pre[:, :, 0] = 0.0
    # suf[:, i, a] = log e_a over labels >= i
    suf = np.full((n, n_pool + 1, k + 1), NEG)
    suf[:, n_pool, 0] = 0.0
    suf[:, :, 0] = 0.0
    for i in range(1, n_pool + 1):
        lw = logw[:, i - 1]
        pre[:, i, 0] = 0.0
        for a in range(1, k + 1):
            pre[:, i, a] = np.logaddexp(pre[:, i - 1, a],
                                        pre[:, i - 1, a - 1] + lw)
    for i in range(n_pool - 1, -1, -1):
        lw = logw[:, i]
        for a in range(1, k + 1):
            suf[:, i, a] = np.logaddexp(suf[:, i + 1, a],
                                        suf[:, i + 1, a - 1] + lw)
    log_eK = pre[:, n_pool, k]
    # e_{K-1}(w_{-i}) = logsumexp_a pre[i,a] + suf[i+1, K-1-a]
    kk = k - 1
    acc = np.full((n, n_pool), NEG)
    for a in range(kk + 1):
        acc = np.logaddexp(
            acc,
            pre[:, :n_pool, a] + suf[:, 1:, kk - a],
        )
    lp = logw + acc - log_eK[:, None]
    return np.exp(lp)


def uniform_log_p(n_pool: int, k: int) -> float:
    """log(1 / C(N, K)) under the fair uniform model."""
    import math

    return -math.log(math.comb(n_pool, k))
