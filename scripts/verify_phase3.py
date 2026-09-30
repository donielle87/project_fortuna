"""Phase 3 F-E002 verifier — IMMUTABLE HISTORICAL RECORD.

F-E002 ran against the pre-correction Phase 1 dataset (953c0701...) and
is preserved as history. After the D-007/D-008 corrective cycle the
live checks moved to scripts/verify_phase3_corrected.py (F-E003). This
verifier now proves F-E002's artifacts have not been rewritten:

  * every F-E002 artifact is byte-identical to the accepted exploratory
    commit 7463bdb (no part of F-E002 was retro-edited)
  * the v1 holdout seal document still records the original seal
  * the original holdout ID manifest still holds exactly 2,072 IDs and
    is disjoint from every exploration manifest
  * no holdout draw_id appears in any F-E002 analysis output
  * the exploration-only loader's structural firewall still holds
  * F-E002's qualifying flags were all promoted or adjudicated
  * no predictive artifacts were created by Phase 3

Never reads holdout outcomes.
"""

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "metadata"
OUT = ROOT / "data/analysis/phase3"
CONFIG = ROOT / "config/experiments/F-E002.yaml"
FE002_COMMIT = "7463bdb3805dd68aab30a9feddcf992600678783"
V1_SEAL = "6cb7c382924c4ad55ab0958239cb488cd95b0e0b99407ebebcfe822a4b16b91c"
FAILS: list[str] = []

# Every artifact that constitutes the immutable F-E002 record.
FE002_PATHS = [
    "config/experiments/F-E002.yaml",
    "research/preregistrations/F-E002-phase3-exploratory-analysis.md",
    "metadata/phase3_exploration_ids.csv",
    "metadata/phase3_holdout_ids.csv",
    "metadata/phase3_holdout_seal.json",
    "metadata/phase3_split_summary.csv",
    "data/analysis/phase3",
    "reports/phase3/phase3_exploratory_analysis.md",
]


def check(ok: bool, name: str) -> None:
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()


def _ids(path: Path) -> set[str]:
    with path.open(newline="") as f:
        return {r["draw_id"] for r in csv.DictReader(f)}


