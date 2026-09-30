"""Fetch every registered source into the immutable raw-artifact store.

Updates retrieved_at / content_sha256 / local_raw_path in the source registry
and appends to metadata/raw_artifacts.csv. Re-runnable: unchanged content is
deduped by SHA-256 (retrieval event still logged); changed content produces a
new artifact, never an overwrite.

Usage: python scripts/fetch_sources.py [--only SRC-ID] [--timeout 45]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.ingestion.fetch import fetch_source  # noqa: E402
from fortuna.provenance.store import ArtifactStore  # noqa: E402
from fortuna.sources.registry import load_source_registry, save_source_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="fetch a single source_id")
    ap.add_argument("--timeout", type=float, default=45.0)
    args = ap.parse_args()

    registry_path = Path("metadata/source_registry.csv")
    sources = load_source_registry(registry_path)
    store = ArtifactStore()

    ok, fail = 0, 0
    for src in sources:
        if args.only and src.source_id != args.only:
            continue
        try:
            art = fetch_source(src, store, timeout=args.timeout)
            src.retrieved_at = art.retrieved_at
            src.content_sha256 = art.sha256
            src.local_raw_path = art.immutable_path
            print(f"OK   {src.source_id}: {art.sha256[:12]} via {art.immutable_path}")
            ok += 1
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"FAIL {src.source_id}: {type(exc).__name__}: {exc}")
            fail += 1

    save_source_registry(sources, registry_path)
    print(f"\n{ok} fetched, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
