"""Unit tests for the rules engine: assignment, pooling guard, integrity."""
from datetime import date

import pytest

from fortuna.rules.assign import (
    AmbiguousRegimeError,
    IncompatibleMatrixError,
    NoRegimeError,
    assert_poolable,
    assign_regime,
    statistical_groups,
)
from fortuna.rules.registry import RegimeIntegrityError, check_regime_integrity
from fortuna.schemas.draws import Draw
from fortuna.schemas.regimes import GameRegime


def mk(game="zz", rid="ZZ-R001", pool="ZZ-S01", cls="baseline",
       start=date(2000, 1, 1), end=None, matrix=None):
    m = dict(main_ball_count=5, main_ball_min=1, main_ball_max=69,
             special_ball_count=1, special_ball_min=1, special_ball_max=26,
             sampling_without_replacement=True)
    if matrix:
        m.update(matrix)
    return GameRegime(regime_id=rid, game_id=game, statistical_regime_id=pool,
                      change_classification=cls, first_affected_draw=start,
                      last_affected_draw=end, drawing_days=["sat"], **m)


def mkdraw(rid="ZZ-R001", d=date(2000, 1, 1), nums=(1, 2, 3, 4, 5), sb=6,
           did="ZZ-D-2000-01-01", game="zz"):
    return Draw(draw_id=did, game_id=game, regime_id=rid, draw_date=d,
                main_numbers=list(nums), special_ball=sb)


def test_assign_regime_hits_correct_era():
    r1 = mk(rid="ZZ-R001", start=date(2000, 1, 1), end=date(2009, 12, 31))
    r2 = mk(rid="ZZ-R002", pool="ZZ-S02", cls="matrix",
            start=date(2010, 1, 1), matrix={"main_ball_max": 70})
    got = assign_regime("zz", date(2005, 6, 15), [r1, r2])
    assert got.regime_id == "ZZ-R001"
    assert assign_regime("zz", date(2010, 1, 1), [r1, r2]).regime_id == "ZZ-R002"


def test_assign_regime_no_coverage_raises():
    r = mk(start=date(2000, 1, 1), end=date(2000, 12, 31))
    with pytest.raises(NoRegimeError):
        assign_regime("zz", date(2001, 1, 1), [r])


def test_assign_regime_ambiguous_raises():
    r1 = mk(rid="ZZ-R001", start=date(2000, 1, 1), end=None)
    r2 = mk(rid="ZZ-R002", pool="ZZ-S02", cls="matrix", start=date(2000, 6, 1),
            matrix={"main_ball_max": 70})
    with pytest.raises(AmbiguousRegimeError):
        assign_regime("zz", date(2000, 6, 15), [r1, r2])


def test_assign_regime_ignores_other_games():
    r = mk(game="zz", rid="ZZ-R001")
    with pytest.raises(NoRegimeError):
        assign_regime("gg", date(2000, 6, 15), [r])


def test_poolable_same_group_via_different_legal_regimes():
    r1 = mk(rid="ZZ-R001", start=date(2000, 1, 1), end=date(2000, 6, 30))
    r2 = mk(rid="ZZ-R002", cls="economic", start=date(2000, 7, 1))
    draws = [mkdraw(rid="ZZ-R001", d=date(2000, 1, 1), did="ZZ-D-2000-01-01"),
             mkdraw(rid="ZZ-R002", d=date(2000, 7, 1), did="ZZ-D-2000-07-01")]
    assert_poolable(draws, [r1, r2])  # same pool group ZZ-S01 -> OK


def test_pool_guard_fails_loudly_across_groups():
    r1 = mk(rid="ZZ-R001", start=date(2000, 1, 1), end=date(2009, 12, 31))
    r2 = mk(rid="ZZ-R002", pool="ZZ-S02", cls="matrix",
            start=date(2010, 1, 1), matrix={"main_ball_max": 70})
    draws = [mkdraw(rid="ZZ-R001", d=date(2000, 1, 1), did="ZZ-D-2000-01-01"),
             mkdraw(rid="ZZ-R002", d=date(2010, 1, 1), did="ZZ-D-2010-01-01")]
    with pytest.raises(IncompatibleMatrixError):
        assert_poolable(draws, [r1, r2])


