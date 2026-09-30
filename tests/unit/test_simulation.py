"""Phase 2 unit tests: engine, exact baselines, seeding, segments, utilities."""

import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime
from fortuna.simulation import exact
from fortuna.simulation.engine import (
    draw_mains,
    draw_mains_ordered,
    simulate_history,
)
from fortuna.simulation.matrix import RegimeMatrix, statistical_matrices
from fortuna.simulation.observation import contiguous_segments
from fortuna.simulation.seeding import make_rng, scope_entropy
from fortuna.simulation.statistics import (
    CATALOG,
    applicable_statistics,
    history_statistics,
    segment_start_mask,
)
from fortuna.statistics.multiple_testing import benjamini_hochberg, holm
from fortuna.statistics.pvalues import mc_pvalue

ROOT = Path(__file__).resolve().parents[2]
PB_S07 = RegimeMatrix("PB-S07", "powerball", 5, 1, 69, 1, 1, 26)
MM_S07 = RegimeMatrix("MM-S07", "mega_millions", 5, 1, 70, 1, 1, 24)
FL_S02 = RegimeMatrix("FL_S02", "florida_lotto", 6, 1, 53)


# ---------------- exact combinatorics ----------------

def test_sample_space_known_jackpots():
    # PB-S07: C(69,5)*26 = 292,201,338 ; MM-S07 (2025 rules): C(70,5)*24
    assert exact.jackpot_sample_space(PB_S07) == 292_201_338
    assert exact.jackpot_sample_space(MM_S07) == 290_472_336
    # FL-S02: C(53,6) = 22,957,480
    assert exact.jackpot_sample_space(FL_S02) == 22_957_480


def test_jackpot_odds_match_registry():
    regs = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)
    mats = statistical_matrices(regs)
    checked = 0
    for r in regs:
        if r.jackpot_odds:
            digits = "".join(c for c in str(r.jackpot_odds) if c.isdigit())
            if digits:
                assert int(digits) == exact.jackpot_sample_space(
                    mats[r.statistical_regime_id]
                ), r.regime_id
                checked += 1
    assert checked > 0


def test_inclusion_pair_triple_probs():
    assert exact.inclusion_prob(69, 5) == pytest.approx(5 / 69)
    assert exact.pair_prob(69, 5) == pytest.approx(math.comb(5, 2) / math.comb(69, 2))
    assert exact.triple_prob(69, 5) == pytest.approx(
        math.comb(5, 3) / math.comb(69, 3)
    )
    assert exact.triple_prob(4, 2) == 0.0


def test_overlap_pmf_is_distribution():
    pmf = exact.overlap_pmf(69, 5)
    assert pmf.sum() == pytest.approx(1.0)
    # E[overlap] = K^2 / N
    mean = float((np.arange(6) * pmf).sum())
    assert mean == pytest.approx(25 / 69)
    # symmetric support j=0..K
    assert len(pmf) == 6


def test_overlap_matches_ticket_match():
    np.testing.assert_allclose(
        exact.ticket_match_pmf(PB_S07), exact.overlap_pmf(69, 5)
    )


def test_odd_even_pmf_hypergeometric():
    pmf = exact.odd_even_pmf(1, 69, 5)  # 35 odd, 34 even
    assert pmf.sum() == pytest.approx(1.0)
    n_odd = 35
    denom = math.comb(69, 5)
    for j in range(6):
        exp = math.comb(n_odd, j) * math.comb(34, 5 - j) / denom
        assert pmf[j] == pytest.approx(exp)


def test_special_repeat_and_no_special():
    assert exact.special_repeat_prob(PB_S07) == pytest.approx(1 / 26)
    assert exact.special_repeat_prob(FL_S02) is None
    assert not FL_S02.has_special


def test_candidate_pool_hypergeometric():
    # pool of 12 from N=69, K=5: P(X>=3) computed exactly
    pmf = exact.candidate_pool_pmf(69, 5, 12)
    assert pmf.sum() == pytest.approx(1.0)
    tail = exact.candidate_pool_tail(69, 5, 12, 3)
    assert tail == pytest.approx(float(pmf[3:].sum()))
    # sanity: E[X] = m*K/N
    mean = float((np.arange(len(pmf)) * pmf).sum())
    assert mean == pytest.approx(12 * 5 / 69)


def test_ticket_joint_match_pmf():
    joint = exact.ticket_joint_match_pmf(PB_S07)
    assert joint.sum() == pytest.approx(1.0)
    # special hit column has mass 1/26
    assert joint[:, 1].sum() == pytest.approx(1 / 26)
    joint_fl = exact.ticket_joint_match_pmf(FL_S02)
    assert joint_fl[:, 1].sum() == 0.0
    assert joint_fl[:, 0].sum() == pytest.approx(1.0)


