"""F-E005 Task 4 tests: exact weighted K-subset model vs enumeration."""

import itertools
import math

import numpy as np

from fortuna.models.wsubset import (
    inclusion_probs,
    log_e_k,
    log_p_subset,
    uniform_log_p,
)


def _enum_probs(w: np.ndarray, k: int) -> dict[frozenset, float]:
    """Brute-force P(S) for every K-subset."""
    n_pool = w.size
    ek = sum(
        math.prod(w[i] for i in comb)
        for comb in itertools.combinations(range(n_pool), k)
    )
    return {
        frozenset(c): math.prod(w[i] for i in c) / ek
        for c in itertools.combinations(range(n_pool), k)
    }


def test_e_k_matches_enumeration():
    rng = np.random.default_rng(7)
    for n_pool, k in ((5, 2), (7, 3), (9, 4)):
        w = rng.uniform(0.2, 4.0, n_pool)
        ek_enum = sum(
            math.prod(w[i] for i in c)
            for c in itertools.combinations(range(n_pool), k)
        )
        got = log_e_k(np.log(w)[None, :], k)[0]
        assert abs(got - math.log(ek_enum)) < 1e-9


def test_distribution_sums_to_one():
    rng = np.random.default_rng(11)
    n_pool, k = 8, 3
    w = rng.uniform(0.1, 5.0, n_pool)
    logw = np.log(w)[None, :]
    total = 0.0
    for c in itertools.combinations(range(n_pool), k):
        lp = log_p_subset(logw, np.array(c)[None, :], k)[0]
        total += math.exp(lp)
    assert abs(total - 1.0) < 1e-9


def test_inclusion_marginals_match_enumeration():
    rng = np.random.default_rng(13)
    n_pool, k = 8, 3
    w = rng.uniform(0.1, 5.0, n_pool)
    probs = _enum_probs(w, k)
    enum_marg = np.zeros(n_pool)
    for s, p in probs.items():
        for i in s:
            enum_marg[i] += p
    got = inclusion_probs(np.log(w)[None, :], k)[0]
    np.testing.assert_allclose(got, enum_marg, atol=1e-9)
    assert abs(got.sum() - k) < 1e-9


def test_uniform_weights_recover_fair_model():
    n_pool, k = 10, 5
    logw = np.zeros((1, n_pool))
    lp = log_p_subset(logw, np.array([0, 1, 2, 3, 4])[None, :], k)
    assert abs(lp[0] - uniform_log_p(n_pool, k)) < 1e-12
    inc = inclusion_probs(logw, k)[0]
    np.testing.assert_allclose(inc, np.full(n_pool, k / n_pool),
                               atol=1e-12)


def test_marginal_bounds_and_sum():
    rng = np.random.default_rng(17)
    n_pool, k = 12, 4
    w = rng.uniform(0.05, 20.0, n_pool)
    inc = inclusion_probs(np.log(w)[None, :], k)[0]
    assert inc.min() >= 0.0 and inc.max() <= 1.0
    assert abs(inc.sum() - k) < 1e-9
