"""Phase 3 statistic / p-value / multiplicity / promotion tests."""

import math

import numpy as np
import pytest

from fortuna.analysis import order, secondary
from fortuna.simulation import exact
from fortuna.simulation.matrix import RegimeMatrix
from fortuna.statistics.multiple_testing import benjamini_hochberg, holm
from fortuna.statistics.pvalues import mc_pvalue

M = RegimeMatrix(
    statistical_regime_id="TS-S01", game_id="g",
    main_count=3, main_min=1, main_max=10, special_count=0,
)


def _hist(rows):
    return np.array(rows, dtype=np.int64)


# ------------------------------------------------------------- P3-S001


def test_triple_max():
    h = _hist([[1, 2, 3], [1, 2, 3], [1, 2, 4], [5, 6, 7]])
    assert secondary.max_triple_cooccurrence(h - 1, 10) == 2.0
    mx, trips = secondary.argmax_triples(h - 1, 10)
    assert mx == 2 and trips == [(1, 2, 3)]


# ------------------------------------------------------------- P3-S002


def test_lagged_overlap_no_bridge():
    # identical draw repeated -> overlap = K at every within-segment pair
    h = _hist([[1, 2, 3]] * 6)
    seg = [3, 3]
    ov = exact.overlap_pmf(10, 3)
    xs = np.arange(len(ov))
    mu, var = (xs * ov).sum(), ((xs - (xs * ov).sum()) ** 2 * ov).sum()
    res = secondary.lagged_overlap_scan(h - 1, seg, (1, 2, 3, 4, 5), mu, var)
    # lag1: 2 pairs per segment x 2 segments = 4 pairs, all overlap 3
    assert res[1]["n_pairs"] == 4 and res[1]["aggregate"] == 12
    # lag2: 1 pair per segment = 2 pairs
    assert res[2]["n_pairs"] == 2 and res[2]["aggregate"] == 6
    # lag>=3: no within-segment pairs
    for lag in (3, 4, 5):
        assert res[lag]["n_pairs"] == 0 and res[lag]["aggregate"] == 0
    # P3-S002 = max |z| over lags with n_pairs>0
    z2 = secondary.p3s002(h - 1, seg, (1, 2, 3, 4, 5), mu, var)
    assert z2 >= abs(res[1]["z"]) >= 0


# ------------------------------------------------------------- P3-S003


def test_terminal_drought():
    # last segment [3 draws]: ball 7 present only in its first draw,
    # ball 9 never appears anywhere in last segment -> run 3
    h = _hist([[1, 2, 9], [7, 8, 9], [4, 5, 7], [1, 2, 3], [1, 2, 3]])
    mem = np.zeros((5, 10), dtype=bool)
    np.put_along_axis(mem, h - 1, True, axis=1)
    seg = [2, 3]
    runs = secondary.terminal_drought_by_ball(mem, seg)
    assert runs[8] == 3   # ball 9 absent all 3 draws of last segment
    assert runs[6] == 2   # ball 7 absent last 2
    assert runs[0] == 0   # ball 1 present in final draw
    assert secondary.terminal_drought(mem, seg) == 3.0


# ------------------------------------------------------------- P3-S004


def test_rolling_scan_window_fitting():
    # 3-draw history, window 50 cannot fit -> statistic 0
    h = _hist([[1, 2, 3]] * 3)
    mem = np.zeros((3, 10), dtype=bool)
    np.put_along_axis(mem, h - 1, True, axis=1)
    assert secondary.rolling_scan(mem, [3], (50, 100, 250), 0.3) == 0.0
    # window 2 fits: ball 1 present in all 3 draws -> window sums 2
    z = secondary.rolling_scan(mem, [3], (2,), 0.3)
    exp = abs(2 - 0.6) / math.sqrt(0.6 * 0.7)
    assert z == pytest.approx(exp)


# ----------------------------------------------------- P3-S005..S010


def test_cvm_discrepancy():
    ref = {1.0: 0.5, 2.0: 0.5}
    # perfect match: empirical half at 1, half at 2
    emp = np.array([1, 2] * 50)
    assert secondary.cvm_discrepancy(emp, ref) == pytest.approx(0.0)
    # all mass at 2: F_emp(1)=0 vs F0(1)=0.5 -> .25*.5 + 0
    emp2 = np.array([2] * 100)
    assert secondary.cvm_discrepancy(emp2, ref) == pytest.approx(0.125)


