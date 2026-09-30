"""Phase 3 split / seal / exploration-segment tests (metadata only)."""

import csv
import math
from datetime import date
from pathlib import Path

import pytest
import yaml

from fortuna.analysis.split import (
    assign_splits,
    exploration_segments,
    holdout_seal_sha256,
    split_policy_sha256,
)
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime
from fortuna.simulation.observation import load_draw_metadata

ROOT = Path(__file__).resolve().parents[2]
DRAWS = ROOT / "data/processed/draws.csv"
EXPL = ROOT / "metadata/phase3_exploration_ids.csv"
HOLD = ROOT / "metadata/phase3_holdout_ids.csv"
SUMMARY = ROOT / "metadata/phase3_split_summary.csv"
SEAL = ROOT / "metadata/phase3_holdout_seal.json"


@pytest.fixture(scope="module")
def split_artifacts():
    import json
    return {
        "expl": list(csv.DictReader(EXPL.open())),
        "hold": list(csv.DictReader(HOLD.open())),
        "summary": list(csv.DictReader(SUMMARY.open())),
        "seal": json.loads(SEAL.read_text()),
    }


def test_holdout_count_is_ceil_20_percent(split_artifacts):
    meta = load_draw_metadata(DRAWS)
    regimes = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}
    n_by = {}
    for r in meta:
        if r["draw_stream"] == "main" and r["analysis_eligible"] == "true":
            s = stat_of.get(r["regime_id"])
            if s:
                n_by[s] = n_by.get(s, 0) + 1
    hold_by = {}
    for r in split_artifacts["hold"]:
        hold_by[r["statistical_regime_id"]] = (
            hold_by.get(r["statistical_regime_id"], 0) + 1
        )
    assert len(hold_by) == 16
    for s, n in n_by.items():
        assert hold_by[s] == math.ceil(0.20 * n), s


def test_split_is_chronological_last_20(split_artifacts):
    expl = {}
    for r in split_artifacts["expl"]:
        expl.setdefault(r["statistical_regime_id"], []).append(r["draw_date"])
    hold = {}
    for r in split_artifacts["hold"]:
        hold.setdefault(r["statistical_regime_id"], []).append(r["draw_date"])
    for s in expl:
        assert max(expl[s]) < min(hold[s]), s  # strict chronological split


def test_no_id_overlap_and_metadata_only(split_artifacts):
    eids = {r["draw_id"] for r in split_artifacts["expl"]}
    hids = {r["draw_id"] for r in split_artifacts["hold"]}
    assert not (eids & hids)
    assert len(eids) + len(hids) == 10332
    allowed = {
        "draw_id", "game_id", "statistical_regime_id", "draw_date",
        "draw_stream", "split",
    }
    for rows in (split_artifacts["expl"], split_artifacts["hold"]):
        assert set(rows[0].keys()) <= allowed
        # manifests must not expose outcome data anywhere
        for r in rows[:50]:
            assert all(";" not in v for v in r.values())


def test_seal_deterministic_and_sensitive(split_artifacts, tmp_path):
    hids = {r["draw_id"] for r in split_artifacts["hold"]}
    s1 = holdout_seal_sha256(DRAWS, hids)
    assert s1 == split_artifacts["seal"]["holdout_seal_sha256"]
    # mutating a holdout row changes the seal
    lines = DRAWS.read_text().splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.split(",", 1)[0] in hids:
            lines[i] = ln.replace(",main,", ",main,X", 1)
            break
    fake = tmp_path / "draws.csv"
    fake.write_text("".join(lines))
    assert holdout_seal_sha256(fake, hids) != s1


def test_split_policy_hash_stable():
    cfg = yaml.safe_load((ROOT / "config/experiments/F-E002.yaml").read_text())
    h = split_policy_sha256(cfg["split"])
    assert h == split_policy_sha256(dict(cfg["split"]))
    changed = dict(cfg["split"], holdout_fraction=0.25)
    assert split_policy_sha256(changed) != h


def test_all_regimes_in_summary(split_artifacts):
    ids = {r["statistical_regime_id"] for r in split_artifacts["summary"]}
    assert len(ids) == 16
    for r in split_artifacts["summary"]:
        n = int(r["eligible_main_draw_count"])
        assert int(r["exploration_count"]) + int(r["holdout_count"]) == n
        segs = [int(x) for x in r["exploration_segment_lengths"].split(";")]
        assert sum(segs) == int(r["exploration_count"])
        assert len(segs) == int(r["exploration_segments"])


def test_assign_splits_independent_per_regime():
    meta = [
        {"draw_id": f"{g}-D-{i:03d}", "game_id": g, "regime_id": g,
         "draw_date": f"2020-01-{i:02d}", "draw_stream": "main",
         "analysis_eligible": "true", "numbers_order": "x",
         "validation_status": "valid", "provisional": "false"}
        for g, n in (("A", 10), ("B", 7)) for i in range(1, n + 1)
    ]
    rows = assign_splits(meta, {"A": "SA", "B": "SB"})
    sa = [r for r in rows if r["statistical_regime_id"] == "SA"]
    sb = [r for r in rows if r["statistical_regime_id"] == "SB"]
    assert sum(r["split"] == "holdout" for r in sa) == 2   # ceil(2.0)
    assert sum(r["split"] == "holdout" for r in sb) == 2   # ceil(1.4)
    assert [r["split"] for r in sa].count("exploration") == 8


def test_exploration_segment_breaks():
    """Synthetic: ineligible positions and the boundary break segments."""

    from fortuna.schemas.regimes import GameRegime as GR

    # legal regime covering the whole window, draws every day
    reg = GR(
        regime_id="TS-R001", game_id="g", statistical_regime_id="TS-S01",
        change_classification="baseline", legal_effective_start=date(2020, 1, 1),
        legal_effective_end=None, first_affected_draw=date(2020, 1, 1),
        last_affected_draw=date(2020, 1, 10), first_unambiguous_draw=None,
        main_ball_count=2, main_ball_min=1, main_ball_max=10,
        special_ball_count=0, special_ball_min=None, special_ball_max=None,
        sampling_without_replacement=True,
        drawing_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        scheduled_draw_time=None, timezone=None, ticket_price=None,
        jackpot_odds=None, overall_odds=None, drawing_location=None,
        drawing_method=None, material_change_reason="x",
        rule_identifier="x", source_id="s",
        verification_date=date(2020, 1, 1), verification_status="verified",
        notes=None,
    )
    meta = []
    # eligible draws on days 1-10; day 5 ineligible; day 7 missing entirely
    for i in range(1, 11):
        if i == 7:
            continue
        meta.append({
            "draw_id": f"g-D-{i:02d}", "game_id": "g", "regime_id": "TS-R001",
            "draw_date": f"2020-01-{i:02d}", "draw_stream": "main",
            "analysis_eligible": "false" if i == 5 else "true",
            "numbers_order": "physical_draw_order",
            "validation_status": "valid", "provisional": "false",
        })
    # exploration = eligible draws before day 9 (simulate a split boundary)
    expl_ids = {
        r["draw_id"] for r in meta
        if r["analysis_eligible"] == "true" and int(r["draw_date"][-2:]) < 9
    }
    segs = exploration_segments(meta, [reg], {"TS-R001": "TS-S01"}, expl_ids)["TS-S01"]
    seg_dates = [[d.day for d in s] for s in segs]
    # days 1-4 | 5 ineligible | 6 | 7 missing | 8 ; days 9-10 sit outside
    # the exploration window entirely (split boundary).
    assert seg_dates == [[1, 2, 3, 4], [6], [8]]
