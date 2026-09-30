"""Generic quarantine protection: an unresolved MATERIAL boundary must make
automatic assignment and pooling impossible inside the uncertain window —
without quarantining dates provably on either side."""
from datetime import date

import pytest

from fortuna.rules.assign import (
    UnverifiedBoundaryError,
    assert_poolable,
    assign_regime,
    statistical_groups,
)
from fortuna.schemas.draws import Draw, DrawValidationStatus
from fortuna.schemas.regimes import GameRegime
from fortuna.validation.draw_validator import validate_draws


def _mk_quarantined_game():
    """Synthetic game ZZ: a matrix change whose effective draw is unresolved
    between 2001-01-03 and 2001-01-06 (Wed/Sat schedule)."""
    old = GameRegime(
        regime_id="ZZ-R001", game_id="zz", statistical_regime_id="ZZ-S01",
        change_classification="baseline",
        first_affected_draw=date(2000, 1, 1), last_affected_draw=date(2000, 12, 30),
        main_ball_count=5, main_ball_min=1, main_ball_max=50,
        special_ball_count=1, special_ball_min=1, special_ball_max=25,
        drawing_days=["wed", "sat"],
    )
    new = GameRegime(
        regime_id="ZZ-R002", game_id="zz", statistical_regime_id="ZZ-S02",
        change_classification="matrix", verification_status="partially_verified",
        # earliest candidate draw — boundary is NOT proven
        first_affected_draw=date(2001, 1, 3),
        # first draw PROVABLY under the new matrix
        first_unambiguous_draw=date(2001, 1, 6),
        last_affected_draw=None,
        main_ball_count=5, main_ball_min=1, main_ball_max=50,
        special_ball_count=1, special_ball_min=1, special_ball_max=36,
        drawing_days=["wed", "sat"],
    )
    return [old, new]


def test_quarantine_blocks_assignment_inside_window():
    regs = _mk_quarantined_game()
    with pytest.raises(UnverifiedBoundaryError):
        assign_regime("zz", date(2001, 1, 3), regs)


def test_unambiguous_sides_still_assign():
    regs = _mk_quarantined_game()
    assert assign_regime("zz", date(2000, 12, 30), regs).regime_id == "ZZ-R001"
    assert assign_regime("zz", date(2001, 1, 6), regs).regime_id == "ZZ-R002"


def test_quarantined_draw_cannot_pool():
    regs = _mk_quarantined_game()
    bad = Draw(draw_id="ZZ-D-2001-01-03", game_id="zz", regime_id="ZZ-R002",
               draw_date=date(2001, 1, 3), main_numbers=[1, 2, 3, 4, 5],
               special_ball=30)
    good_old = Draw(draw_id="ZZ-D-2000-12-30", game_id="zz", regime_id="ZZ-R001",
                    draw_date=date(2000, 12, 30), main_numbers=[1, 2, 3, 4, 5],
                    special_ball=10)
    # quarantined draw alone can't even be grouped under its claimed regime
    with pytest.raises(UnverifiedBoundaryError):
        statistical_groups([bad], regs)
    with pytest.raises(UnverifiedBoundaryError):
        assert_poolable([bad, good_old], regs)
    # and without it, pooling still works
    assert_poolable([good_old], regs)


def test_quarantined_draw_fails_validation():
    regs = _mk_quarantined_game()
    bad = Draw(draw_id="ZZ-D-2001-01-03", game_id="zz", regime_id="ZZ-R002",
               draw_date=date(2001, 1, 3), main_numbers=[1, 2, 3, 4, 5],
               special_ball=30)
    results = validate_draws([bad], regs, collect=True)
    assert any("unresolved" in r or "quarantined" in r
               for r in results[bad.draw_id])
    assert bad.validation_status == DrawValidationStatus.REJECTED


def test_mm_r002_partially_verified_schedule_stays_poolable(regimes):
    """MM-R002 is partially_verified but schedule-only: it shares pool MM-S01,
    so draws on its era must NOT be quarantined."""
    r = assign_regime("mega_millions", date(1998, 6, 5), regimes)
    assert r.regime_id == "MM-R002"
    assert r.statistical_regime_id == "MM-S01"
    d = _mm_draw("MM-R002", date(1998, 6, 5))
    assert_poolable([d], regimes)


def _mm_draw(rid, d):
    return Draw(draw_id=f"MM-D-{d.isoformat()}", game_id="mega_millions",
                regime_id=rid, draw_date=d, main_numbers=[1, 2, 3, 4, 5],
                special_ball=10)


def test_no_real_regime_has_unneeded_quarantine(regimes):
    """In the shipped inventory, quarantine windows exist only where a
    material boundary is genuinely unresolved."""
    for r in regimes:
        if r.first_unambiguous_draw is not None:
            assert r.verification_status.value != "verified", r.regime_id
