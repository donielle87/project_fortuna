"""D-008 draw-exclusion tests — evidence-based, never duplicate-only.

The generic rule 'two consecutive identical sets => phantom' is NOT
implemented anywhere: only ledger rows with decision_status='excluded'
remove a canonical draw from eligibility, and every such row carries
independent source/schedule evidence.
"""
import csv
from datetime import date
from pathlib import Path

from fortuna.ingestion.pipeline import (
    apply_eligibility,
    build_canonical,
    load_exclusions,
    reconcile_groups,
    structural_validate,
)
from fortuna.ingestion.staging import StagedDraw
from fortuna.schemas.draws import DrawStream, OrderSemantics

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "metadata/draw_exclusions.csv"

TIERS = {"SRC-WI-PB-CSV": 1, "SRC-NY-PB-DATA": 2, "SRC-MD-PB-ARCHIVE": 1}


def _staged(d, nums=(1, 2, 3, 4, 5), sb=10, src="SRC-WI-PB-CSV"):
    return StagedDraw(
        game_id="powerball", draw_date=d, draw_stream=DrawStream.MAIN,
        main_numbers=list(nums), special_ball=sb,
        numbers_order=OrderSemantics.SOURCE_SORTED_ORDER,
        source_id=src, artifact_sha256="0" * 64,
    )


# ---------- generic rules must NOT trigger exclusion ---------------------

def test_identical_consecutive_sets_alone_not_excluded(regimes):
    """Two consecutive draws with identical main sets remain eligible
    absent ledger evidence — rarity alone cannot prove corruption."""
    a = _staged(date(2020, 1, 4))
    b = _staged(date(2020, 1, 8))  # next Wed, identical set
    groups, _ = reconcile_groups([a, b], TIERS)
    draws, _, ckeys = build_canonical(groups, regimes, TIERS, {})
    structural_validate(draws, regimes)
    reasons = apply_eligibility(draws, ckeys, regimes, TIERS)
    assert len(draws) == 2
    assert all(d.analysis_eligible for d in draws)
    assert not reasons


def test_off_schedule_weekday_alone_not_excluded(regimes):
    """A documented-exception-style off-schedule draw is not rejected by
    any generic weekday rule."""
    # 2020-01-05 is a Sunday (PB era is Wed/Sat): a sole-source but
    # otherwise valid record stays eligible without ledger evidence.
    a = _staged(date(2020, 1, 5))
    groups, _ = reconcile_groups([a], TIERS)
    draws, _, ckeys = build_canonical(groups, regimes, TIERS, {})
    structural_validate(draws, regimes)
    apply_eligibility(draws, ckeys, regimes, TIERS)
    assert draws[0].analysis_eligible is True


def test_ledger_row_excludes_specific_draw(regimes):
    a = _staged(date(2020, 1, 5))
    excl = {
        "PB-D-2020-01-05": {
            "reason_code": "off_schedule_duplicate_set",
            "decision_id": "D-008",
        }
    }
    groups, _ = reconcile_groups([a], TIERS)
    draws, _, ckeys = build_canonical(groups, regimes, TIERS, {})
    structural_validate(draws, regimes)
    reasons = apply_eligibility(draws, ckeys, regimes, TIERS, excl)
    assert draws[0].analysis_eligible is False
    assert "excluded_non_draw_artifact" in reasons[draws[0].draw_id]


def test_loader_respects_decision_status(tmp_path):
    tmp_meta = tmp_path / "metadata"
    tmp_meta.mkdir()
    led = tmp_meta / "draw_exclusions.csv"
    with led.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "exclusion_id", "game_id", "draw_date", "draw_id",
            "source_id", "reason_code", "evidence",
            "decision_status", "decision_id",
        ])
        w.writeheader()
        w.writerow({
            "exclusion_id": "EX-T1", "game_id": "powerball",
            "draw_date": "2020-01-05", "draw_id": "PB-D-2020-01-05",
            "source_id": "SRC-X", "reason_code": "suspect",
            "evidence": "under investigation",
            "decision_status": "suspect_unresolved", "decision_id": "",
        })
        w.writerow({
            "exclusion_id": "EX-T2", "game_id": "powerball",
            "draw_date": "2020-01-08", "draw_id": "PB-D-2020-01-08",
            "source_id": "SRC-X", "reason_code": "misdated_duplicate_set",
            "evidence": "sole-source off-schedule duplicate",
            "decision_status": "excluded", "decision_id": "D-008",
        })
    excl = load_exclusions(tmp_path)
    assert set(excl) == {"PB-D-2020-01-08"}  # suspect_unresolved inert


# ---------- real-ledger disposition ---------------------------------------

def test_real_ledger_dispositions():
    """The committed ledger is internally consistent and the disputed
    MM-S03 pair is resolved against evidence: 2002-06-05 (Wed) is the
    erroneous record, not the scheduled 2002-06-07 (Fri)."""
    rows = list(csv.DictReader(LEDGER.open(encoding="utf-8")))
    assert len(rows) == 12
    excl_ids = {r["draw_id"] for r in rows if r["decision_status"] == "excluded"}
    assert len(excl_ids) == 12
    assert "MM-D-2002-06-05" in excl_ids
    assert "MM-D-2002-06-07" not in excl_ids
    assert all(r["source_id"].startswith("SRC-MD-") for r in rows)
    assert all(r["evidence"].strip() for r in rows)


def test_excluded_draws_ineligible_in_canonical_store():
    draws = list(csv.DictReader(
        (ROOT / "data/processed/draws.csv").open(encoding="utf-8")
    ))
    by_id = {r["draw_id"]: r for r in draws}
    rows = list(csv.DictReader(LEDGER.open(encoding="utf-8")))
    for r in rows:
        d = by_id[r["draw_id"]]
        assert d["analysis_eligible"] == "false", r["draw_id"]
        assert "excluded per draw_exclusions.csv" in (
            d["data_quality_notes"] or "")
    # the real draws survive
    assert by_id["MM-D-2002-06-07"]["analysis_eligible"] == "true"
    assert by_id["MM-D-2014-01-14"]["analysis_eligible"] == "true"


def test_no_excluded_holdout_id():
    hold = {
        r["draw_id"]
        for r in csv.DictReader(
            (ROOT / "metadata/phase3_holdout_ids.csv").open()
        )
    }
    rows = list(csv.DictReader(LEDGER.open(encoding="utf-8")))
    leaked = [r["draw_id"] for r in rows if r["draw_id"] in hold]
    assert not leaked, leaked
