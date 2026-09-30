"""Phase 1 parser + pipeline unit tests (synthetic inputs, no artifacts)."""
from datetime import UTC, date, datetime

from fortuna.ingestion import parsers
from fortuna.ingestion.pipeline import (
    apply_eligibility,
    build_canonical,
    canonical_draw_id,
    reconcile_groups,
    structural_validate,
)
from fortuna.ingestion.staging import StagedDraw
from fortuna.schemas.artifacts import RawArtifact
from fortuna.schemas.draws import DrawStream, DrawValidationStatus, OrderSemantics


def _art(source_id="SRC-TEST", sha="0" * 64):
    return RawArtifact(
        artifact_id="RA-999999", source_id=source_id, filename="t.json",
        mime_type="application/json", retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        sha256=sha, immutable_path="data/raw/SRC-TEST/t.json",
    )


def _staged(game="powerball", d=date(2020, 1, 4), nums=(1, 2, 3, 4, 5), sb=10,
            stream=DrawStream.MAIN, src="SRC-A", mult=None, **kw):
    return StagedDraw(
        game_id=game, draw_date=d, draw_stream=stream,
        main_numbers=list(nums), special_ball=sb, multiplier=mult,
        source_id=src, artifact_sha256="0" * 64, **kw,
    )


# ---------- NY Socrata ----------

def test_socrata_pb_parses_and_splits_double_play():
    content = (
        b'[{"draw_date":"2021-08-25T00:00:00.000",'
        b'"winning_numbers":"10 20 29 48 51 17","multiplier":"2",'
        b'"double_play_winning_numbers":"09 10 21 59 62 22"},'
        b'{"draw_date":"2021-08-28T00:00:00.000",'
        b'"winning_numbers":"05 09 11 16 66 07","multiplier":"3"}]'
    )
    recs = parsers.parse_ny_socrata_powerball(content, _art("SRC-NY-PB-DATA"))
    assert len(recs) == 3
    dp = [r for r in recs if r.draw_stream == DrawStream.DOUBLE_PLAY]
    assert len(dp) == 1 and dp[0].main_numbers == [9, 10, 21, 59, 62]
    assert dp[0].special_ball == 22
    main = [r for r in recs if r.draw_stream == DrawStream.MAIN]
    assert main[0].main_numbers == [10, 20, 29, 48, 51]
    assert main[0].special_ball == 17 and main[0].multiplier == 2.0
    assert main[0].numbers_order == OrderSemantics.SOURCE_SORTED_ORDER


def test_socrata_mm_mega_ball_and_multiplier():
    content = (
        b'[{"draw_date":"2002-05-17T00:00:00.000","winning_numbers":"15 18 25 33 47",'
        b'"mega_ball":"30"},'
        b'{"draw_date":"2025-04-08T00:00:00.000","winning_numbers":"01 02 03 04 05",'
        b'"mega_ball":"9","multiplier":"4"}]'
    )
    recs = parsers.parse_ny_socrata_megamillions(content, _art("SRC-NY-MM-DATA"))
    assert len(recs) == 2
    assert recs[0].special_ball == 30 and recs[0].multiplier is None
    assert recs[1].multiplier == 4.0


def test_socrata_metadata_view_yields_no_rows():
    recs = parsers.parse_ny_socrata_powerball(b'{"name":"dataset meta"}', _art())
    assert recs == []


# ---------- NY archive HTML ----------

