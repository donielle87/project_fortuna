"""F-E004 synthetic power tests (Task 15) — the P3B statistics must
detect known injected defects at reasonable effect strength.

Each test estimates the detection rate of a statistic under a biased
generator against its own fair-null critical value, both computed by
Monte Carlo on small histories (kept cheap for CI).
"""

from pathlib import Path

import numpy as np
import pytest

from fortuna.analysis import positional as pos
from fortuna.analysis import positional_synth as synth
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime
from fortuna.simulation.engine import draw_mains_ordered
from fortuna.simulation.matrix import statistical_matrices
from fortuna.simulation.seeding import make_rng

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def m():
    regs = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)
    return statistical_matrices(regs)["MM-S04"]  # K=5, N=56


def _power(m, stat_fn, scenario, effect, n_ord=400, segs=None, n_rep=60):
    segs = segs or [n_ord]
    rng0 = make_rng(1000, "T", f"null|{scenario}")
    fair = np.array([
        stat_fn(draw_mains_ordered(rng0, m, n_ord) - m.main_min)
        for _ in range(n_rep)
    ])
    crit = np.quantile(fair, 0.95)
    rng1 = make_rng(2000, "T", f"alt|{scenario}|{effect}")
    hits = sum(
        stat_fn(
            synth.make_history(rng1, m, n_ord, segs, scenario, effect)
        ) >= crit
        for _ in range(n_rep)
    )
    return hits / n_rep


def test_power_position1_bias(m):
    """A: position-1 bias is detected by S001/S002 at strong effect."""
    p1 = _power(
        m, lambda h: pos.p3b_s001(h, m.main_pool),
        "position1_bias", 3.0,
    )
    p2 = _power(
        m, lambda h: pos.p3b_s002(h, m.main_pool),
        "position1_bias", 3.0,
    )
    assert p1 >= 0.8 and p2 >= 0.8


def test_power_conditional_bias(m):
    """B: within-draw conditional dependence detected by S004/S006
    while the marginal-only stat S001 stays near-null."""
    p4 = _power(
        m, lambda h: pos.p3b_s004(h, m.main_pool),
        "conditional_bias", 0.8,
    )
    p6 = _power(
        m, lambda h: pos.p3b_s006(h, m.main_pool),
        "conditional_bias", 0.8,
    )
    p1 = _power(
        m, lambda h: pos.p3b_s001(h, m.main_pool),
        "conditional_bias", 0.8,
    )
    assert p4 >= 0.8 and p6 >= 0.8
    assert p1 < p4          # marginals stay ~uniform


def test_power_serial_same_position(m):
    """C: X1,t -> X1,t+1 dependence detected by S007."""
    p = _power(
        m,
        lambda h: pos.p3b_s007(h, m.main_pool, [h.shape[0]], (1,)),
        "serial_same_pos", 0.4,
    )
    assert p >= 0.8


def test_power_serial_cross_position(m):
    """D: X5,t -> X1,t+1 dependence detected by S008."""
    p = _power(
        m,
        lambda h: pos.p3b_s008(h, m.main_pool, [h.shape[0]], (1,)),
        "serial_cross_pos", 0.4,
    )
    assert p >= 0.8


def test_power_temporal_position(m):
    """E: a temporary position-1 bias inside one window is detected by
    the S009 rolling scan even when the full-history marginal is mild."""
    n = 500
    p9 = _power(
        m,
        lambda h: pos.p3b_s009(h, m.main_pool, [h.shape[0]], (100, 250)),
        "temporal_position", 6.0, n_ord=n,
    )
    assert p9 >= 0.8


def test_fair_control_type1(m):
    """Fair histories should exceed the 95% critical ~5% of the time."""
    p = _power(m, lambda h: pos.p3b_s001(h, m.main_pool), "fair", 0.0)
    assert p <= 0.25  # loose bound; point estimate should be ~0.05
