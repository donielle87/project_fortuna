"""Phase 3 exploration-only loader + holdout firewall tests."""

import csv
from pathlib import Path

import pytest

from fortuna.analysis.loader import (
    load_exploration_draws,
    load_exploration_histories,
    load_exploration_physical_order,
)

ROOT = Path(__file__).resolve().parents[2]
DRAWS = ROOT / "data/processed/draws.csv"
DRAWNUMS = ROOT / "data/processed/draw_numbers.csv"
EXPL = ROOT / "metadata/phase3_exploration_ids.csv"


def _expl_ids() -> set[str]:
    with EXPL.open(newline="") as f:
        return {r["draw_id"] for r in csv.DictReader(f)}


def _write_fake_store(tmp_path: Path) -> tuple[Path, Path]:
    """Two exploration draws + one holdout row with TRAP outcome data."""
    draws = tmp_path / "draws.csv"
    draws.write_text(
        "draw_id,game_id,regime_id,draw_date,scheduled_datetime,"
        "drawing_identifier,draw_stream,main_numbers,numbers_order,"
        "special_ball,multiplier,jackpot,jackpot_cash_value,jackpot_winners,"
        "drawing_location,machine_id,ball_set_id,source_id,retrieved_at,"
        "raw_artifact_sha256,parser_version,ingestion_version,"
        "validation_status,analysis_eligible,provisional,data_quality_notes,"
        "corroborating_source_ids\n"
        "E1,g,R,2020-01-01,,,main,1;2;3;4;5,physical_draw_order,7,,,,,,,,,,,,valid,true,false,,\n"
        "E2,g,R,2020-01-02,,,main,6;7;8;9;10,physical_draw_order,11,,,,,,,,,,,,valid,true,false,,\n"
        "H1,g,R,2020-01-03,,,main,TRAP_FIELD,physical_draw_order,TRAP,,,,,,,,,,,,valid,true,false,,\n"
    )
    nums = tmp_path / "draw_numbers.csv"
    nums.write_text(
        "draw_id,ball_position,ball_type,number,position_semantics\n"
        "E1,1,main,3,physical_draw_order\n"
        "E1,2,main,1,physical_draw_order\n"
        "E1,3,main,5,physical_draw_order\n"
        "E1,4,main,2,physical_draw_order\n"
        "E1,5,main,4,physical_draw_order\n"
        "E2,1,main,10,physical_draw_order\n"
        "E2,2,main,9,physical_draw_order\n"
        "E2,3,main,8,physical_draw_order\n"
        "E2,4,main,7,physical_draw_order\n"
        "E2,5,main,6,physical_draw_order\n"
        "H1,1,main,NOT_A_NUMBER,physical_draw_order\n"
    )
    return draws, nums


def test_holdout_trap_fields_never_parsed(tmp_path):
    draws, nums = _write_fake_store(tmp_path)
    expl = {"E1", "E2"}
    out = load_exploration_draws(draws, expl)
    assert [d.draw_id for d in out] == ["E1", "E2"]
    assert out[0].mains == (1, 2, 3, 4, 5) and out[0].special == 7
    order = load_exploration_physical_order(nums, expl)
    assert order["E1"] == [3, 1, 5, 2, 4]
    assert order["E2"] == [10, 9, 8, 7, 6]


def test_holdout_id_in_exploration_set_fails(tmp_path):
    draws, nums = _write_fake_store(tmp_path)
    with pytest.raises(ValueError):
        load_exploration_draws(draws, {"E1", "H1"})
    with pytest.raises(ValueError):
        load_exploration_physical_order(nums, {"E1", "H1"})


def test_histories_grouped_by_stat_regime(tmp_path):
    draws, nums = _write_fake_store(tmp_path)
    h = load_exploration_histories(draws, nums, {"E1", "E2"}, {"R": "S"})
    assert set(h) == {"S"}
    assert h["S"].mains == [(1, 2, 3, 4, 5), (6, 7, 8, 9, 10)]
    assert h["S"].physical_order["E1"] == [3, 1, 5, 2, 4]


def test_sorted_order_not_used_for_physical(tmp_path):
    draws, nums = _write_fake_store(tmp_path)
    # add a sorted-order exploration draw with positions rows
    with nums.open("a") as f:
        f.write("E3,1,main,1,source_sorted_order\n")
    with draws.open("a") as f:
        f.write(
            "E3,g,R,2020-01-04,,,main,1;2;3;4;5,source_sorted_order,,,,,,,,,,,,,valid,true,false,,\n"
        )
    order = load_exploration_physical_order(nums, {"E1", "E2", "E3"})
    assert "E3" not in order  # sorted order never substituted


def test_real_exploration_loads_cleanly():
    ids = _expl_ids()
    draws = load_exploration_draws(DRAWS, ids)
    assert len(draws) == len(ids) == 8260
    for d in draws[:200]:
        assert all(isinstance(x, int) for x in d.mains)
        assert len(d.mains) in (5, 6)
        if d.regime_id.startswith("FL"):
            assert d.special is None
        else:
            assert isinstance(d.special, int)


def test_loader_sees_no_holdout_ids():
    ids = _expl_ids()
    with (ROOT / "metadata/phase3_holdout_ids.csv").open(newline="") as f:
        hold_ids = {r["draw_id"] for r in csv.DictReader(f)}
    assert not (ids & hold_ids)
    draws = load_exploration_draws(DRAWS, ids)
    assert not ({d.draw_id for d in draws} & hold_ids)
