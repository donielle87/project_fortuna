"""Build metadata/phase2_observation_plan.csv from the canonical dataset.

Metadata-only: reads game/date/regime/eligibility/stream/order-semantics —
never winning-number values. Phase 2 uses the plan to size Monte Carlo
replicate histories and to place sequential segment boundaries.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime
from fortuna.simulation.observation import (
    build_observation_plan,
    observation_plan_hash,
    write_observation_plan,
)

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    man = json.loads((ROOT / "data/processed/dataset_manifest.json").read_text())
    dataset_sha = man["dataset_sha256"]
    regimes = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)
    rows = build_observation_plan(
        ROOT / "data/processed/draws.csv", regimes, dataset_sha
    )
    out = ROOT / "metadata/phase2_observation_plan.csv"
    write_observation_plan(out, rows)
    print(f"wrote {out} ({len(rows)} statistical regimes)")
    print(f"observation_plan_sha256: {observation_plan_hash(rows)}")
    for r in rows:
        print(
            f"  {r['statistical_regime_id']}: n={r['eligible_main_draw_count']} "
            f"segments={r['num_contiguous_segments']} "
            f"({r['contiguous_sequence_segment_lengths'][:60]})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
