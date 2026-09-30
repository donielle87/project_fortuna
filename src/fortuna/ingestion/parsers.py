"""Deterministic parsers: raw artifact bytes -> StagedDraw records.

Every parser is pure: same bytes in -> same records out. No field is
inferred; order semantics reflect only what the source documents.
"""

import csv
import io
import json
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.etree import ElementTree as ET

from fortuna.ingestion.staging import StagedDraw
from fortuna.schemas.draws import DrawStream, OrderSemantics

PARSER_VERSION = "1.0.0"

_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _artifact_ctx(artifact) -> dict:
    return {
        "source_id": artifact.source_id,
        "artifact_sha256": artifact.sha256,
        "artifact_path": artifact.immutable_path,
        "retrieved_at": artifact.retrieved_at,
        "parser_version": PARSER_VERSION,
    }


def _socrata_rows(content: bytes) -> list:
    """Socrata resource export = JSON array. The api/views metadata artifact
    (a JSON object) yields [] here so only data artifacts produce draws."""
    obj = json.loads(content)
    return obj if isinstance(obj, list) else []


def parse_ny_socrata_powerball(content: bytes, artifact) -> list[StagedDraw]:
    """NY open-data Powerball: winning_numbers 'w1 w2 w3 w4 w5 PB' sorted."""
    rows = _socrata_rows(content)
    out: list[StagedDraw] = []
    for r in rows:
        d = datetime.fromisoformat(r["draw_date"]).date()
        parts = r["winning_numbers"].split()
        rec = StagedDraw(
            game_id="powerball",
            draw_date=d,
            draw_stream=DrawStream.MAIN,
            main_numbers=[int(p) for p in parts[:5]],
            special_ball=int(parts[5]),
            multiplier=float(r["multiplier"]) if r.get("multiplier") else None,
            numbers_order=OrderSemantics.SOURCE_SORTED_ORDER,
            **_artifact_ctx(artifact),
        )
        out.append(rec)
        dp = r.get("double_play_winning_numbers")
        if dp:
            dparts = dp.split()
            out.append(
                StagedDraw(
                    game_id="powerball",
                    draw_date=d,
                    draw_stream=DrawStream.DOUBLE_PLAY,
                    main_numbers=[int(p) for p in dparts[:5]],
                    special_ball=int(dparts[5]),
                    numbers_order=OrderSemantics.SOURCE_SORTED_ORDER,
                    notes="double play draw reported in Socrata double_play_winning_numbers",
                    **_artifact_ctx(artifact),
                )
            )
    return out


def parse_ny_socrata_megamillions(content: bytes, artifact) -> list[StagedDraw]:
    """NY open-data Mega Millions: winning_numbers 5 whites + mega_ball col."""
    rows = _socrata_rows(content)
    out: list[StagedDraw] = []
    for r in rows:
        d = datetime.fromisoformat(r["draw_date"]).date()
        parts = r["winning_numbers"].split()
        out.append(
            StagedDraw(
                game_id="mega_millions",
                draw_date=d,
                main_numbers=[int(p) for p in parts[:5]],
                special_ball=int(r["mega_ball"]) if r.get("mega_ball") else None,
                multiplier=float(r["multiplier"]) if r.get("multiplier") else None,
                numbers_order=OrderSemantics.SOURCE_SORTED_ORDER,
                **_artifact_ctx(artifact),
            )
        )
    return out


def _balls(block: str, cls: str) -> list[int]:
    return [
        int(x) for x in re.findall(rf'class="resultBall {cls}">(\d+)</span>', block)
    ]


