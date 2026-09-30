"""F-E004 eligibility tests — physical-order admissibility, holdout
firewall, and the n>=100 gate. Metadata-only; no outcome fields."""

import csv
from pathlib import Path

from fortuna.analysis.split import exploration_segments
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime
from fortuna.simulation.observation import load_draw_metadata

ROOT = Path(__file__).resolve().parents[2]
DRAWS = ROOT / "data/processed/draws.csv"
META = ROOT / "metadata"


def _exploration_ids():
    ids = set()
    with (META / "phase3_exploration_ids_v2.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            ids.add(r["draw_id"])
    return ids


def test_physical_segments_metadata_only():
    meta = load_draw_metadata(DRAWS)
    regimes = load_csv(META / "game_regimes.csv", GameRegime)
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}
    expl = _exploration_ids()
    osegs = exploration_segments(meta, regimes, stat_of, expl,
                                 order_only=True)
    # every physical-order exploration draw is inside exactly one segment
    phys_ids = {
        r["draw_id"] for r in meta
        if r["draw_id"] in expl
        and r.get("numbers_order") == "physical_draw_order"
    }
    seg_dates = {
        (sid, d) for sid, segs in osegs.items() for s in segs for d in s
    }
    covered = set()
    for r in meta:
        if r["draw_id"] in phys_ids:
            covered.add(
                (stat_of[r["regime_id"]], r["draw_date"])
            )
    from datetime import date
    assert all(
        (sid, date.fromisoformat(dstr)) in seg_dates
        for sid, dstr in covered
    )
    # no holdout ID is a physical-order exploration draw
    hold = set()
    with (META / "phase3_holdout_ids.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            hold.add(r["draw_id"])
    assert not (hold & phys_ids)


def test_sorted_and_unknown_rows_break_segments():
    meta = load_draw_metadata(DRAWS)
    regimes = load_csv(META / "game_regimes.csv", GameRegime)
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}
    expl = _exploration_ids()
    all_segs = exploration_segments(meta, regimes, stat_of, expl)
    osegs = exploration_segments(meta, regimes, stat_of, expl,
                                 order_only=True)
    # physical segments are a strict refinement: total physical draws
    # <= total exploration draws per regime
    for sid in all_segs:
        n_all = sum(len(s) for s in all_segs[sid])
        n_ord = sum(len(s) for s in osegs.get(sid, []))
        assert n_ord <= n_all
    # PB-S01/PB-S02 had their physical-order claims fully withdrawn by
    # the D-007 audit (sorted backfill) -> zero physical-order draws
    assert sum(len(s) for s in osegs.get("PB-S01", [])) == 0
    assert sum(len(s) for s in osegs.get("PB-S02", [])) == 0


def test_min_sample_gate_counts():
    meta = load_draw_metadata(DRAWS)
    regimes = load_csv(META / "game_regimes.csv", GameRegime)
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}
    expl = _exploration_ids()
    osegs = exploration_segments(meta, regimes, stat_of, expl,
                                 order_only=True)
    counts = {
        sid: sum(len(s) for s in segs) for sid, segs in osegs.items()
    }
    qualifying = [s for s, n in counts.items() if n >= 100]
    # sanity: the known qualifying set from the corrected split
    assert counts.get("MM-S03", 0) < 100    # 94 physical-order draws
    assert counts.get("PB-S03", 0) < 100    # 99 physical-order draws
    assert len(qualifying) == 10
