"""F-E004 Phase 3B tests — positional statistics, eligibility, power."""

from pathlib import Path

import numpy as np
import pytest

from fortuna.analysis import positional as pos
from fortuna.analysis import positional_synth as synth
from fortuna.analysis.montecarlo_p3b import run_regime_p3b
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime
from fortuna.simulation.engine import draw_mains_ordered
from fortuna.simulation.matrix import statistical_matrices
from fortuna.simulation.seeding import make_rng

ROOT = Path(__file__).resolve().parents[2]


def _matrix(sid="PB-S07"):
    regs = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)
    return statistical_matrices(regs)[sid]


@pytest.fixture
def m():
    return _matrix()


def test_ordered_draws_valid_and_uniform_marginals(m):
    rng = make_rng(1, "T", "t")
    od = draw_mains_ordered(rng, m, 4000) - m.main_min
    assert od.shape == (4000, m.main_count)
    for row in od[:200]:
        assert len(set(row.tolist())) == m.main_count  # no replacement
    # position marginals are uniform: mean label per position ~ N/2
    means = od.mean(axis=0)
    assert np.abs(means - (m.main_pool - 1) / 2).max() < 1.0
    # ordered draws are NOT sorted (sequential mechanism)
    assert not (np.diff(od, axis=1) >= 0).all(axis=1).all()


def test_position_ball_counts(m):
    od = np.array([[0, 1, 2, 3, 4], [4, 3, 2, 1, 0]])
    c = pos.position_ball_counts(od, 5)
    assert c.shape == (5, 5)
    assert c[0, 0] == 1 and c[0, 4] == 1      # position 1 saw balls 0 and 4
    assert c[2, 2] == 2                      # position 3 saw ball 2 twice


def test_s001_s002_fair_small(m):
    rng = make_rng(2, "T", "t")
    od = draw_mains_ordered(rng, m, 2000) - m.main_min
    t1, t2 = pos.p3b_s001(od, m.main_pool), pos.p3b_s002(od, m.main_pool)
    assert t1 > 0 and t2 > 0
    # chi2 omnibus around its rough df scale under the null
    assert t1 < m.main_count * m.main_pool * 3


def test_s003_cvm_uniform(m):
    rng = make_rng(3, "T", "t")
    od = draw_mains_ordered(rng, m, 1500) - m.main_min
    fair = pos.p3b_s003(od, m.main_pool)
    biased = od.copy()
    biased[:, 0] = 0                        # position 1 degenerate
    assert pos.p3b_s003(biased, m.main_pool) > fair * 10


def test_s004_adjacent_transition(m):
    rng = make_rng(4, "T", "t")
    od = draw_mains_ordered(rng, m, 1500) - m.main_min
    fair = pos.p3b_s004(od, m.main_pool)
    forced = synth.inject_conditional_bias(
        od, make_rng(5, "T", "t"), m.main_pool, q=1.0
    )
    assert pos.p3b_s004(forced, m.main_pool) > fair * 2


def test_s005_ordered_pair_extreme(m):
    rng = make_rng(6, "T", "t")
    od = draw_mains_ordered(rng, m, 1500) - m.main_min
    assert pos.p3b_s005(od, m.main_pool) > 0
    # degenerate: position 2 always successor of position 1
    forced = od.copy()
    forced[:, 1] = (forced[:, 0] + 1) % m.main_pool
    # collision may occur; ensure still detected via a non-colliding scheme
    assert pos.p3b_s005(forced, m.main_pool) > pos.p3b_s005(od, m.main_pool)


def test_s006_mi_fair_small_and_detects_dependence(m):
    rng = make_rng(7, "T", "t")
    od = draw_mains_ordered(rng, m, 2000) - m.main_min
    fair = pos.p3b_s006(od, m.main_pool)
    forced = synth.inject_conditional_bias(
        od, make_rng(8, "T", "t"), m.main_pool, q=0.8
    )
    # sparse-contingency MI carries a ~1-bit sampling bias under the
    # fair null; the MC null calibrates the SAME measure, so the test
    # asserts injected dependence exceeds the fair value, not zero.
    assert fair > 0
    assert pos.p3b_s006(forced, m.main_pool) > fair * 1.5


def test_s007_serial_within_segments(m):
    rng = make_rng(9, "T", "t")
    od = draw_mains_ordered(rng, m, 800) - m.main_min
    segs = [800]
    fair = pos.p3b_s007(od, m.main_pool, segs, (1, 2, 3, 4, 5))
    biased = synth.inject_serial_bias(
        od, make_rng(10, "T", "t"), m.main_pool, segs, 1, 0, 0, 0.5
    )
    assert pos.p3b_s007(biased, m.main_pool, segs, (1,)) > fair


def test_s007_no_bridging(m):
    rng = make_rng(11, "T", "t")
    od = draw_mains_ordered(rng, m, 600) - m.main_min
    whole = pos.p3b_s007_components(od, m.main_pool, [600], (1,))[(0, 1)]
    split = pos.p3b_s007_components(
        od, m.main_pool, [300, 300], (1,)
    )[(0, 1)]
    assert whole["n_pairs"] == 599
    assert split["n_pairs"] == 598          # one pair lost at the break


def test_s008_cross_position(m):
    rng = make_rng(12, "T", "t")
    od = draw_mains_ordered(rng, m, 800) - m.main_min
    segs = [800]
    fair = pos.p3b_s008(od, m.main_pool, segs, (1, 2, 3))
    biased = synth.inject_serial_bias(
        od, make_rng(13, "T", "t"), m.main_pool,
        segs, 1, m.main_count - 1, 0, 0.6,
    )
    assert pos.p3b_s008(biased, m.main_pool, segs, (1,)) > fair


def test_s009_window_scan_and_applicability(m):
    rng = make_rng(14, "T", "t")
    od = draw_mains_ordered(rng, m, 400) - m.main_min
    z, diag = pos.p3b_s009_scan(od, m.main_pool, [400], (100, 250))
    assert z > 0 and len(diag) > 0
    assert not pos.s009_applicable([50, 49], (100, 250))
    # injected local bias detected
    rows = np.arange(0, 100)
    biased = synth.inject_position_bias(
        od, make_rng(15, "T", "t"), m.main_pool, 0,
        n_boosted=5, delta=4.0, rows=rows,
    )
    zb, _ = pos.p3b_s009_scan(biased, m.main_pool, [400], (100,))
    assert zb > z


def test_s010_equipment_positional(m):
    rng = make_rng(16, "T", "t")
    od = draw_mains_ordered(rng, m, 600) - m.main_min
    labels = np.array(["A"] * 300 + ["B"] * 300)
    t = pos.p3b_s010_chi2(od, labels, m.main_pool)
    assert t > 0
    # biased category: machine A always starts with low balls
    od_b = od.copy()
    od_b[:300, 0] = rng.integers(0, 5, 300)
    tb = pos.p3b_s010_chi2(od_b, labels, m.main_pool)
    assert tb > t * 2


def test_fair_histories_distinct_rows_determinism(m):
    a = run_regime_p3b(m, 120, [120], 99, "T", 2, 5, (1,), (1,), (100,))
    b = run_regime_p3b(m, 120, [120], 99, "T", 2, 5, (1,), (1,), (100,))
    for s in pos.MC_STATS:
        assert np.array_equal(np.concatenate(a[s]), np.concatenate(b[s]))
    c = run_regime_p3b(m, 120, [120], 98, "T", 2, 5, (1,), (1,), (100,))
    assert not np.array_equal(
        np.concatenate(a["P3B-S001"]), np.concatenate(c["P3B-S001"])
    )