def parse_ny_archive_html(
    content: bytes, artifact, *, slug: str, game_id: str, special_cls: str
) -> list[StagedDraw]:
    """NY Lottery official year-archive HTML pages (sorted order, jackpot).

    Powerball rows may embed a "Double Play" sub-block — that is a separate
    draw_stream, never folded into the main numbers. Power Play is taken
    from the 'Power Play: ×N' badge when present.
    """
    text = content.decode("utf-8", "replace")
    out: list[StagedDraw] = []
    for m in re.finditer(
        r'href="/' + slug + r'/results/(\d{2})-(\d{2})-(\d{4})"(.*?)</tr>',
        text, re.S,
    ):
        mm, dd, yy, body = m.group(1), m.group(2), m.group(3), m.group(4)
        d = date(int(yy), int(mm), int(dd))

        dp_i = body.find("Double Play")
        main_body = body[:dp_i] if dp_i != -1 else body
        dp_body = body[dp_i:] if dp_i != -1 else ""

        jm = re.search(r"<strong[^>]*>\$([\d,]+)</strong>", body)
        mult = None
        mmx = re.search(r"(?:Power Play|Megaplier)\s*:\s*<strong>&times;(\d+)", body)
        if mmx:
            mult = float(mmx.group(1))

        out.append(
            StagedDraw(
                game_id=game_id,
                draw_date=d,
                main_numbers=_balls(main_body, "ball"),
                special_ball=(
                    _balls(main_body, special_cls)[0]
                    if _balls(main_body, special_cls)
                    else None
                ),
                multiplier=mult,
                jackpot=Decimal(jm.group(1).replace(",", "")) if jm else None,
                numbers_order=OrderSemantics.SOURCE_SORTED_ORDER,
                **_artifact_ctx(artifact),
            )
        )
        if dp_body:
            out.append(
                StagedDraw(
                    game_id=game_id,
                    draw_date=d,
                    draw_stream=DrawStream.DOUBLE_PLAY,
                    main_numbers=_balls(dp_body, "ball"),
                    special_ball=(
                        _balls(dp_body, special_cls)[0]
                        if _balls(dp_body, special_cls)
                        else None
                    ),
                    numbers_order=OrderSemantics.SOURCE_SORTED_ORDER,
                    notes="double play sub-draw embedded in main row",
                    **_artifact_ctx(artifact),
                )
            )
    return out


_XLSX_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def _xlsx_rows(content: bytes) -> list[list[str]]:
    """Minimal xlsx reader: shared strings + first worksheet."""
    z = zipfile.ZipFile(io.BytesIO(content))
    ss: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{_XLSX_NS}si"):
            ss.append("".join(t.text or "" for t in si.iter(f"{_XLSX_NS}t")))
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows: list[list[str]] = []
    for r in sheet.iter(f"{_XLSX_NS}row"):
        row: list[str] = []
        for c in r.findall(f"{_XLSX_NS}c"):
            v = c.find(f"{_XLSX_NS}v")
            if v is None:
                row.append("")
            elif c.get("t") == "s":
                row.append(ss[int(v.text)])
            else:
                row.append(v.text or "")
        rows.append(row)
    return rows


def parse_mo_powerball_xlsx(content: bytes, artifact) -> list[StagedDraw]:
    """MO Lottery PB xlsx: 'Numbers As Drawn' is genuine physical order."""
    rows = _xlsx_rows(content)
    out: list[StagedDraw] = []
    for r in rows:
        if not r or not _XLSX_DATE_RE.match(r[0] or ""):
            continue
        dd, mm, yy = _XLSX_DATE_RE.match(r[0]).groups()  # type: ignore[union-attr]
        as_drawn = [int(x) for x in r[1].split("--") if x.strip()]
        in_order = [int(x) for x in r[2].split("--") if x.strip()]
        if not as_drawn or not in_order:
            continue
        jackpot = None
        jm = re.search(r"\$([\d.]+)\s*(million|billion)?", r[5] or "", re.I)
        if jm:
            val = Decimal(jm.group(1))
            if (jm.group(2) or "").lower() == "billion":
                val *= 1_000_000_000
            else:
                val *= 1_000_000
            jackpot = val
        # 'Numbers As Drawn' differing from sorted proves physical-order
        # capture; identical columns are unverifiable (likely backfilled).
        order = (
            OrderSemantics.PHYSICAL_DRAW_ORDER
            if as_drawn != in_order
            else OrderSemantics.UNKNOWN_ORDER
        )
        out.append(
            StagedDraw(
                game_id="powerball",
                draw_date=date(int(yy), int(mm), int(dd)),
                main_numbers=as_drawn,
                special_ball=int(r[3]) if r[3] else None,
                multiplier=float(r[4]) if r[4] not in ("", "0") else None,
                jackpot=jackpot,
                numbers_order=order,
                notes=None if as_drawn != in_order else "as_drawn==sorted (backfill suspected)",
                **_artifact_ctx(artifact),
            )
        )
    return out


def parse_tx_csv(content: bytes, artifact, *, game_id: str) -> list[StagedDraw]:
    """Texas Lottery CSV: 'Game,MM,DD,YYYY,n1..n5,special,multiplier'.

    Numbers are listed in draw order (unsorted) => physical_draw_order.
    """
    text = content.decode("utf-8-sig", "replace")
    out: list[StagedDraw] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 10 or not row[0].strip():
            continue
        try:
            d = date(int(row[3]), int(row[1]), int(row[2]))
            nums = [int(row[i]) for i in range(4, 9)]
            special = int(row[9])
            mult = float(row[10]) if len(row) > 10 and row[10].strip() else None
        except (ValueError, IndexError):
            continue
        out.append(
            StagedDraw(
                game_id=game_id,
                draw_date=d,
                main_numbers=nums,
                special_ball=special,
                multiplier=mult,
                numbers_order=OrderSemantics.PHYSICAL_DRAW_ORDER,
                **_artifact_ctx(artifact),
            )
        )
    return out