def test_ny_archive_parses_row_jackpot_multiplier_and_dp_block():
    html = b"""
    <tr><td><a href="/powerball/results/06-03-2026"><span>Wednesday</span></a></td>
    <td><div>
      <span class="resultBall ball">14</span><span class="resultBall ball">16</span>
      <span class="resultBall ball">38</span><span class="resultBall ball">55</span>
      <span class="resultBall ball">64</span><span class="resultBall powerball">12</span>
    </div>
    <div><div>Double Play</div><div>
      <span class="resultBall ball">26</span><span class="resultBall ball">28</span>
      <span class="resultBall ball">31</span><span class="resultBall ball">56</span>
      <span class="resultBall ball">64</span><span class="resultBall powerball">13</span>
    </div></div>
    <div class="power-play">Power Play: <strong>&times;3</strong></div></td>
    <td><strong style="font-size: 14px;">$194,200,000</strong></td></tr>
    """
    recs = parsers.parse_ny_archive_html(
        html, _art("SRC-NY-PB-ARCHIVE"), slug="powerball",
        game_id="powerball", special_cls="powerball",
    )
    assert len(recs) == 2
    main = [r for r in recs if r.draw_stream == DrawStream.MAIN][0]
    dp = [r for r in recs if r.draw_stream == DrawStream.DOUBLE_PLAY][0]
    assert main.main_numbers == [14, 16, 38, 55, 64] and main.special_ball == 12
    assert main.multiplier == 3.0 and main.jackpot == 194_200_000
    assert dp.main_numbers == [26, 28, 31, 56, 64] and dp.special_ball == 13
    assert dp.multiplier is None  # DP has no Power Play


# ---------- MO xlsx ----------

def _xlsx_bytes(rows: list[list[str]]) -> bytes:
    import io
    import zipfile
    from xml.sax.saxutils import escape

    ss, body = [], []
    for r in rows:
        row_xml = ""
        for v in r:
            ss.append(v)
            row_xml += f'<c t="s"><v>{len(ss) - 1}</v></c>'
        body.append(f"<row>{row_xml}</row>")
    sheet = (
        '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main"><sheetData>' + "".join(body) + "</sheetData></worksheet>"
    )
    shared = (
        '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/'
        'spreadsheetml/2006/main">' + "".join(f"<si><t>{escape(v)}</t></si>" for v in ss)
        + "</sst>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", shared)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def test_mo_xlsx_as_drawn_vs_sorted_order_semantics():
    content = _xlsx_bytes([
        ["Draw Date", "Numbers As Drawn", "Numbers In Order", "PB", "PP", "Jackpot"],
        ["28-09-2026", "49--42--21--29--17", "17--21--29--42--49", "7", "3", "$389 million"],
        ["01-01-2000", "6--9--16--28--38", "6--9--16--28--38", "13", "0", "$10 million"],
    ])
    recs = parsers.parse_mo_powerball_xlsx(content, _art("SRC-MO-PB-XLSX"))
    assert len(recs) == 2
    assert recs[0].main_numbers == [49, 42, 21, 29, 17]
    assert recs[0].numbers_order == OrderSemantics.PHYSICAL_DRAW_ORDER
    assert recs[0].jackpot == 389_000_000 and recs[0].multiplier == 3.0
    # identical columns can't prove draw order
    assert recs[1].numbers_order == OrderSemantics.UNKNOWN_ORDER
    assert recs[1].multiplier is None  # '0' = no Power Play


# ---------- TX CSV ----------

def test_tx_csv_draw_order_and_dates():
    content = (
        b"Mega Millions,12,5,2003,12,44,15,18,1,42,4\n"
        b"Mega Millions,9,25,2026,58,67,25,68,57,16,\n"
    )
    recs = parsers.parse_tx_csv(content, _art("SRC-TX-MM-CSV"), game_id="mega_millions")
    assert len(recs) == 2
    assert recs[0].draw_date == date(2003, 12, 5)
    assert recs[0].main_numbers == [12, 44, 15, 18, 1]
    assert recs[0].special_ball == 42 and recs[0].multiplier == 4.0
    assert recs[0].numbers_order == OrderSemantics.PHYSICAL_DRAW_ORDER
    assert recs[1].multiplier is None  # post-2025 built-in multiplier is blank


# ---------- FL PDFs ----------

