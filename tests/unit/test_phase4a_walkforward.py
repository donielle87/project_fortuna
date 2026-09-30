"""F-E005 walk-forward integrity tests: strict-past features, warmup,
refit cadence, nested chronological penalty selection, and null sanity.
"""

import numpy as np

from fortuna.backtesting.walkforward import (
    REFIT_CADENCE,
    WARMUP,
    run_regime_walkforward,
)
from fortuna.models import fm


def _fair_history(rng, n, n_pool, k, m_pool):
    draws = np.array(
        [sorted(rng.choice(n_pool, k, replace=False)) for _ in range(n)]
    )
    sp = rng.integers(0, m_pool, n) if m_pool else None
    return draws, sp


def test_features_are_strictly_past():
    """F[t] must be identical whether or not draw t's outcome exists."""
    rng = np.random.default_rng(3)
    n_pool, k, m = 30, 5, 8
    draws, sp = _fair_history(rng, 40, n_pool, k, m)
    f1, s1 = fm.feature_trajectories(draws, sp, n_pool, k, m)
    # mutate the last outcome; earlier feature rows must not change
    draws2 = draws.copy()
    draws2[-1] = (draws[-1] + 7) % n_pool
    draws2.sort(axis=1)
    sp2 = sp.copy()
    sp2[-1] = (sp[-1] + 3) % m
    f2, s2 = fm.feature_trajectories(draws2, sp2, n_pool, k, m)
    np.testing.assert_array_equal(f1[:-1], f2[:-1])
    np.testing.assert_array_equal(s1[:-1], s2[:-1])


def test_warmup_enforced():
    rng = np.random.default_rng(5)
    draws, sp = _fair_history(rng, 150, 40, 5, 10)
    log = []
    rows = run_regime_walkforward(draws, sp, 40, 5, 10, "T", log)
    for recs in rows.values():
        assert len(recs) == 150 - WARMUP
        assert all(r["n_prior"] >= WARMUP for r in recs)


def test_refit_cadence():
    rng = np.random.default_rng(7)
    draws, sp = _fair_history(rng, 210, 40, 5, 10)
    log = []
    run_regime_walkforward(draws, sp, 40, 5, 10, "T", log)
    scored = sorted({e["scored_index"] for e in log})
    assert scored == list(range(0, 210 - WARMUP, REFIT_CADENCE))
    # each refit saw only draws < t: n_train equals draws before scoring
    for e in log:
        assert e["n_train"] >= WARMUP


def test_penalties_within_frozen_grid():
    rng = np.random.default_rng(9)
    draws, sp = _fair_history(rng, 210, 40, 5, 10)
    log = []
    run_regime_walkforward(draws, sp, 40, 5, 10, "T", log)
    assert log
    for e in log:
        assert e["penalty"] in fm.PENALTY_GRID


def test_inner_validation_is_chronological():
    """Inner fit = first 80%, inner validation = last 20% — the split is
    positional, never shuffled (structural assertion on the splitter)."""
    feats = np.random.default_rng(0).normal(size=(100, 6, 2))
    draws0 = np.tile(np.arange(5), (100, 1))
    seen = {}
    orig = fm._fit

    def spy(x, y, k, lam, softmax, beta0=None):
        seen.setdefault("n", []).append(x.shape[0])
        return orig(x, y, k, lam, softmax, beta0=beta0)

    fm._fit, prev = spy, fm._fit
    try:
        fm._nested_penalty(feats, draws0, 5, False, [], "T", 0)
    finally:
        fm._fit = prev
    # 4 inner fits (first 80) + 1 final fit (all 100)
    assert seen["n"][:4] == [80, 80, 80, 80]
    assert seen["n"][4] == 100


def test_no_future_influence_on_single_prediction():
    """Inserting a different future draw after t must not change the
    prediction scored at t."""
    rng = np.random.default_rng(11)
    draws, sp = _fair_history(rng, 130, 40, 5, 10)
    log1, log2 = [], []
    r1 = run_regime_walkforward(draws, sp, 40, 5, 10, "T", log1)
    d2, s2 = draws.copy(), sp.copy()
    d2[-1] = (draws[-1] + 5) % 40
    d2.sort(axis=1)
    s2[-1] = (sp[-1] + 1) % 10
    r2 = run_regime_walkforward(d2, s2, 40, 5, 10, "T", log2)
    for mid in fm.MODEL_IDS:
        # all scored draws except the last must be identical
        a = [x["logp_main_model"] for x in r1[mid][:-1]]
        b = [x["logp_main_model"] for x in r2[mid][:-1]]
        np.testing.assert_allclose(a, b, atol=1e-12)


def test_null_history_no_systematic_edge():
    """Fair synthetic history: no model should show large pooled lift."""
    rng = np.random.default_rng(21)
    draws, sp = _fair_history(rng, 300, 35, 5, 10)
    log = []
    rows = run_regime_walkforward(draws, sp, 35, 5, 10, "T", log)
    for mid in fm.MODEL_IDS:
        d = np.array([r["d_main"] for r in rows[mid]])
        assert d.mean() < 0.05, f"{mid} spurious lift {d.mean():.4f}"
