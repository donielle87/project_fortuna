"""Build the Phase 3 exploration/holdout split — METADATA ONLY.

Generates (under metadata/):
  phase3_exploration_ids.csv   draw_id + metadata columns only
  phase3_holdout_ids.csv       draw_id + metadata columns only
  phase3_split_summary.csv     per-regime counts, dates, segment lengths
  phase3_holdout_seal.json     dataset/policy/manifest/seal hashes

The split is chronological (last ceil(20%) per statistical regime),
never randomized, and built before any Phase 3 outcome read. No
winning-number field is parsed anywhere in this script: draw rows are
accessed through the whitelisted-metadata reader and the holdout seal
hashes raw row bytes by draw_id membership only.
"""

import json
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.analysis.split import build_phase3_split
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime

ROOT = Path(__file__).resolve().parent.parent
DRAWS = ROOT / "data/processed/draws.csv"
CONFIG = ROOT / "config/experiments/F-E002.yaml"
OUT = ROOT / "metadata"


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text())
    dataset_sha = json.loads(
        (ROOT / "data/processed/dataset_manifest.json").read_text()
    )["dataset_sha256"]
    assert dataset_sha == cfg["accepted_phase1_dataset_sha256"], (
        "Phase 1 dataset hash mismatch — frozen input violated"
    )
    regimes = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)

    res = build_phase3_split(DRAWS, regimes, cfg["split"], OUT)
    seal_doc = res["seal_doc"]
    seal_doc["dataset_sha256"] = dataset_sha
    seal_doc["created_utc"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
    )
    (OUT / "phase3_holdout_seal.json").write_text(
        json.dumps(seal_doc, indent=2)
    )

    n_expl = sum(len(v) for v in [res["exploration_ids"]])
    n_hold = sum(len(v) for v in [res["holdout_ids"]])
    print(f"exploration draws: {n_expl}  holdout draws: {n_hold}")
    print(f"holdout seal: {seal_doc['holdout_seal_sha256']}")
    for s in res["summary"]:
        print(
            f"  {s['statistical_regime_id']}: {s['exploration_count']} expl / "
            f"{s['holdout_count']} hold; expl end {s['exploration_end_date']}, "
            f"hold start {s['holdout_start_date']}; "
            f"{s['exploration_segments']} segments "
            f"[{s['exploration_segment_lengths']}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
