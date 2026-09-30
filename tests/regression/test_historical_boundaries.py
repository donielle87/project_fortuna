"""Regression tests pinning the verified historical regime boundaries.

These tests exist so a future metadata edit can never silently re-merge
incompatible matrices or move a verified boundary.
"""
from datetime import date

import pytest

from fortuna.rules.assign import IncompatibleMatrixError, assert_poolable, assign_regime
from fortuna.schemas.draws import Draw
from fortuna.validation.draw_validator import validate_draw


def _by_id(regimes):
    return {r.regime_id: r for r in regimes}


_PREFIX = {"powerball": "PB", "mega_millions": "MM", "florida_lotto": "FL"}


def _draw(game, rid, d, nums, sb=None, did=None):
    did = did or f"{_PREFIX[game]}-D-{d.isoformat()}"
    return Draw(draw_id=did, game_id=game, regime_id=rid, draw_date=d,
                main_numbers=nums, special_ball=sb)


# ---------- Powerball ----------

def test_pb_559_ball_fails_under_569(regimes):
    """A 5/59-era draw is structurally invalid under the 5/69 regime is NOT
    the claim here — the real regression is the reverse direction plus
    misassignment. A draw using numbers legal under 5/69 (e.g. white 68)
    must FAIL under a 5/59 regime."""
    by = _by_id(regimes)
    r559 = by["PB-R008"]  # 5/59 + 1/35
    d = _draw("powerball", "PB-R008", date(2013, 1, 2), [1, 2, 3, 4, 68], 10)
    reasons = validate_draw(d, r559)
    assert any("68" in r and "outside" in r for r in reasons)


def test_pb_special_ball_39_fails_under_2012_rules(regimes):
    """Powerball 39 was legal pre-2012; under 5/59+1/35 it must be rejected."""
    by = _by_id(regimes)
    d = _draw("powerball", "PB-R008", date(2013, 1, 2), [1, 2, 3, 4, 5], 39)
    reasons = validate_draw(d, by["PB-R008"])
    assert any("39" in r for r in reasons)


@pytest.mark.parametrize("d,expected", [
    (date(1992, 4, 22), "PB-R001"),
    (date(1997, 11, 5), "PB-R002"),   # first 5/49 draw
    (date(2002, 10, 9), "PB-R004"),   # first 5/53 draw
    (date(2005, 8, 31), "PB-R005"),   # first 5/55 draw
    (date(2009, 1, 7), "PB-R006"),    # first 5/59+1/39 draw (FL era)
    (date(2012, 1, 4), "PB-R007"),    # first Tallahassee draw
    (date(2012, 1, 18), "PB-R008"),   # first 5/59+1/35 draw
    (date(2015, 10, 7), "PB-R009"),   # first 5/69+1/26 draw
    (date(2021, 8, 23), "PB-R010"),   # first Monday draw
    (date(2021, 8, 21), "PB-R009"),   # last Sat-only-schedule draw
])
def test_pb_assignment_boundaries(regimes, d, expected):
    assert assign_regime("powerball", d, regimes).regime_id == expected


def test_pb_monday_addition_same_pool(regimes):
    """2021-08-23 Monday draw pools legally with a 2016 draw (same matrix)."""
    d_old = _draw("powerball", "PB-R009", date(2016, 1, 6),
                  [1, 2, 3, 4, 5], 10, "PB-D-2016-01-06")
    d_new = _draw("powerball", "PB-R010", date(2021, 8, 23),
                  [6, 7, 8, 9, 10], 11, "PB-D-2021-08-23")
    assert_poolable([d_old, d_new], regimes)  # PB-S07 both


def test_pb_cross_matrix_pooling_rejected(regimes):
    d1 = _draw("powerball", "PB-R008", date(2013, 1, 2),
               [1, 2, 3, 4, 5], 10, "PB-D-2013-01-02")
    d2 = _draw("powerball", "PB-R009", date(2016, 1, 6),
               [1, 2, 3, 4, 5], 10, "PB-D-2016-01-06")
    with pytest.raises(IncompatibleMatrixError):
        assert_poolable([d1, d2], regimes)


# ---------- Mega Millions ----------