def test_inclusion_covariance_negative():
    mom = exact.inclusion_moments(69, 5)
    assert mom["p"] == pytest.approx(5 / 69)
    assert mom["p_pair"] == pytest.approx(5 * 4 / (69 * 68))
    assert mom["cov"] < 0
    assert mom["var"] == pytest.approx(5 / 69 * 64 / 69)


def test_sum_pmf_distribution():
    pmf = exact.sum_pmf(1, 49, 6)
    assert sum(pmf.values()) == pytest.approx(1.0)
    mean = sum(s * p for s, p in pmf.items())
    assert mean == pytest.approx(6 * 25)  # K * (1+49)/2


def test_range_pmf_distribution():
    pmf = exact.range_pmf(1, 49, 6)
    assert sum(pmf.values()) == pytest.approx(1.0)
    assert min(pmf) == 5 and max(pmf) == 48


# ---------------- engine ----------------

def test_draws_valid_without_replacement():
    rng = make_rng(20260930, "F-E001", "test|engine|basic")
    mains, specials = simulate_history(rng, PB_S07, 500)
    assert mains.shape == (500, 5)
    for row in mains:
        assert len(set(row)) == 5
        assert 1 <= row.min() and row.max() <= 69
        assert (np.diff(row) > 0).all()  # sorted
    assert specials is not None
    assert specials.min() >= 1 and specials.max() <= 26


def test_no_special_game_returns_none():
    rng = make_rng(20260930, "F-E001", "test|engine|nospecial")
    mains, specials = simulate_history(rng, FL_S02, 100)
    assert specials is None
    assert mains.shape == (100, 6)


def test_ordered_draws_are_permutations():
    rng = make_rng(20260930, "F-E001", "test|engine|ordered")
    od = draw_mains_ordered(rng, PB_S07, 200)
    for row in od:
        assert len(set(row)) == 5
    # ordered rows are generally NOT sorted (physical order differs)
    assert not (np.diff(od, axis=1) > 0).all(axis=1).all()


def test_deterministic_seeding_reproduces():
    r1 = make_rng(20260930, "F-E001", "g|r|HISTORIES|batch1")
    r2 = make_rng(20260930, "F-E001", "g|r|HISTORIES|batch1")
    np.testing.assert_array_equal(draw_mains(r1, PB_S07, 50), draw_mains(r2, PB_S07, 50))


def test_child_streams_independent():
    r1 = make_rng(20260930, "F-E001", "g|r|HISTORIES|batch1")
    r2 = make_rng(20260930, "F-E001", "g|r|HISTORIES|batch2")
    a, b = draw_mains(r1, PB_S07, 200), draw_mains(r2, PB_S07, 200)
    assert not np.array_equal(a, b)


def test_scope_entropy_stable():
    assert scope_entropy("F-E001", "a|b|c") == scope_entropy("F-E001", "a|b|c")
    assert scope_entropy("F-E001", "a|b|c") != scope_entropy("F-E001", "a|b|d")


def test_all_16_regimes_build():
    regs = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)
    mats = statistical_matrices(regs)
    assert len(mats) == 16
    for sid, m in mats.items():
        rng = make_rng(1, "F-E001", f"t|{sid}|x")
        mains, sp = simulate_history(rng, m, 10)
        assert mains.shape == (10, m.main_count)
        assert (sp is None) == (not m.has_special)


# ---------------- segments ----------------

def test_segments_break_on_missing():
    timeline = [date(2020, 1, d) for d in range(1, 11)]
    eligible = set(timeline) - {date(2020, 1, 5)}
    segs = contiguous_segments(timeline, eligible)
    assert [len(s) for s in segs] == [4, 5]


def test_segments_break_on_ineligible_draw_position():
    # an excluded draw position (missing or ineligible) breaks continuity
    timeline = [date(2020, 1, d) for d in (1, 2, 3, 4)]
    elig = {date(2020, 1, 1), date(2020, 1, 2), date(2020, 1, 4)}
    segs = contiguous_segments(timeline, elig)
    assert [len(s) for s in segs] == [2, 1]


def test_offschedule_eligible_draw_is_part_of_timeline():
    # an eligible draw on a non-scheduled date is a real observation and
    # does not itself break continuity; it extends the sequence
    timeline = [date(2020, 1, 1), date(2020, 1, 3), date(2020, 1, 4),
                date(2020, 1, 5)]
    elig = set(timeline)
    segs = contiguous_segments(timeline, elig)
    assert [len(s) for s in segs] == [4]


