"""D-007 atomic order/sequence provenance tests (synthetic + canonical).

A canonical draw's stored main-number sequence, its numbers_order label,
and number_sequence_source_id must refer to ONE staged source record.
numbers_order may never be borrowed from a different source than the
sequence itself.
"""
import csv
from datetime import date
from pathlib import Path

import pytest

from fortuna.ingestion import parsers
from fortuna.ingestion.pipeline import (
    build_canonical,
    draw_source_ids,
    reconcile_groups,
)
from fortuna.ingestion.staging import StagedDraw
from fortuna.schemas.draws import DrawStream, OrderSemantics

ROOT = Path(__file__).resolve().parents[2]

TIERS = {
    "SRC-WI-PB-CSV": 1,
    "SRC-MO-PB-XLSX": 1,
    "SRC-TX-PB-CSV": 1,
    "SRC-NY-PB-DATA": 2,
    "SRC-NY-PB-ARCHIVE": 3,
    "SRC-NY-MM-ARCHIVE": 3,
}


def _staged(
    d=date(2020, 1, 4), nums=(1, 2, 3, 4, 5), sb=10, src="SRC-A",
    order=OrderSemantics.SOURCE_SORTED_ORDER, **kw,
):
    return StagedDraw(
        game_id="powerball", draw_date=d, draw_stream=DrawStream.MAIN,
        main_numbers=list(nums), special_ball=sb, numbers_order=order,
        source_id=src, artifact_sha256="0" * 64, **kw,
    )


def _build(recs, regimes, tiers=None, resolutions=None):
    groups, _ = reconcile_groups(recs, tiers or {})
    return build_canonical(groups or {}, regimes, tiers or {},
                           resolutions or {})


# ---------- 1. label cannot be borrowed over another source's sequence ----

def test_sorted_primary_not_upgraded_by_tier3_physical_claim(regimes):
    """A Tier-3 physical claim must not put a physical label on the
    primary's sorted sequence."""
    primary = _staged(src="SRC-NY-PB-DATA", nums=(5, 11, 29, 47, 50))
    corr = _staged(
        src="SRC-NY-PB-ARCHIVE", nums=(47, 5, 50, 11, 29),
        order=OrderSemantics.PHYSICAL_DRAW_ORDER,
    )
    draws, errors, _ = _build([corr, primary], regimes, TIERS)
    d = draws[0]
    assert d.main_numbers == [5, 11, 29, 47, 50]            # primary's seq
    assert d.numbers_order == OrderSemantics.SOURCE_SORTED_ORDER
    assert d.number_sequence_source_id == "SRC-NY-PB-DATA"


def test_authoritative_physical_supplier_adopted_atomically(regimes):
    """If a trustworthy corroborating source supplies physical order, the
    canonical sequence IS that source's stored sequence."""
    primary = _staged(src="SRC-NY-PB-DATA", nums=(5, 11, 29, 47, 50))
    corr = _staged(
        src="SRC-MO-PB-XLSX", nums=(47, 5, 50, 11, 29),
        order=OrderSemantics.PHYSICAL_DRAW_ORDER,
    )
    draws, _, _ = _build([corr, primary], regimes, TIERS)
    d = draws[0]
    assert d.main_numbers == [47, 5, 50, 11, 29]           # corr's seq
    assert d.numbers_order == OrderSemantics.PHYSICAL_DRAW_ORDER
    assert d.number_sequence_source_id == "SRC-MO-PB-XLSX"


def test_single_source_unknown_order_stays_unknown(regimes):
    """A lone source record keeps its own order semantics; nothing is
    inferred."""
    primary = _staged(
        src="SRC-NY-PB-DATA", nums=(5, 11, 29, 47, 50),
        order=OrderSemantics.UNKNOWN_ORDER,
    )
    draws, _, _ = _build([primary], regimes, TIERS)
    d = draws[0]
    assert d.numbers_order == OrderSemantics.UNKNOWN_ORDER
    assert d.number_sequence_source_id == "SRC-NY-PB-DATA"


def test_authoritative_sorted_upgrade_over_unknown(regimes):
    """Authoritative corroborating source with physical semantics supplies
    its own stored sequence when the primary's order is unknown."""
    primary = _staged(
        src="SRC-NY-PB-DATA", nums=(5, 11, 29, 47, 50),
        order=OrderSemantics.UNKNOWN_ORDER,
    )
    corr = _staged(src="SRC-TX-PB-CSV", nums=(11, 5, 29, 50, 47),
                   order=OrderSemantics.PHYSICAL_DRAW_ORDER)
    draws, _, _ = _build([corr, primary], regimes, TIERS)
    d = draws[0]
    assert d.main_numbers == [11, 5, 29, 50, 47]
    assert d.numbers_order == OrderSemantics.PHYSICAL_DRAW_ORDER
    assert d.number_sequence_source_id == "SRC-TX-PB-CSV"


# ---------- 2-4. atomicity invariants on synthetic groups ----------------

