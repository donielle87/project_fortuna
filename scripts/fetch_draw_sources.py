"""Fetch Phase 1 historical draw sources into the immutable artifact store.

Each URL fetched is stored under its source_id with SHA-256 provenance.
Pagination sources (NY Lottery year archive) produce one artifact per page
under the same source_id — the artifact manifest records every page.

Usage: python scripts/fetch_draw_sources.py
"""

import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.ingestion.fetch import fetch_bytes
from fortuna.provenance.store import ArtifactStore

CURRENT_YEAR = datetime.now().year

# (source_id, url) pairs. NY Lottery archive is year-paginated.
FETCHES: list[tuple[str, str]] = [
    # NY Lottery official year archive — Powerball back to 1992-04-22
    *[
        (
            "SRC-NY-PB-ARCHIVE",
            f"https://www.nylottery.org/powerball/past-winning-numbers/{y}",
        )
        for y in range(1992, CURRENT_YEAR + 1)
    ],
    # NY Lottery official year archive — Mega Millions/Big Game back to 1996-09-06
    *[
        (
            "SRC-NY-MM-ARCHIVE",
            f"https://www.nylottery.org/mega-millions/past-winning-numbers/{y}",
        )
        for y in range(1996, CURRENT_YEAR + 1)
    ],
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
    print(f"\n{ok} fetched, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