def test_segment_mask_consistency():
    mask = segment_start_mask(7, [3, 4])
    assert np.flatnonzero(mask).tolist() == [0, 3]


def test_sequential_stats_do_not_bridge():
    # construct a history where draw 0 and draw 1 share all balls; if the
    # boundary sat between them, F-S006 must not count that overlap.
    mains = np.array([[1, 2, 3, 4, 5], [1, 2, 3, 4, 5]])
    mtx = RegimeMatrix("X", "florida_lotto", 5, 1, 45)
    stats_joined = history_statistics(mains, None, mtx, [2])
    stats_split = history_statistics(mains, None, mtx, [1, 1])
    assert stats_joined["F-S006"] == 5.0
    assert stats_split["F-S006"] == 0.0


# ---------------- statistics catalog ----------------

def test_catalog_has_13_statistics():
    assert set(CATALOG) == {f"F-S{i:03d}" for i in range(1, 14)}


def test_applicability_special_vs_no_special():
    pb = applicable_statistics(PB_S07)
    fl = applicable_statistics(FL_S02)
    assert "F-S009" in pb and "F-S009" not in fl
    assert "F-S011" in pb and "F-S011" not in fl
    assert len(pb) == 13 and len(fl) == 10


def test_stat_sequential_flags():
    seq = {s for s, spec in CATALOG.items() if spec.sequential}
    assert seq == {"F-S006", "F-S007", "F-S008", "F-S011"}


# ---------------- p-values / multiplicity ----------------

def test_mc_pvalue_correction():
    null = np.arange(100)
    assert mc_pvalue(200, null, "upper") == pytest.approx(1 / 101)
    assert mc_pvalue(50, null, "upper") == pytest.approx(51 / 101)
    assert mc_pvalue(-1, null, "lower") == pytest.approx(1 / 101)
    two = mc_pvalue(5, null, "two-sided")
    assert two == pytest.approx((min(2 * min(6, 95), 100) + 1) / 101)


def test_bh_known_example():
    # classic BH rejections at alpha=0.05 for sorted p's
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205])
    res = benjamini_hochberg(p, 0.05)
    # crit_i = i*0.05/8; largest p_(i)<=crit_i is i=2 -> reject 2
    assert res["rejected"].tolist() == [True, True, False, False, False, False, False, False]
    assert res["adjusted"][0] == pytest.approx(0.001 * 8 / 1)
    assert res["adjusted"][7] == pytest.approx(0.205)


def test_holm_known_example():
    p = np.array([0.01, 0.04, 0.03, 0.002])
    res = holm(p, 0.05)
    # sorted: 0.002(<=.0125) 0.01(<=.0167) 0.03(<=.025? no) 0.04 stop
    assert res["rejected"].tolist() == [True, False, False, True]
    assert res["adjusted"].max() <= 1.0


# ---------------- simulator calibration ----------------

def test_engine_matches_inclusion_prob():
    rng = make_rng(7, "F-E001", "test|calib|incl")
    mains = draw_mains(rng, PB_S07, 50_000)
    freq = np.bincount(mains.ravel() - 1, minlength=69) / 50_000
    p = 5 / 69
    se = math.sqrt(p * (1 - p) / 50_000)
    assert np.abs(freq - p).max() < 5 * se


def test_engine_matches_overlap_pmf():
    rng = make_rng(7, "F-E001", "test|calib|overlap")
    mains = draw_mains(rng, MM_S07, 40_000)
    m = np.zeros((40_000, 70), dtype=bool)
    np.put_along_axis(m, mains - 1, True, axis=1)
    pairs = (m[0::2] & m[1::2]).sum(axis=1)
    obs = np.bincount(pairs, minlength=6) / pairs.size
    pmf = exact.overlap_pmf(70, 5)
    for j in range(6):
        se = math.sqrt(pmf[j] * (1 - pmf[j]) / pairs.size)
        assert abs(obs[j] - pmf[j]) < 5 * se


def test_convergence_v2_accepts_clean_batches():
    from fortuna.simulation.convergence import check_convergence
    rng = np.random.default_rng(0)
    batches = [rng.normal(10, 2, 5000) for _ in range(4)]
    assert check_convergence(batches).status == "CONVERGED"


def test_convergence_v2_rejects_shifted_batch():
    from fortuna.simulation.convergence import check_convergence
    rng = np.random.default_rng(0)
    batches = [rng.normal(10, 2, 5000) for _ in range(3)]
    batches.append(rng.normal(14, 2, 5000))  # genuinely off-distribution
    assert check_convergence(batches).status == "NOT CONVERGED"