@pytest.mark.parametrize("corr_order", [
    OrderSemantics.PHYSICAL_DRAW_ORDER,
    OrderSemantics.SOURCE_SORTED_ORDER,
    OrderSemantics.UNKNOWN_ORDER,
])
def test_sequence_semantics_and_source_always_agree(regimes, corr_order):
    primary = _staged(src="SRC-WI-PB-CSV", nums=(9, 3, 44, 27, 50),
                      order=OrderSemantics.PHYSICAL_DRAW_ORDER)
    corr = _staged(src="SRC-NY-PB-DATA", nums=(3, 9, 27, 44, 50),
                   order=corr_order)
    draws, _, _ = _build([corr, primary], regimes, TIERS)
    d = draws[0]
    seq_src = primary if d.number_sequence_source_id == "SRC-WI-PB-CSV" \
        else corr
    assert d.numbers_order == seq_src.numbers_order
    assert d.main_numbers == seq_src.main_numbers
    assert d.number_sequence_source_id in draw_source_ids(d)
    if d.numbers_order == OrderSemantics.PHYSICAL_DRAW_ORDER:
        assert seq_src.numbers_order == OrderSemantics.PHYSICAL_DRAW_ORDER


def test_resolution_override_relabels_sequence_provenance(regimes):
    wi = _staged(src="SRC-WI-PB-CSV", nums=(1, 2, 3, 4, 5))
    mo = _staged(src="SRC-MO-PB-XLSX", nums=(1, 2, 3, 4, 6))
    res = {
        ("powerball", date(2020, 1, 4), "main_numbers"): {
            "resolved_value": "9;10;11;12;13",
            "resolution": "test",
            "resolution_evidence": "test",
            "evidence_source_id": "SRC-EVIDENCE",
            "status": "resolved",
        }
    }
    groups, _ = reconcile_groups([wi, mo], TIERS)
    draws, _, _ = build_canonical(groups, regimes, TIERS, res)
    d = draws[0]
    assert d.numbers_order == OrderSemantics.SOURCE_SORTED_ORDER
    assert d.number_sequence_source_id == "SRC-EVIDENCE"


# ---------- 5-6. parser-level order audit --------------------------------

def test_wi_sorted_era_reclassified_sorted_and_ascending_rows_unknown():
    """WI-style artifact: an all-ascending year is sorted backfill; a mixed
    year keeps physical only for non-ascending rows."""
    content = (
        b'"Draw Date",,,,,,PB,"Power Play","Est. Jackpot"\n'
        # 1999 rows all ascending -> era is sorted backfill
        b"1999-01-02,1,2,3,4,5,8,3x,$10.00M\n"
        b"1999-01-06,6,7,8,9,10,9,2x,$12.00M\n"
        # 2005 mixed: one ascending, one non-ascending
        b"2005-01-01,2,4,6,8,10,1,2x,$20.00M\n"
        b"2005-01-05,49,7,21,29,42,3,2x,$22.00M\n"
    )
    recs = parsers.parse_wi_powerball_csv(content, _art_stub("SRC-WI-PB-CSV"))
    by_date = {r.draw_date.isoformat(): r for r in recs}
    assert by_date["1999-01-02"].numbers_order == (
        OrderSemantics.SOURCE_SORTED_ORDER)
    assert by_date["1999-01-06"].numbers_order == (
        OrderSemantics.SOURCE_SORTED_ORDER)
    assert by_date["2005-01-01"].numbers_order == OrderSemantics.UNKNOWN_ORDER
    assert by_date["2005-01-05"].numbers_order == (
        OrderSemantics.PHYSICAL_DRAW_ORDER)


def _art_stub(source_id):
    from datetime import UTC, datetime

    from fortuna.schemas.artifacts import RawArtifact
    return RawArtifact(
        artifact_id="RA-999999", source_id=source_id, filename="t.csv",
        mime_type="text/csv", retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        sha256="0" * 64, immutable_path="data/raw/SRC-TEST/t.csv",
    )


# ---------- real canonical store invariants -------------------------------

def _real_draws():
    return list(csv.DictReader(
        (ROOT / "data/processed/draws.csv").open(encoding="utf-8")
    ))


def test_canonical_physical_rows_have_atomic_provenance():
    """Every canonical physical-order record must name a sequence source,
    and that source must be one the parsers can emit physical order for
    (post-audit: WI/MO/TX/FL-LOTTO only)."""
    physical_capable = {
        "SRC-WI-PB-CSV", "SRC-MO-PB-XLSX", "SRC-TX-PB-CSV",
        "SRC-TX-MM-CSV", "SRC-FL-LOTTO-HIST-PDF",
    }
    for r in _real_draws():
        if r["numbers_order"] != "physical_draw_order":
            continue
        assert r["number_sequence_source_id"] in physical_capable, (
            r["draw_id"], r["number_sequence_source_id"])
        assert r["number_sequence_source_id"] in (
            r["source_id"], *r["corroborating_source_ids"].split(";"))


def test_canonical_sequence_matches_claimed_semantics():
    """A canonical row claiming physical order must store a non-ascending
    sequence (ascending physical claims were demoted by the audit)."""
    import re
    bad = []
    for r in _real_draws():
        if r["numbers_order"] != "physical_draw_order":
            continue
        nums = [int(x) for x in re.split(r"[;]", r["main_numbers"])]
        if nums == sorted(nums):
            bad.append(r["draw_id"])
    assert not bad, bad[:10]