_PDF_ROW_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2})\s+(.*)")


def _yy2(year2: str) -> int:
    # Archives span 1988-; pivot at 50: '88'..'49' -> 1988..2049 is impossible
    # to misread because no draw predates 1988 and none postdates 2049.
    y = int(year2)
    return 2000 + y if y < 50 else 1900 + y


def parse_fl_pdf(
    content: bytes,
    artifact,
    *,
    game_id: str,
    lotto_sorted_after: date | None = None,
) -> list[StagedDraw]:
    """Florida Lottery history PDFs (pypdf text extraction)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    lines: list[str] = []
    for page in reader.pages:
        lines += page.extract_text().splitlines()
    return parse_fl_history_lines(
        lines, artifact, game_id=game_id, lotto_sorted_after=lotto_sorted_after
    )


def parse_fl_history_lines(
    lines: list[str],
    artifact,
    *,
    game_id: str,
    lotto_sorted_after: date | None = None,
) -> list[StagedDraw]:
    """Parse extracted FL history-PDF text lines -> staged draws.

    Line forms:
      Lotto:   '9/26/26 1 5 10 15 35 45 LOTTO 5 / D' | '... LOTTO DP 1 / C'
               pre-DP era: '5/7/88 30 44 17 49 42 15' (no tag)
               XTRA era:   '7/1/20 12 20 23 37 48 51 X4 3 / C' (multiplier+
               machine/ball, no tag)
      PB:      '9/28/26 17 21 29 42 49 PB 7 X3 POWERBALL' | '... POWERBALL DP'
      MM:      '09/25/26 25 57 58 67 68 MB 16' (+ optional ' X4')
    """
    out: list[StagedDraw] = []
    for line in lines:
        line = line.strip()
        m = _PDF_ROW_RE.match(line)
        if not m:
            continue
        mm, dd, yy, rest = m.groups()
        d = date(_yy2(yy), int(mm), int(dd))
        upper = rest.upper()
        stream = DrawStream.MAIN
        machine_id = ball_set_id = None
        mult = None
        special: int | None = None

        if game_id == "florida_lotto":
            gm = re.search(
                r"\b(LOTTO DP|LOTTO)\b\s*(\d+|[A-Za-z])?\s*/?\s*([A-Za-z0-9]+)?$",
                upper,
            )
            if gm:
                nums_txt = rest[: gm.start()].strip()
                stream = DrawStream.DOUBLE_PLAY if gm.group(1) == "LOTTO DP" else DrawStream.MAIN
                machine_id, ball_set_id = gm.group(2), gm.group(3)
            else:
                xm = re.search(
                    r"\bX(\d+)\s+(\d+|[A-Za-z])\s*/\s*([A-Za-z0-9]+)\s*$", upper
                )
                if xm:
                    # XTRA-era rows: 'X4 3 / C' = multiplier + machine/ball
                    nums_txt = rest[: xm.start()].strip()
                    mult = float(xm.group(1))
                    machine_id, ball_set_id = xm.group(2), xm.group(3)
                elif re.fullmatch(r"[\d ]+", rest):
                    # Pre-XTRA rows carry no game tag:
                    # '5/7/88 30 44 17 49 42 15' => main draw.
                    nums_txt = rest
                else:
                    continue
        elif game_id == "powerball":
            gm = re.search(r"\bPB\s+(\d+)\b(?:\s+X(\d+))?\s+(POWERBALL DP|POWERBALL)\b", upper)
            if not gm:
                continue
            nums_txt = rest[: gm.start()].strip()
            special = int(gm.group(1))
            mult = float(gm.group(2)) if gm.group(2) else None
            stream = DrawStream.DOUBLE_PLAY if "DP" in gm.group(3) else DrawStream.MAIN
        else:  # mega_millions
            gm = re.search(r"\bMB\s+(\d+)\b(?:\s+X(\d+))?", upper)
            if not gm:
                continue
            nums_txt = rest[: gm.start()].strip()
            special = int(gm.group(1))
            mult = float(gm.group(2)) if gm.group(2) else None

        nums = [int(x) for x in nums_txt.split() if x.isdigit()]
        if not nums:
            continue
        order = OrderSemantics.UNKNOWN_ORDER
        notes = None
        if game_id == "florida_lotto" and lotto_sorted_after is not None:
            order = (
                OrderSemantics.PHYSICAL_DRAW_ORDER
                if d < lotto_sorted_after
                else OrderSemantics.SOURCE_SORTED_ORDER
            )
        elif game_id in ("powerball", "mega_millions"):
            # FL PB/MM PDFs list numbers sorted ascending; a rare
            # unsorted row is flagged, not treated as draw order.
            order = OrderSemantics.SOURCE_SORTED_ORDER
            if nums != sorted(nums):
                notes = "row not sorted in a sorted-order source"
        rec = StagedDraw(
            game_id=game_id,
            draw_date=d,
            draw_stream=stream,
            main_numbers=nums,
            special_ball=special,
            multiplier=mult,
            machine_id=machine_id,
            ball_set_id=ball_set_id,
            numbers_order=order,
            notes=notes,
            **_artifact_ctx(artifact),
        )
        out.append(rec)
    return out


def parse_wi_powerball_csv(content: bytes, artifact) -> list[StagedDraw]:
    """Wisconsin Lottery official CSV export (dir=drawn => physical order).

    Layout: date, n1..n5, PB, "Power Play" ('3x' or ' '), jackpot ('$389.00M').
    """
    text = content.decode("utf-8-sig", "replace")
    out: list[StagedDraw] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 9:
            continue
        try:
            d = date.fromisoformat(row[0].strip())
        except ValueError:
            continue
        try:
            nums = [int(row[i]) for i in range(1, 6)]
            pb = int(row[6])
        except ValueError:
            continue
        mult = None
        if len(row) > 7:
            mm = re.search(r"(\d+)", row[7] or "")
            if mm:
                mult = float(mm.group(1))
        jackpot = None
        if len(row) > 8:
            jm = re.search(r"\$([\d.]+)M", row[8] or "")
            if jm:
                jackpot = Decimal(jm.group(1)) * 1_000_000
        out.append(
            StagedDraw(
                game_id="powerball",
                draw_date=d,
                main_numbers=nums,
                special_ball=pb,
                multiplier=mult,
                jackpot=jackpot,
                numbers_order=OrderSemantics.PHYSICAL_DRAW_ORDER,
                **_artifact_ctx(artifact),
            )
        )
    return out


_MD_ROW_RE = re.compile(
    r'<td class="date">(\d{2})/(\d{2})/(\d{2})</td>'
    r'<td class="numbers"><ul class="balls">(.*?)</ul></td>'
    r'<td class="bonus"><ul class="balls"><li[^>]*>(\d+)</li></ul></td>'
    r'<td class="multiplier">([^<]*)</td>',
    re.S,
)


def parse_md_archive_html(
    content: bytes, artifact, *, game_id: str
) -> list[StagedDraw]:
    """Maryland Lottery winning-number archive HTML (sorted order)."""
    text = content.decode("utf-8", "replace")
    out: list[StagedDraw] = []
    for m in _MD_ROW_RE.finditer(text):
        mm, dd, yy, ball_block, bonus, mult = m.groups()
        nums = [int(x) for x in re.findall(r"<li>(\d+)</li>", ball_block)]
        if len(nums) != 5:
            continue
        mv = mult.strip()
        out.append(
            StagedDraw(
                game_id=game_id,
                draw_date=date(_yy2(yy), int(mm), int(dd)),
                main_numbers=nums,
                special_ball=int(bonus),
                multiplier=(
                    float(mv.lstrip("xX"))
                    if mv not in ("N/A", "", "x")
                    else None
                ),
                numbers_order=OrderSemantics.SOURCE_SORTED_ORDER,
                **_artifact_ctx(artifact),
            )
        )
    return out


def parse_mm_com_api(content: bytes, artifact) -> list[StagedDraw]:
    """Official Mega Millions operator API page (sorted order).

    Response: {"d": "<json>"} where inner JSON has DrawingData rows with
    PlayDate, N1..N5, MBall, Megaplier (-1 = none).
    """
    payload = json.loads(content)
    inner = json.loads(payload["d"])
    out: list[StagedDraw] = []
    for r in inner.get("DrawingData", []):
        d = datetime.fromisoformat(r["PlayDate"]).date()
        mp = r.get("Megaplier")
        out.append(
            StagedDraw(
                game_id="mega_millions",
                draw_date=d,
                main_numbers=[r["N1"], r["N2"], r["N3"], r["N4"], r["N5"]],
                special_ball=int(r["MBall"]),
                multiplier=float(mp) if mp is not None and mp > 0 else None,
                numbers_order=OrderSemantics.SOURCE_SORTED_ORDER,
                **_artifact_ctx(artifact),
            )
        )
    return out