def test_convergence_v2_handles_integer_quantiles():
    from fortuna.simulation.convergence import check_convergence
    # integer-valued stat: batch quantiles differing by 1 unit are noise
    rng = np.random.default_rng(0)
    batches = [rng.poisson(20, 5000).astype(float) for _ in range(4)]
    assert check_convergence(batches).status == "CONVERGED"


def _run_stats(mains: np.ndarray, n_pool: int, segs: list[int]) -> dict:
    """Helper: F-S007/F-S008 for an explicit label matrix."""
    mtx = RegimeMatrix("T", "test", mains.shape[1], 1, n_pool)
    out = history_statistics(mains, None, mtx, segs)
    return out["F-S007"], out["F-S008"]


def _brute_runs(mains0: np.ndarray, n_pool: int, segs: list[int]):
    """Deliberately simple reference: per segment, per number, per run."""
    n = mains0.shape[0]
    bounds = [0]
    for L in segs:
        bounds.append(bounds[-1] + L)
    assert bounds[-1] == n
    max_absent = max_present = 0
    for s, e in zip(bounds[:-1], bounds[1:], strict=True):
        for v in range(n_pool):
            run_a = run_p = 0
            for t in range(s, e):
                hit = v in mains0[t]
                run_a = 0 if hit else run_a + 1
                run_p = run_p + 1 if hit else 0
                max_absent = max(max_absent, run_a)
                max_present = max(max_present, run_p)
    return max_absent, max_present


def test_drought_counts_segment_start():
    # absent in all 3 draws of a 3-draw segment -> drought 3, not 2
    mains = np.array([[2, 3, 4, 5, 6]] * 3)  # label 1 never drawn
    d, _ = _run_stats(mains, 45, [3])
    assert d == 3.0


def test_streak_counts_segment_start():
    # present in all 3 draws -> streak 3, not 2
    mains = np.array([[1, 3, 4, 5, 6]] * 3)  # label 1 always drawn
    _, s = _run_stats(mains, 45, [3])
    assert s == 3.0


def test_single_draw_segment_runs():
    absent = np.array([[2, 3, 4, 5, 6]])      # 1 absent -> drought 1
    present = np.array([[1, 3, 4, 5, 6]])     # 1 present -> streak 1
    assert _run_stats(absent, 45, [1])[0] == 1.0
    assert _run_stats(present, 45, [1])[1] == 1.0


def test_run_starting_at_second_segment_start():
    # 2 segments [2,3]; label 1 absent everywhere in segment 2 ->
    # drought contribution 3 (not 2), starting exactly at seg 2 start
    seg1 = np.array([[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]])          # 1 absent in row 2
    seg2 = np.array([[6, 7, 8, 9, 10]] * 3)                       # 1 absent x3
    d, _ = _run_stats(np.vstack([seg1, seg2]), 45, [2, 3])
    assert d == 3.0
    # labels 6-10 present last draw of seg1 AND all of seg2:
    # confined streak = 3; bridging would report 4
    _, s = _run_stats(np.vstack([seg1, seg2]), 45, [2, 3])
    assert s == 3.0


def test_runs_never_bridge_segments():
    # absent run 2 | absent run 3 across a break -> max 3, not 5
    m1 = np.array([[6, 7, 8, 9, 10]] * 2)
    m2 = np.array([[6, 7, 8, 9, 10]] * 3)
    d, _ = _run_stats(np.vstack([m1, m2]), 45, [2, 3])
    assert d == 3.0
    # present run 2 | present run 3 -> max 3, not 5
    p1 = np.array([[1, 2, 3, 4, 5]] * 2)
    p2 = np.array([[1, 2, 3, 4, 5]] * 3)
    _, s = _run_stats(np.vstack([p1, p2]), 45, [2, 3])
    assert s == 3.0


def test_run_stats_against_brute_force():
    rng = np.random.default_rng(42)
    n_pool, k = 20, 4
    for trial in range(200):
        segs = rng.integers(1, 8, size=rng.integers(1, 4)).tolist()
        n = sum(segs)
        mains = np.sort(
            np.stack([rng.choice(n_pool, k, replace=False) + 1
                      for _ in range(n)]), axis=1)
        got = _run_stats(mains, n_pool, segs)
        exp = _brute_runs(mains - 1, n_pool, segs)
        assert got == (float(exp[0]), float(exp[1])), f"trial {trial}"


def test_ordered_draw_position_uniform():
    rng = make_rng(7, "F-E001", "test|calib|order")
    od = draw_mains_ordered(rng, PB_S07, 30_000)
    # each label equally likely in draw position 0
    freq0 = np.bincount(od[:, 0] - 1, minlength=69) / 30_000
    p = 1 / 69
    se = math.sqrt(p * (1 - p) / 30_000)
    assert np.abs(freq0 - p).max() < 5 * se