def test_fl_lotto_pdf_streams_order_boundary_and_machine_fields():
    recs = parsers.parse_fl_history_lines(
        [
            "Draw Date Winning Numbers Game Machine/Ball Set",
            "9/26/26 1 5 10 15 35 45 LOTTO 5 / D",
            "9/26/26 3 9 25 31 41 51 LOTTO DP 1 / C",
            "6/6/20 27 32 36 38 43 50 X5 1 / D",
            "1/29/05 4 15 43 30 14 50",
            "2/2/05 4 8 22 25 29 42",
        ],
        _art("SRC-FL-LOTTO-HIST-PDF"), game_id="florida_lotto",
        lotto_sorted_after=date(2005, 2, 2),
    )
    assert len(recs) == 5
    dp = [r for r in recs if r.draw_stream == DrawStream.DOUBLE_PLAY]
    assert len(dp) == 1 and dp[0].machine_id == "1" and dp[0].ball_set_id == "C"
    xtra = [r for r in recs if r.draw_date == date(2020, 6, 6)][0]
    assert xtra.multiplier == 5.0 and xtra.machine_id == "1" and xtra.ball_set_id == "D"
    phys = [r for r in recs if r.draw_date == date(2005, 1, 29)][0]
    srt = [r for r in recs if r.draw_date == date(2005, 2, 2)][0]
    assert phys.numbers_order == OrderSemantics.PHYSICAL_DRAW_ORDER
    assert srt.numbers_order == OrderSemantics.SOURCE_SORTED_ORDER


def test_fl_pb_pdf_splits_powerball_dp():
    recs = parsers.parse_fl_history_lines(
        [
            "9/28/26 17 21 29 42 49 PB 7 X3 POWERBALL",
            "9/28/26 11 20 26 43 46 PB 18 POWERBALL DP",
        ],
        _art("SRC-FL-PB-HIST-PDF"), game_id="powerball",
    )
    assert {r.draw_stream for r in recs} == {DrawStream.MAIN, DrawStream.DOUBLE_PLAY}
    main = [r for r in recs if r.draw_stream == DrawStream.MAIN][0]
    assert main.special_ball == 7 and main.multiplier == 3.0
    dp = [r for r in recs if r.draw_stream == DrawStream.DOUBLE_PLAY][0]
    assert dp.special_ball == 18


def test_fl_mm_pdf_megaball_and_megaplier():
    recs = parsers.parse_fl_history_lines(
        [
            "09/25/26 25 57 58 67 68 MB  16",
            "07/05/13 2 23 41 47 54 MB 42 X4",
        ],
        _art("SRC-FL-MM-HIST-PDF"), game_id="mega_millions",
    )
    assert recs[0].special_ball == 16 and recs[0].multiplier is None
    assert recs[1].special_ball == 42 and recs[1].multiplier == 4.0


# ---------- Pipeline: ids, reconcile, eligibility ----------

def test_canonical_draw_id_dp_suffix():
    assert canonical_draw_id("powerball", date(2021, 8, 25), DrawStream.MAIN) == "PB-D-2021-08-25"
    assert (
        canonical_draw_id("powerball", date(2021, 8, 25), DrawStream.DOUBLE_PLAY)
        == "PB-D-2021-08-25-DP"
    )


def test_reconcile_match_and_conflict(regimes):
    a = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-NY-PB-ARCHIVE")
    b = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-NY-PB-DATA")
    c = _staged(nums=(1, 2, 3, 4, 5), sb=11, src="SRC-MO-PB-XLSX")  # conflict
    groups, rows = reconcile_groups([a, b, c])
    assert len(groups) == 1
    conf = [r for r in rows if r["classification"] == "CONFLICT"]
    assert conf and all(r["field"] == "special_ball" for r in conf)


def test_field_complement_not_conflict():
    a = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-NY-PB-ARCHIVE", mult=None)
    b = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-NY-PB-DATA", mult=3.0)
    _, rows = reconcile_groups([a, b])
    comp = [r for r in rows if r["field"] == "multiplier"]
    assert comp[0]["classification"] == "FIELD_COMPLEMENT"


