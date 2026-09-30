"""Fetch Phase 1 historical draw sources into the immutable artifact store.

Each URL fetched is stored under its source_id with SHA-256 provenance.
Pagination sources (NY Lottery year archive) produce one artifact per page
under the same source_id — the artifact manifest records every page.

Usage: python scripts/fetch_draw_sources.py
"""

import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.ingestion.fetch import fetch_bytes, fetch_post_bytes
from fortuna.provenance.store import ArtifactStore

CURRENT_YEAR = datetime.now().year
TODAY = date.today()

# nylottery.org is an independent unofficial service (Tier 3). It is no
# longer fetched; previously preserved artifacts remain for reconciliation.

# (source_id, url) pairs. NY Lottery archive is year-paginated.
FETCHES: list[tuple[str, str]] = [
    # Wisconsin Lottery official CSV export — Powerball 1992-04-22 onward,
    # physical draw order (dir=drawn)
    (
        "SRC-WI-PB-CSV",
        "https://wilottery.com/winners/draw-history?csv=1&game=powerball"
        "&start=04/22/1992&end=" + TODAY.strftime("%m/%d/%Y") + "&dir=drawn",
    ),
    # Maryland Lottery official winning-number archive — Mega Millions/Big
    # Game back to first draw 1996-09-06 (MD is a founding member)
    (
        "SRC-MD-MM-ARCHIVE",
        "https://www.mdlottery.com/wp-admin/admin-ajax.php?action=jquery_shortcode"
        "&shortcode=find_numbers&atts=%7B%22game%22%3A%22mega-millions%22%2C"
        "%22start%22%3A%2209%2F01%2F1996%22%2C%22end%22%3A%22"
        + TODAY.strftime("%m%%2F%d%%2F%Y")
        + "%22%2C%22method%22%3A%22ANY%22%7D",
    ),
    # Maryland Lottery official Powerball archive (MD joined PB 2010-01-30;
    # supplementary corroboration for the modern era)
    (
        "SRC-MD-PB-ARCHIVE",
        "https://www.mdlottery.com/wp-admin/admin-ajax.php?action=jquery_shortcode"
        "&shortcode=find_numbers&atts=%7B%22game%22%3A%22powerball%22%2C"
        "%22start%22%3A%2201%2F01%2F2010%22%2C%22end%22%3A%22"
        + TODAY.strftime("%m%%2F%d%%2F%Y")
        + "%22%2C%22method%22%3A%22ANY%22%7D",
    ),
    # Official Mega Millions (operator) correction statement for the
    # 2022-05-10 drawing — host miscalled Mega Ball 9 as 6.
    (
        "SRC-MM-2022-CORRECTION",
        "https://www.megamillions.com/News/2022/"
        "Statement-on-the-May-10,-2022,-Mega-Millions%C2%AE-Draw.aspx",
    ),
    # NY State open-data full exports
    (
        "SRC-NY-PB-DATA",
        "https://data.ny.gov/resource/d6yy-54nr.json?$limit=50000&$order=draw_date",
    ),
    (
        "SRC-NY-MM-DATA",
        "https://data.ny.gov/resource/5xaw-6ayf.json?$limit=50000&$order=draw_date",
    ),
    # Missouri Lottery official Powerball xlsx (1998+, as-drawn order)
    (
        "SRC-MO-PB-XLSX",
        "https://www.molottery.com/powerball/past-winning-numbers.do?order=desc",
    ),
    # Texas Lottery official CSVs
    (
        "SRC-TX-PB-CSV",
        "https://www.texaslottery.com/export/sites/lottery/Games/Powerball/"
        "Winning_Numbers/powerball.csv",
    ),
    (
        "SRC-TX-MM-CSV",
        "https://www.texaslottery.com/export/sites/lottery/Games/Mega_Millions/"
        "Winning_Numbers/megamillions.csv",
    ),
    # Florida Lottery official history PDFs (curl fallback handles its TLS)
    (
        "SRC-FL-PB-HIST-PDF",
        "https://files.floridalottery.com/exptkt/"
        "powerball_winning-numbers-history.pdf",
    ),
    (
        "SRC-FL-MM-HIST-PDF",
        "https://files.floridalottery.com/exptkt/"
        "mega-millions_winning-numbers-history.pdf",
    ),
    (
        "SRC-FL-LOTTO-HIST-PDF",
        "https://files.floridalottery.com/exptkt/"
        "lotto_winning-numbers-history.pdf",
    ),
]

# Official Mega Millions operator API (megamillions.com asmx). Coverage
# begins 2010-02-05; paged at the service's max pageSize (200).
MM_API = (
    "https://www.megamillions.com/cmspages/utilservice.asmx/"
    "GetDrawingPagingData"
)
MM_API_FIRST_PAGE = 1
MM_API_START = "01/01/2010"


def main() -> int:
    store = ArtifactStore()
    ok = fail = 0
    for source_id, url in FETCHES:
        try:
            got = fetch_bytes(url, timeout=60)
            hint = url.rsplit("/", 1)[-1].split("?")[0] or None
            art = store.store(
                source_id=source_id,
                content=got.content,
                mime_type=got.mime_type,
                filename_hint=hint,
            )
            print(f"[ok] {source_id} {url} -> {art.sha256[:12]} via {got.via}")
            ok += 1
        except Exception as exc:  # noqa: BLE001 - report every fetch, keep going
            print(f"[FAIL] {source_id} {url}: {exc}")
            fail += 1
        time.sleep(0.4)  # be polite to the operators

    # Official Mega Millions operator API — paginated POST JSON, one artifact
    # per page under SRC-MM-COM-API.
    import json as _json

    page = MM_API_FIRST_PAGE
    end = TODAY.strftime("%m/%d/%Y")
    while True:
        body = {
            "startDate": MM_API_START,
            "endDate": end,
            "pageNumber": page,
            "pageSize": 200,
        }
        try:
            got = fetch_post_bytes(MM_API, body, timeout=60)
            art = store.store(
                source_id="SRC-MM-COM-API",
                content=got.content,
                mime_type=got.mime_type,
                filename_hint=f"mm_api_p{page}.json",
            )
            payload = _json.loads(got.content)
            inner = _json.loads(payload["d"])
            print(
                f"[ok] SRC-MM-COM-API page {page} -> {art.sha256[:12]} "
                f"({len(inner['DrawingData'])} rows)"
            )
            ok += 1
            if page * 200 >= inner["TotalResults"] or not inner["DrawingData"]:
                break
            page += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] SRC-MM-COM-API page {page}: {exc}")
            fail += 1
            break
        time.sleep(0.4)
    print(f"\n{ok} fetched, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
