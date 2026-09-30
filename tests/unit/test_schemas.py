"""Unit tests for pydantic contracts and CSV I/O."""
import pytest
from pydantic import ValidationError

from fortuna.schemas.csv_io import dump_csv, load_csv
from fortuna.schemas.draws import Draw
from fortuna.schemas.regimes import GameRegime
from fortuna.schemas.sources import Source


def _regime_kwargs(**over):
    base = dict(
        regime_id="PB-R001", game_id="powerball", statistical_regime_id="PB-S01",
        main_ball_count=5, main_ball_min=1, main_ball_max=69,
        special_ball_count=1, special_ball_min=1, special_ball_max=26,
        drawing_days="wed;sat",
    )
    base.update(over)
    return base


def test_regime_days_parse_and_lowercase():
    r = GameRegime(**_regime_kwargs(drawing_days="Wed; SAT"))
    assert r.drawing_days == ["wed", "sat"]


def test_regime_rejects_bad_day():
    with pytest.raises(ValidationError):
        GameRegime(**_regime_kwargs(drawing_days="wed;funday"))


def test_regime_rejects_special_bounds_without_count():
    with pytest.raises(ValidationError):
        GameRegime(**_regime_kwargs(special_ball_count=0))


def test_regime_rejects_inverted_range():
    with pytest.raises(ValidationError):
        GameRegime(**_regime_kwargs(main_ball_max=10, main_ball_min=20))


def test_regime_rejects_inverted_span():
    with pytest.raises(ValidationError):
        GameRegime(**_regime_kwargs(
            first_affected_draw="2020-01-10", last_affected_draw="2020-01-01"))


def test_regime_id_pattern():
    with pytest.raises(ValidationError):
        GameRegime(**_regime_kwargs(regime_id="PB-R1"))
    with pytest.raises(ValidationError):
        GameRegime(**_regime_kwargs(regime_id="pb-R001"))


def test_csv_roundtrip(tmp_path):
    rows = [
        Source(source_id="SRC-A", game="powerball", publisher="x",
               source_type="official_rules", url="https://example.com",
               authority_tier=1),
        Source(source_id="SRC-B", game="multi", publisher="y",
               source_type="annual_report", url="https://example.org",
               authority_tier=2, notes="contains; semicolons? no, commas, yes"),
    ]
    p = tmp_path / "s.csv"
    dump_csv(p, rows)
    back = load_csv(p, Source)
    assert back == rows


def test_csv_empty_cell_is_none(tmp_path):
    p = tmp_path / "s.csv"
    dump_csv(p, [Source(source_id="SRC-A", game="powerball", publisher="x",
                        source_type="official_rules", url="u", authority_tier=1)])
    back = load_csv(p, Source)
    assert back[0].notes is None


def test_draw_requires_regime_id():
    with pytest.raises(ValidationError):
        Draw(draw_id="PB-D-2020-01-01", game_id="powerball", draw_date="2020-01-01",
             main_numbers=[1, 2, 3, 4, 5], special_ball=6)


def test_draw_id_pattern():
    d = Draw(draw_id="PB-D-2020-01-01", game_id="powerball", regime_id="PB-R009",
             draw_date="2020-01-01", main_numbers=[1, 2, 3, 4, 5], special_ball=6)
    nums = d.to_draw_numbers()
    assert len(nums) == 6 and nums[-1].ball_type.value == "special"
    assert [n.number for n in nums[:5]] == [1, 2, 3, 4, 5]