def test_canonical_draw_conflict_marks_ineligible(regimes):
    # same date, differing winning numbers across two sources
    a = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-NY-PB-ARCHIVE")
    b = _staged(nums=(1, 2, 3, 4, 6), sb=10, src="SRC-NY-PB-DATA")
    groups, _ = reconcile_groups([a, b])
    draws, errors, ckeys = build_canonical(groups, regimes)
    assert len(draws) == 1 and not errors
    apply_eligibility(draws, ckeys, regimes)
    assert draws[0].analysis_eligible is False
    assert "conflict" in (draws[0].data_quality_notes or "")


def test_provisional_never_eligible(regimes):
    a = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-NY-PB-ARCHIVE")
    groups, _ = reconcile_groups([a])
    draws, _, ckeys = build_canonical(groups, regimes)
    draws[0].provisional = True
    apply_eligibility(draws, ckeys, regimes)
    assert draws[0].analysis_eligible is False


def test_quarantined_draw_status(regimes):
    # A draw dated inside a hypothetical quarantine window lands QUARANTINED.
    # Use a synthetic game so the fake regime can't overlap real PB spans.
    from fortuna.schemas.regimes import GameRegime

    reg = GameRegime(
        regime_id="ZZ-R001", game_id="zz_game", statistical_regime_id="ZZ-S01",
        change_classification="matrix", first_affected_draw=date(2020, 1, 1),
        first_unambiguous_draw=date(2020, 1, 8),
        main_ball_count=5, main_ball_min=1, main_ball_max=69,
        special_ball_count=1, special_ball_min=1, special_ball_max=26,
        drawing_days=["wed", "sat"], verification_status="partially_verified",
    )
    a = _staged(game="zz_game", d=date(2020, 1, 4), nums=(1, 2, 3, 4, 5), sb=10)
    groups, _ = reconcile_groups([a])
    draws, _, _ = build_canonical(groups, [*regimes, reg])
    assert draws[0].validation_status == DrawValidationStatus.QUARANTINED
    apply_eligibility(draws, set(), [*regimes, reg])
    assert draws[0].analysis_eligible is False


# ---------- Source-authority gate (Phase 1 corrective) ----------

TIERS = {
    "SRC-WI-PB-CSV": 1,
    "SRC-MO-PB-XLSX": 1,
    "SRC-TX-PB-CSV": 1,
    "SRC-NY-PB-DATA": 2,
    "SRC-NY-PB-ARCHIVE": 3,
    "SRC-NY-MM-ARCHIVE": 3,
}


def test_tier3_only_draw_is_ineligible(regimes):
    a = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-NY-PB-ARCHIVE")
    groups, _ = reconcile_groups([a], TIERS)
    draws, _, ckeys = build_canonical(groups, regimes, TIERS)
    reasons = apply_eligibility(draws, ckeys, regimes, TIERS)
    assert draws[0].analysis_eligible is False
    assert "unofficial_source_only" in reasons[draws[0].draw_id]


def test_tier3_divergence_does_not_block_authoritative_draw(regimes):
    wi = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-WI-PB-CSV")
    ny = _staged(nums=(1, 2, 3, 4, 5), sb=11, src="SRC-NY-PB-ARCHIVE")
    groups, rows = reconcile_groups([ny, wi], TIERS)  # staged order irrelevant
    draws, _, ckeys = build_canonical(groups, regimes, TIERS)
    structural_validate(draws, regimes)
    reasons = apply_eligibility(draws, ckeys, regimes, TIERS)
    d = draws[0]
    assert d.analysis_eligible is True
    assert d.draw_id not in reasons
    assert d.source_id == "SRC-WI-PB-CSV"          # authoritative primary wins
    assert d.special_ball == 10
    assert "SRC-NY-PB-ARCHIVE" in d.corroborating_source_ids
    conf = [r for r in rows if r["classification"] == "CONFLICT"]
    assert conf and all(r["status"] == "resolved" for r in conf)


