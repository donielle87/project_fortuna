"""Unit tests for the draw validator."""
from datetime import date

from fortuna.schemas.draws import Draw, DrawValidationStatus
from fortuna.schemas.regimes import GameRegime
from fortuna.validation.draw_validator import validate_draw, validate_draws


def regime(**over):
    base = dict(
        regime_id="PB-R009", game_id="powerball", statistical_regime_id="PB-S07",
        change_classification="matrix",
        first_affected_draw=date(2015, 10, 7), last_affected_draw=date(2021, 8, 21),
        main_ball_count=5, main_ball_min=1, main_ball_max=69,
        special_ball_count=1, special_ball_min=1, special_ball_max=26,
        drawing_days=["wed", "sat"],
    )
    base.update(over)
    return GameRegime(**base)


def draw(**over):
    base = dict(
        draw_id="PB-D-2020-06-03", game_id="powerball", regime_id="PB-R009",
        draw_date=date(2020, 6, 3), main_numbers=[1, 2, 3, 4, 5], special_ball=26,
    )
    base.update(over)
    return Draw(**base)


def test_valid_draw_no_reasons():
    assert validate_draw(draw(), regime()) == []


def test_out_of_range_main_number():
    rs = validate_draw(draw(main_numbers=[1, 2, 3, 4, 70]), regime())
    assert any("outside regime range" in r for r in rs)


def test_duplicate_main_numbers():
    rs = validate_draw(draw(main_numbers=[5, 5, 3, 4, 2]), regime())
    assert any("duplicate" in r for r in rs)


def test_wrong_count():
    rs = validate_draw(draw(main_numbers=[1, 2, 3, 4]), regime())
    assert any("expected 5" in r for r in rs)


def test_special_ball_out_of_range():
    rs = validate_draw(draw(special_ball=27), regime())
    assert any("special ball 27" in r for r in rs)


def test_special_ball_can_equal_main_number():
    # separate pool: special=5 with 5 among whites is legal
    assert validate_draw(draw(special_ball=5), regime()) == []


def test_no_special_ball_game():
    r = regime(regime_id="FL-R004", game_id="florida_lotto",
               statistical_regime_id="FL-S02", main_ball_count=6,
               main_ball_max=53, special_ball_count=0,
               special_ball_min=None, special_ball_max=None)
    d = Draw(draw_id="FL-D-2020-10-10", game_id="florida_lotto",
             regime_id="FL-R004", draw_date=date(2020, 10, 10),
             main_numbers=[1, 2, 3, 4, 5, 6])
    assert validate_draw(d, r) == []
    # and a draw supplying a special ball is rejected
    d2 = Draw(draw_id="FL-D-2020-10-14", game_id="florida_lotto",
              regime_id="FL-R004", draw_date=date(2020, 10, 14),
              main_numbers=[1, 2, 3, 4, 5, 6], special_ball=9)
    assert validate_draw(d2, r)


def test_wrong_regime_claim_detected(regimes):
    """A draw dated in the 5/69 era claiming the 5/59 regime is caught."""
    d = Draw(draw_id="PB-D-2016-01-06", game_id="powerball",
             regime_id="PB-R008",  # claims 5/59+1/35 era
             draw_date=date(2016, 1, 6),
             main_numbers=[1, 2, 3, 4, 5], special_ball=20)
    results = validate_draws([d], regimes, collect=True)
    assert any("governed by PB-R009" in r for r in results[d.draw_id])
    assert d.validation_status == DrawValidationStatus.REJECTED


def test_validate_draws_raises_unless_collect(regimes):
    d = Draw(draw_id="PB-D-2016-01-06", game_id="powerball",
             regime_id="PB-R009", draw_date=date(2016, 1, 6),
             main_numbers=[1, 2, 3, 4, 70], special_ball=20)  # 70 > 69
    import pytest
    with pytest.raises(ValueError):
        validate_draws([d], regimes)
    # with collect, no raise and reasons returned
    res = validate_draws([d], regimes, collect=True)
    assert res[d.draw_id]