def test_pool_guard_unknown_regime_fails():
    r = mk()
    d = mkdraw(rid="ZZ-R999")
    with pytest.raises(NoRegimeError):
        assert_poolable([d], [r])


def test_statistical_groups_buckets_correctly():
    r1 = mk(rid="ZZ-R001", start=date(2000, 1, 1), end=date(2000, 6, 30))
    r2 = mk(rid="ZZ-R002", cls="economic", start=date(2000, 7, 1),
            end=date(2000, 12, 31))
    r3 = mk(rid="ZZ-R003", pool="ZZ-S02", cls="matrix", start=date(2001, 1, 1),
            matrix={"main_ball_max": 70})
    draws = [mkdraw(rid="ZZ-R001", d=date(2000, 1, 1), did="ZZ-D-2000-01-01"),
             mkdraw(rid="ZZ-R002", d=date(2000, 7, 1), did="ZZ-D-2000-07-01"),
             mkdraw(rid="ZZ-R003", d=date(2001, 1, 6), did="ZZ-D-2001-01-06")]
    groups = statistical_groups(draws, [r1, r2, r3])
    assert set(groups) == {"ZZ-S01", "ZZ-S02"}
    assert len(groups["ZZ-S01"]) == 2


def test_integrity_duplicate_id_fails():
    r1 = mk(rid="ZZ-R001", end=date(2000, 6, 30))
    r2 = mk(rid="ZZ-R001", cls="economic", start=date(2000, 7, 1))
    with pytest.raises(RegimeIntegrityError):
        check_regime_integrity([r1, r2])


def test_integrity_mixed_matrix_in_pool_group_fails():
    r1 = mk(rid="ZZ-R001", end=date(2000, 6, 30))
    r2 = mk(rid="ZZ-R002", cls="economic", start=date(2000, 7, 1),
            matrix={"main_ball_max": 70})  # different matrix, same pool
    with pytest.raises(RegimeIntegrityError, match="sampling-equivalent"):
        check_regime_integrity([r1, r2])


def test_integrity_material_change_reusing_group_fails():
    r1 = mk(rid="ZZ-R001", end=date(2000, 6, 30))
    r2 = mk(rid="ZZ-R002", cls="matrix", start=date(2000, 7, 1),
            matrix={"main_ball_max": 70})
    # matrix change claims materiality but we reused ZZ-S01 with a different
    # matrix -> caught by the pool-group consistency check first
    with pytest.raises(RegimeIntegrityError):
        check_regime_integrity([r1, r2])


def test_integrity_nonmaterial_change_new_group_fails():
    r1 = mk(rid="ZZ-R001", end=date(2000, 6, 30))
    r2 = mk(rid="ZZ-R002", pool="ZZ-S02", cls="schedule", start=date(2000, 7, 1))
    with pytest.raises(RegimeIntegrityError, match="non-material"):
        check_regime_integrity([r1, r2])


def test_integrity_overlap_fails():
    r1 = mk(rid="ZZ-R001", end=date(2000, 12, 31))
    r2 = mk(rid="ZZ-R002", pool="ZZ-S02", cls="matrix", start=date(2000, 6, 1),
            matrix={"main_ball_max": 70})
    with pytest.raises(RegimeIntegrityError, match="overlapping"):
        check_regime_integrity([r1, r2])


def test_integrity_gap_without_draw_day_ok():
    # Sat -> Wed transition: gap days Sun-Tue contain no scheduled draw
    r1 = mk(rid="ZZ-R001", end=date(2000, 1, 1))  # Saturday
    r2 = mk(rid="ZZ-R002", pool="ZZ-S02", cls="matrix", start=date(2000, 1, 5),
            matrix={"main_ball_max": 70})
    r2.drawing_days = ["wed"]
    warnings = check_regime_integrity([r1, r2])
    assert warnings == []