def test_authoritative_conflict_still_blocks(regimes):
    wi = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-WI-PB-CSV")
    mo = _staged(nums=(1, 2, 3, 4, 5), sb=11, src="SRC-MO-PB-XLSX")
    groups, _ = reconcile_groups([wi, mo], TIERS)
    draws, _, ckeys = build_canonical(groups, regimes, TIERS)
    reasons = apply_eligibility(draws, ckeys, regimes, TIERS)
    assert draws[0].analysis_eligible is False
    assert "unresolved_conflict" in reasons[draws[0].draw_id]


def test_official_resolution_applies_canonical_value(regimes):
    wi = _staged(nums=(1, 2, 3, 4, 5), sb=10, src="SRC-WI-PB-CSV")
    mo = _staged(nums=(1, 2, 3, 4, 5), sb=11, src="SRC-MO-PB-XLSX")
    res = {
        ("powerball", date(2020, 1, 4), "special_ball"): {
            "resolved_value": "10",
            "resolution": "first-party operator record controls",
            "resolution_evidence": "test",
            "status": "resolved",
        }
    }
    groups, _ = reconcile_groups([wi, mo], TIERS)
    draws, _, ckeys = build_canonical(groups, regimes, TIERS, res)
    structural_validate(draws, regimes)
    apply_eligibility(draws, ckeys, regimes, TIERS)
    assert draws[0].analysis_eligible is True
    assert draws[0].special_ball == 10
    assert not ckeys


def test_wi_csv_parser_drawn_order():
    content = (
        b'"Wisconsin Lottery - Powerball Winning Numbers - Order Drawn"\n'
        b'"Draw Date",,,,,,PB,"Power Play","Est. Jackpot"\n'
        b"1992-04-22,49,42,21,29,17,8,3x,$389.00M\n"
    )
    recs = parsers.parse_wi_powerball_csv(content, _art("SRC-WI-PB-CSV"))
    assert len(recs) == 1
    r = recs[0]
    assert r.draw_date == date(1992, 4, 22)
    assert r.main_numbers == [49, 42, 21, 29, 17]
    assert r.special_ball == 8 and r.multiplier == 3.0
    assert r.jackpot == 389_000_000
    assert r.numbers_order == OrderSemantics.PHYSICAL_DRAW_ORDER


def test_md_archive_html_parser():
    html = (
        b'<tr><td class="date">09/06/96</td>'
        b'<td class="numbers"><ul class="balls"><li>5</li><li>11</li>'
        b'<li>29</li><li>47</li><li>50</li></ul></td>'
        b'<td class="bonus"><ul class="balls"><li>6</li></ul></td>'
        b'<td class="multiplier">N/A</td></tr>'
    )
    recs = parsers.parse_md_archive_html(
        html, _art("SRC-MD-MM-ARCHIVE"), game_id="mega_millions"
    )
    assert len(recs) == 1
    assert recs[0].draw_date == date(1996, 9, 6)
    assert recs[0].main_numbers == [5, 11, 29, 47, 50]
    assert recs[0].special_ball == 6


def test_mm_com_api_parser():
    import json as _json

    inner = _json.dumps(
        {
            "DrawingData": [
                {
                    "PlayDate": "2011-09-23T00:00:00",
                    "N1": 21, "N2": 27, "N3": 32, "N4": 40, "N5": 52,
                    "MBall": "36", "Megaplier": -1,
                }
            ]
        }
    )
    content = _json.dumps({"d": inner}).encode()
    recs = parsers.parse_mm_com_api(content, _art("SRC-MM-COM-API"))
    assert len(recs) == 1
    assert recs[0].main_numbers == [21, 27, 32, 40, 52]
    assert recs[0].special_ball == 36 and recs[0].multiplier is None
