"""Build the corrected (v2) Phase 3 exploration set — METADATA ONLY.

The F-E002 holdout population (metadata/phase3_holdout_ids.csv) is
FROZEN: never recomputed, resized, or moved. Under the corrected Phase 1
dataset (D-007/D-008):

  corrected exploration = original exploration IDs INTERSECT corrected
                          analysis-eligible canonical draws

Generates (under metadata/):
  phase3_exploration_ids_v2.csv   corrected exploration manifest
  phase3_split_summary_v2.csv     per-regime corrected counts/segments
  phase3_holdout_seal_v2.json     seal of the SAME frozen holdout IDs
                                  against the corrected canonical rows

The v1 seal (phase3_holdout_seal.json) is preserved untouched as the
historical F-E002 record. No winning-number field is parsed anywhere in
this script: rows are accessed through the whitelisted-metadata reader
and the holdout seal hashes raw row bytes by draw_id membership only.
"""

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.analysis.split import build_corrected_split
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime

ROOT = Path(__file__).resolve().parent.parent
DRAWS = ROOT / "data/processed/draws.csv"
META = ROOT / "metadata"


def _ids(path: Path) -> set[str]:
    with path.open(newline="") as f:
        return {r["draw_id"] for r in csv.DictReader(f)}


def main() -> int:
    dataset_sha = json.loads(
        (ROOT / "data/processed/dataset_manifest.json").read_text()
    )["dataset_sha256"]
    v1_seal = json.loads((META / "phase3_holdout_seal.json").read_text())
    assert v1_seal["holdout_seal_sha256"] == (
        "6cb7c382924c4ad55ab0958239cb488cd95b0e0b99407ebebcfe822a4b16b91c"
    ), "v1 seal document is not the accepted historical record"

    hold_ids = _ids(META / "phase3_holdout_ids.csv")
    orig_expl = _ids(META / "phase3_exploration_ids.csv")
    assert len(hold_ids) == 2072 and len(orig_expl) == 8260, (
        "frozen F-E002 split populations changed"
    )

    regimes = load_csv(META / "game_regimes.csv", GameRegime)
    res = build_corrected_split(DRAWS, regimes, hold_ids, orig_expl, META)

    seal_doc = {
        "phase": 3,
        "experiment_id": "F-E003",
        "seal_version": 2,
        "supersedes": "metadata/phase3_holdout_seal.json (v1, F-E002)",
        "dataset_sha256": dataset_sha,
        "corrected_exploration_manifest_sha256":
            res["exploration_manifest_sha256"],
        "holdout_manifest_sha256": v1_seal["holdout_manifest_sha256"],
        "holdout_seal_sha256": res["seal_sha256"],
        "holdout_id_population": "frozen original F-E002 IDs (2072)",
        "holdout_counts": {
            s["statistical_regime_id"]: s["holdout_count"]
            for s in res["summary"]
        },
        "exploration_counts": {
            s["statistical_regime_id"]: s["exploration_count"]
            for s in res["summary"]
        },
        "exploration_removed_draw_ids": res["removed_exploration_ids"],
        "invalidated_holdout_ids": res["invalidated_holdout_ids"],
        "note": (
            "Same frozen holdout ID set as v1; row bytes differ because "
            "D-007 added atomic sequence provenance to the canonical "
            "schema. Outcome fields are never parsed."
        ),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (META / "phase3_holdout_seal_v2.json").write_text(
        json.dumps(seal_doc, indent=2)
    )

    print(f"frozen holdout IDs: {len(hold_ids)} (unchanged)")
    print(f"corrected exploration draws: {len(res['exploration_ids'])}")
    print(
        f"exploration IDs removed by exclusions: "
        f"{len(res['removed_exploration_ids'])}"
    )
    print(
        f"invalidated holdout IDs: "
        f"{len(res['invalidated_holdout_ids'])}"
    )
    print(f"v2 holdout seal: {res['seal_sha256']}")
    for s in res["summary"]:
        print(
            f"  {s['statistical_regime_id']}: {s['exploration_count']} expl "
            f"(-{s['exploration_removed_count']}) / {s['holdout_count']} "
            f"hold (frozen); {s['exploration_segments']} segments "
            f"[{s['exploration_segment_lengths']}]; order-eligible "
            f"{s['order_eligible_exploration_count']} "
            f"[{s['order_eligible_segment_lengths']}]"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