def _read(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    # ---- F-E002 immutability -------------------------------------------
    diff = _git(["diff", "--name-only", FE002_COMMIT, "HEAD", "--"]
                + FE002_PATHS)
    check(diff == "", f"F-E002 artifacts unmodified since {FE002_COMMIT[:7]}")
    wt = _git(["status", "--porcelain", "--"] + FE002_PATHS)
    check(wt == "", "F-E002 artifacts clean in working tree")

    # ---- v1 seal record preserved ---------------------------------------
    seal_path = META / "phase3_holdout_seal.json"
    check(seal_path.exists(), "v1 holdout seal document exists")
    seal_doc = json.loads(seal_path.read_text())
    check(seal_doc["holdout_seal_sha256"] == V1_SEAL,
          "v1 seal hash preserved")
    check(seal_doc["dataset_sha256"] ==
          "953c0701aeef6782a361146999ca43c1d4d2863d807c8e4dbe39cfa4108f3891",
          "v1 seal pins original (pre-correction) dataset hash")

    # ---- frozen holdout manifest ----------------------------------------
    expl_path = META / "phase3_exploration_ids.csv"
    hold_path = META / "phase3_holdout_ids.csv"
    expl_ids = _ids(expl_path)
    hold_ids = _ids(hold_path)
    check(len(hold_ids) == 2072, "frozen holdout still 2,072 IDs")
    check(len(expl_ids) == 8260, "original exploration still 8,260 IDs")
    check(not (expl_ids & hold_ids), "original split disjoint")
    v2_path = META / "phase3_exploration_ids_v2.csv"
    if v2_path.exists():
        expl_v2 = _ids(v2_path)
        check(not (expl_v2 & hold_ids),
              "corrected exploration shares no holdout ID")
        check(expl_v2 <= expl_ids,
              "corrected exploration is a subset of original IDs")

    # ---- no holdout leakage into F-E002 outputs --------------------------
    analysis_files = list(OUT.glob("*.csv"))
    check(len(analysis_files) >= 13, "all F-E002 outputs exist")
    leaked = []
    for p in analysis_files:
        for line in p.read_text().splitlines()[1:]:
            first = line.split(",", 1)[0]
            if first in hold_ids:
                leaked.append(f"{p.name}:{first}")
    check(not leaked, f"no holdout draw_id in F-E002 outputs {leaked[:5]}")

    # ---- loader firewall self-test ---------------------------------------
    from fortuna.analysis.loader import load_exploration_draws

    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "draws.csv"
        fake.write_text(
            "draw_id,game_id,regime_id,draw_date,scheduled_datetime,"
            "drawing_identifier,draw_stream,main_numbers,numbers_order,"
            "number_sequence_source_id,"
            "special_ball,multiplier,jackpot,jackpot_cash_value,"
            "jackpot_winners,drawing_location,machine_id,ball_set_id,"
            "source_id,retrieved_at,raw_artifact_sha256,parser_version,"
            "ingestion_version,validation_status,analysis_eligible,"
            "provisional,data_quality_notes,corroborating_source_ids\n"
            "E1,g,FL-R001,2020-01-01,,,main,1;2;3;4;5;6,"
            "physical_draw_order,SRC-X,"
            ",,,,,,,,,,,,valid,true,false,,\n"
            "H1,g,FL-R001,2020-01-02,,,main,TRAP,physical_draw_order,SRC-X,"
            ",,,,,,,,,,,,valid,true,false,,\n"
        )
        try:
            load_exploration_draws(fake, {"E1"})
            fw_ok = True
        except Exception:
            fw_ok = False
        check(fw_ok, "loader skips non-exploration trap fields")
        try:
            load_exploration_draws(fake, {"E1", "H1"})
            trap_ok = False
        except ValueError:
            trap_ok = True
        check(trap_ok, "loader fails if holdout id is admitted")

    # ---- F-E002 internal consistency (self-contained) --------------------
    import yaml

    cfg = yaml.safe_load(CONFIG.read_text())
    prom = cfg["promotion"]
    prim_p = _read(OUT / "phase3_primary_pvalues.csv")
    sec = _read(OUT / "phase3_secondary_pvalues.csv")
    hyps = _read(OUT / "phase3_candidate_hypotheses.csv")
    adj = _read(OUT / "phase3_artifact_diagnostics.csv")
    qualifying = {
        (r["statistical_regime_id"], r["statistic_id"])
        for r in prim_p + sec
        if r["bh_flag"] == "True" and abs(float(r["z"])) >= prom["abs_z_min"]
    }
    promoted = {(h["statistical_regime"], h["test_statistic"]) for h in hyps}
    explained = {
        (r["statistical_regime_id"], r["affected_statistics"])
        for r in adj
        if r["artifact"] == "flag_adjudication" and "EXPLAINED" in r["detail"]
    }
    check(
        qualifying == promoted | explained,
        "F-E002 qualifying flags all adjudicated "
        f"({len(qualifying)} = {len(promoted)} promoted + "
        f"{len(explained)} explained)",
    )
    man = json.loads((OUT / "phase3_analysis_manifest.json").read_text())
    check(man["holdout_seal_sha256"] == V1_SEAL,
          "F-E002 manifest records v1 seal")
    check(man.get("candidate_hypotheses", -1) == len(hyps),
          "F-E002 manifest hypothesis count matches")

    # ---- prohibited products ----------------------------------------------
    banned_files = [
        p for p in OUT.iterdir()
        if any(t in p.name.lower()
               for t in ("best", "hot", "cold", "likely", "recommended",
                         "ticket", "prediction"))
    ]
    check(not banned_files, f"no prohibited output files {banned_files}")
    # Phase 4A (F-E005) legitimately registered the frozen F-M family;
    # anything else — or any logged prediction — remains prohibited.
    import csv as _csv
    allowed_models = {"F-M000", "F-M001", "F-M002", "F-M003", "F-M004"}
    mr = ROOT / "registry/model_registry.csv"
    model_rows = list(_csv.DictReader(mr.open())) if mr.exists() else []
    check(
        {r["model_id"] for r in model_rows} <= allowed_models,
        "only authorized F-E005 models registered",
    )
    pl = ROOT / "registry/prediction_ledger.csv"
    check(
        not pl.exists() or len(pl.read_text().splitlines()) <= 1,
        "no predictions registered",
    )

    if FAILS:
        print(f"PHASE 3 (F-E002 IMMUTABILITY) VERIFICATION FAILED "
              f"({len(FAILS)} checks)")
        return 1
    print("PHASE 3 (F-E002 IMMUTABILITY) VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