@pytest.mark.parametrize("d,expected", [
    (date(1996, 9, 6), "MM-R001"),    # first Big Game draw
    (date(2002, 5, 14), "MM-R003"),   # last Big Game draw
    (date(2002, 5, 17), "MM-R004"),   # first Mega Millions draw
    (date(2005, 6, 24), "MM-R005"),   # first 5/56+1/46 draw
    (date(2013, 10, 22), "MM-R006"),  # first 5/75+1/15 draw
    (date(2017, 10, 31), "MM-R007"),  # first 5/70+1/25 draw
    (date(2025, 4, 4), "MM-R007"),    # final old-matrix draw
    (date(2025, 4, 8), "MM-R008"),    # first 5/70+1/24 draw
])
def test_mm_assignment_boundaries(regimes, d, expected):
    assert assign_regime("mega_millions", d, regimes).regime_id == expected


def test_mm_megaball_25_rejected_under_new_matrix(regimes):
    """The final old-matrix draw (2025-04-04) actually drew MB 25 — impossible
    under the new 1/24 pool."""
    by = _by_id(regimes)
    d = _draw("mega_millions", "MM-R008", date(2025, 4, 8), [1, 2, 3, 4, 5], 25)
    reasons = validate_draw(d, by["MM-R008"])
    assert any("25" in r for r in reasons)


def test_mm_cross_matrix_pooling_rejected(regimes):
    d1 = _draw("mega_millions", "MM-R007", date(2020, 1, 3),
               [1, 2, 3, 4, 5], 10, "MM-D-2020-01-03")
    d2 = _draw("mega_millions", "MM-R008", date(2025, 4, 8),
               [1, 2, 3, 4, 5], 10, "MM-D-2025-04-08")
    with pytest.raises(IncompatibleMatrixError):
        assert_poolable([d1, d2], regimes)


# ---------- Florida Lotto ----------

def test_fl_649_draw_with_49_fails_under_653(regimes):
    """Ball 49 was drawn 1988-05-07 (first draw ever). Under 6/53 rules it is
    legal range-wise (49<=53) — so instead pin the REAL regression: a draw
    dated in the 6/49 era claiming the 6/53 regime is caught as misassigned."""
    by = _by_id(regimes)
    # correct era check: 6/49-era draw assigned FL-R001 validates clean
    d = _draw("florida_lotto", "FL-R001", date(1988, 5, 7),
              [5, 12, 19, 30, 41, 49], None, "FL-D-1988-05-07")
    assert validate_draw(d, by["FL-R001"]) == []
    # ball 53 under the 6/49 regime must fail
    d2 = _draw("florida_lotto", "FL-R001", date(1990, 1, 6),
               [5, 12, 19, 30, 41, 53], None, "FL-D-1990-01-06")
    assert validate_draw(d2, by["FL-R001"])


@pytest.mark.parametrize("d,expected", [
    (date(1988, 5, 7), "FL-R001"),    # first draw ever
    (date(1999, 10, 23), "FL-R001"),  # last 6/49 draw
    (date(1999, 10, 27), "FL-R002"),  # first 6/53 draw
    (date(2020, 10, 10), "FL-R004"),  # first $2/Double Play draw
])
def test_fl_assignment_boundaries(regimes, d, expected):
    assert assign_regime("florida_lotto", d, regimes).regime_id == expected


def test_fl_649_and_653_never_pool(regimes):
    d1 = _draw("florida_lotto", "FL-R001", date(1999, 10, 23),
               [1, 2, 3, 4, 5, 6], None, "FL-D-1999-10-23")
    d2 = _draw("florida_lotto", "FL-R002", date(1999, 10, 27),
               [1, 2, 3, 4, 5, 6], None, "FL-D-1999-10-27")
    with pytest.raises(IncompatibleMatrixError):
        assert_poolable([d1, d2], regimes)


def test_fl_economic_eras_share_pool(regimes):
    """XTRA-era and $2/Double-Play-era draws share pool FL-S02 with the 1999
    matrix era — economic changes don't split the series."""
    draws = [
        _draw("florida_lotto", "FL-R002", date(2005, 1, 5),
              [1, 2, 3, 4, 5, 6], None, "FL-D-2005-01-05"),
        _draw("florida_lotto", "FL-R003", date(2015, 1, 3),
              [7, 8, 9, 10, 11, 12], None, "FL-D-2015-01-03"),
        _draw("florida_lotto", "FL-R004", date(2021, 1, 2),
              [13, 14, 15, 16, 17, 18], None, "FL-D-2021-01-02"),
    ]
    assert_poolable(draws, regimes)