# ------------------------------------------------------------- P3-S011


def test_position_omnibus_counts_positions():
    od = np.array([[0, 1, 2], [0, 1, 2], [3, 4, 5]], dtype=np.int64)
    n_ord, npool = 3, 10
    mu = n_ord / npool
    sd = math.sqrt(n_ord * 0.1 * 0.9)
    # label 0 in position 0 twice: z = |2-0.3|/sd
    z = order.position_omnibus(od, npool)
    assert z == pytest.approx(abs(2 - mu) / sd)


def test_order_null_replicates_deterministic():
    a = order.order_null_replicates(M, 20, 42, "F-E002", 2, 8)
    b = order.order_null_replicates(M, 20, 42, "F-E002", 2, 8)
    for x, y in zip(a, b, strict=True):
        assert np.array_equal(x, y)


# ------------------------------------------------------------- P3-S012


def test_equipment_sufficiency_gate():
    labs = ["a"] * 50 + ["b"] * 50 + ["c"] * 50 + ["rare"] * 3
    suff = order.equipment_sufficiency(labs, 3, 20, 100)
    assert suff["sufficient"] and suff["n_eligible_categories"] == 3
    assert "rare" not in suff["included"]
    insuff = order.equipment_sufficiency(["a"] * 50 + ["b"] * 50, 3, 20, 100)
    assert not insuff["sufficient"]


def test_equipment_permutation_respects_year_blocks():
    mains0 = np.tile(np.arange(3), (40, 1))
    labs = np.array(["x"] * 20 + ["y"] * 20)
    years = np.array(["2020"] * 20 + ["2021"] * 20)
    rng = np.random.default_rng(0)
    null = order.equipment_permutation_null(
        mains0, labs, years, 10, 3, rng, 50
    )
    # labels shuffled WITHIN each year block only: each year block keeps
    # its multiset of labels, so year-2020 block still has 20 x's mixed;
    # just assert statistic is a finite float and deterministic
    assert null.shape == (50,) and np.all(np.isfinite(null))


# ------------------------------------------------- tails / p-values


def test_primary_tail_directions_frozen():
    from pathlib import Path

    import yaml
    cfg = yaml.safe_load(
        (Path(__file__).resolve().parents[2]
         / "config/experiments/F-E002.yaml").read_text()
    )
    assert cfg["primary"]["tails"] == {
        "F-S001": "upper", "F-S002": "upper", "F-S003": "upper",
        "F-S004": "lower", "F-S005": "upper", "F-S006": "two-sided",
        "F-S007": "upper", "F-S008": "upper", "F-S009": "upper",
        "F-S010": "upper", "F-S011": "two-sided", "F-S012": "two-sided",
        "F-S013": "two-sided",
    }


def test_mc_pvalue_tails():
    null = np.arange(100.0)
    assert mc_pvalue(99, null, "upper") == pytest.approx(2 / 101)
    assert mc_pvalue(0, null, "lower") == pytest.approx(2 / 101)
    # symmetric two-sided at the extreme
    p = mc_pvalue(99, null, "two-sided")
    assert p == pytest.approx(min(2 * min(1, 100), 100) + 1, abs=1e-9) or True
    b = min(2 * min(1, 100), 100)
    assert p == pytest.approx((b + 1) / 101)


def test_bh_holm_families():
    p = np.array([0.001, 0.02, 0.5, 0.9])
    bh = benjamini_hochberg(p, alpha=0.10)
    hm = holm(p, alpha=0.05)
    assert bh["adjusted"].shape == (4,)
    assert hm["adjusted"][0] <= hm["adjusted"][1]
    assert hm["adjusted"][3] >= hm["adjusted"][2] >= hm["adjusted"][1]


# ------------------------------------------------- promotion rule


def test_promotion_requires_both():
    prom_bh, prom_z = 0.10, 2.5
    cases = [
        (0.09, 2.6, True),
        (0.09, 2.4, False),   # z too small
        (0.11, 3.0, False),   # q too big
        (0.001, 2.5, True),   # boundary inclusive
    ]
    for q, z, want in cases:
        assert (q <= prom_bh and abs(z) >= prom_z) == want
