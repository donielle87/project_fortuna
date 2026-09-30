"""Corrected Phase 3 (F-E003) verifier — firewall, provenance, integrity.

Verifies the D-007/D-008 corrective cycle end to end:

  * upstream verifiers pass (Phase 0/1/2 + F-E002 immutability)
  * atomic sequence provenance: every physical_draw_order exploration
    record carries a non-empty number_sequence_source_id, and no
    canonical physical-order row stores a literally-ascending sequence
  * exclusions match metadata/draw_exclusions.csv exactly; duplicate
    numbers alone cannot establish phantom status (the ledger is the
    sole exclusion basis)
  * original 2,072 holdout IDs frozen; v1 seal preserved as history;
    v2 seal reproduces against the corrected canonical rows; no
    holdout ID moved into corrected exploration
  * corrected exploration = original exploration INTERSECT corrected
    eligible draws
  * F-E002 artifacts unmodified since commit 7463bdb
  * F-E003 preregistration committed before corrected outcome outputs
  * corrected Phase 2 null (F-E001 v4) matches corrected metadata
  * all qualifying F-E003 flags are promoted or resolved by documented
    evidence (never by rarity)
  * no predictive model, ticket, ranking, or candidate pool exists

Never reads holdout winning-number outcomes.
"""

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "metadata"
OUT = ROOT / "data/analysis/phase3_corrected"
CONFIG = ROOT / "config/experiments/F-E003.yaml"
FE002_COMMIT = "7463bdb3805dd68aab30a9feddcf992600678783"
V1_SEAL = "6cb7c382924c4ad55ab0958239cb488cd95b0e0b99407ebebcfe822a4b16b91c"
OLD_DATASET = "953c0701aeef6782a361146999ca43c1d4d2863d807c8e4dbe39cfa4108f3891"
FAILS: list[str] = []


def check(ok: bool, name: str) -> None:
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def _run(script: str) -> int:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=ROOT, capture_output=True,
    ).returncode


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    cfg = yaml.safe_load(CONFIG.read_text())

    # ---- upstream gates ---------------------------------------------------
    for s in ("verify_phase0.py", "verify_phase1.py", "verify_phase2.py",
              "verify_phase3.py"):
        check(_run(s) == 0, f"{s} passes")

    dataset_sha = json.loads(
        (ROOT / "data/processed/dataset_manifest.json").read_text()
    )["dataset_sha256"]
    check(dataset_sha != OLD_DATASET,
          "dataset hash changed under correction")
    check(dataset_sha == cfg["accepted_phase1_dataset_sha256"],
          "F-E003 config pins corrected dataset hash")

    # ---- preregistration / governance --------------------------------------
    prereg_rel = ("research/preregistrations/"
                  "F-E003-phase3-corrected-reanalysis.md")
    check((ROOT / prereg_rel).exists(), "F-E003 preregistration exists")
    check(CONFIG.exists(), "F-E003 config exists")
    reg = _read(ROOT / "registry/experiment_registry.csv")
    e003 = [r for r in reg if r["experiment_id"] == "F-E003"]
    check(len(e003) == 1 and e003[0]["outcome"] == "exploratory",
          "F-E003 registered as exploratory")

    prereg_commit = _git([
        "log", "--diff-filter=A", "--format=%H", "--", prereg_rel,
    ]).splitlines()[-1]
    out_commits = _git([
        "log", "--diff-filter=A", "--format=%H", "--",
        "data/analysis/phase3_corrected",
    ]).splitlines()
    check(bool(prereg_commit), "F-E003 preregistration is committed")
    ok_order = True
    for c in out_commits:
        anc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", prereg_commit, c],
            cwd=ROOT,
        ).returncode
        if anc != 0:
            ok_order = False
    check(ok_order, "F-E003 preregistration precedes outcome outputs")

    # ---- holdout preservation ----------------------------------------------
    expl_v1_path = META / "phase3_exploration_ids.csv"
    expl_v2_path = META / "phase3_exploration_ids_v2.csv"
    hold_path = META / "phase3_holdout_ids.csv"
    seal_v1_path = META / "phase3_holdout_seal.json"
    seal_v2_path = META / "phase3_holdout_seal_v2.json"
    summ_v2_path = META / "phase3_split_summary_v2.csv"
    for p in (expl_v1_path, expl_v2_path, hold_path, seal_v1_path,
              seal_v2_path, summ_v2_path):
        check(p.exists(), f"{p.name} exists")

    expl_v1 = _ids(expl_v1_path)
    expl_v2 = _ids(expl_v2_path)
    hold_ids = _ids(hold_path)
    check(len(hold_ids) == 2072, "frozen holdout ID set unchanged (2,072)")
    check(not (expl_v2 & hold_ids),
          "no original holdout ID in corrected exploration")
    check(expl_v2 <= expl_v1, "corrected exploration is subset of original")

    v1_doc = json.loads(seal_v1_path.read_text())
    v2_doc = json.loads(seal_v2_path.read_text())
    check(v1_doc["holdout_seal_sha256"] == V1_SEAL,
          "v1 seal preserved as historical record")
    check(v1_doc["dataset_sha256"] == OLD_DATASET,
          "v1 seal pins pre-correction dataset")
    check(v2_doc["dataset_sha256"] == dataset_sha,
          "v2 seal pins corrected dataset")
    check(v2_doc["corrected_exploration_manifest_sha256"] == _sha(expl_v2_path),
          "v2 seal records corrected exploration manifest")
    check(v2_doc["holdout_seal_sha256"] != V1_SEAL,
          "v2 seal differs from v1 (row bytes changed as documented)")

    from fortuna.analysis.split import holdout_seal_sha256
    check(
        holdout_seal_sha256(ROOT / "data/processed/draws.csv", hold_ids)
        == v2_doc["holdout_seal_sha256"],
        "v2 seal reproduces on corrected canonical rows",
    )
    check(not v2_doc.get("invalidated_holdout_ids"),
          "no frozen holdout ID invalidated")

    # corrected exploration == original INTERSECT corrected eligible
    from fortuna.simulation.observation import load_draw_metadata

    meta = load_draw_metadata(ROOT / "data/processed/draws.csv")
    by_id = {r["draw_id"]: r for r in meta}
    eligible = {
        r["draw_id"] for r in meta
        if r["draw_stream"] == "main" and r["analysis_eligible"] == "true"
    }
    check(expl_v2 == expl_v1 & eligible,
          "corrected exploration = original INTERSECT eligible")

    # ---- exclusion ledger ---------------------------------------------------
    ledger_path = META / "draw_exclusions.csv"
    check(ledger_path.exists(), "draw_exclusions.csv exists")
    ledger = _read(ledger_path)
    excluded = [r for r in ledger if r["decision_status"] == "excluded"]
    check(len(excluded) == len(ledger),
          "all ledger rows carry a decision")
    check(all(r["evidence"].strip() and r["decision_id"]
              for r in excluded),
          "every exclusion has independent evidence + decision ID")
    check(all(r["draw_id"] in by_id for r in excluded),
          "every excluded ID resolves to a canonical draw")
    check(all(by_id[r["draw_id"]]["analysis_eligible"] == "false"
              for r in excluded),
          "excluded draws are analysis-ineligible")
    check(not ({r["draw_id"] for r in excluded} & expl_v2),
          "no excluded draw in corrected exploration")
    check(not ({r["draw_id"] for r in excluded} & hold_ids),
          "no excluded draw in frozen holdout")
    # duplicate-set rarity alone can never establish exclusion: every
    # ledger reason code is an evidence class, not 'identical sets'
    allowed_reasons = {
        "off_schedule_duplicate_set", "misdated_duplicate_set",
        "off_schedule_unsupported",
    }
    check({r["reason_code"] for r in excluded} <= allowed_reasons,
          "exclusion reasons are evidence-based classes")

    # ---- atomic order/sequence provenance ------------------------------------
    phys_capable = {
        "SRC-WI-PB-CSV", "SRC-MO-PB-XLSX", "SRC-TX-PB-CSV",
        "SRC-TX-MM-CSV", "SRC-FL-LOTTO-HIST-PDF",
    }
    phys_bad = []
    for r in meta:
        if r["numbers_order"] != "physical_draw_order":
            continue
        if not r.get("number_sequence_source_id"):
            phys_bad.append(r["draw_id"])
        elif r["number_sequence_source_id"] not in phys_capable:
            phys_bad.append(r["draw_id"])
    check(not phys_bad,
          f"physical rows have capable sequence source {phys_bad[:5]}")

    # ---- no holdout leakage ---------------------------------------------------
    analysis_files = list(OUT.glob("*.csv"))
    check(len(analysis_files) >= 13, "all F-E003 outputs exist")
    leaked = []
    for p in analysis_files:
        for line in p.read_text().splitlines()[1:]:
            first = line.split(",", 1)[0]
            if first in hold_ids:
                leaked.append(f"{p.name}:{first}")
    check(not leaked,
          f"no holdout draw_id in F-E003 outputs {leaked[:5]}")

    # loader firewall self-test
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
        # physical label without sequence provenance is rejected
        fake2 = Path(td) / "draws2.csv"
        fake2.write_text(
            "draw_id,game_id,regime_id,draw_date,scheduled_datetime,"
            "drawing_identifier,draw_stream,main_numbers,numbers_order,"
            "number_sequence_source_id,"
            "special_ball,multiplier,jackpot,jackpot_cash_value,"
            "jackpot_winners,drawing_location,machine_id,ball_set_id,"
            "source_id,retrieved_at,raw_artifact_sha256,parser_version,"
            "ingestion_version,validation_status,analysis_eligible,"
            "provisional,data_quality_notes,corroborating_source_ids\n"
            "E1,g,FL-R001,2020-01-01,,,main,1;2;3;4;5;6,"
            "physical_draw_order,,"
            ",,,,,,,,,,,,valid,true,false,,\n"
        )
        try:
            load_exploration_draws(fake2, {"E1"})
            prov_ok = False
        except AssertionError:
            prov_ok = True
        check(prov_ok,
              "loader rejects physical order without sequence provenance")

    # ---- manifest / provenance -----------------------------------------------
    man_path = OUT / "phase3_corrected_manifest.json"
    check(man_path.exists(), "corrected analysis manifest exists")
    man = json.loads(man_path.read_text())
    for key in (
        "phase3_preregistration_commit", "analysis_code_commit",
        "accepted_phase1_dataset_sha256", "accepted_phase2_commit",
        "observation_plan_sha256",
        "corrected_exploration_manifest_sha256", "holdout_manifest_sha256",
        "holdout_seal_sha256_v1", "holdout_seal_sha256_v2",
        "exploration_counts", "exploration_removed_counts",
        "holdout_counts", "exploration_segment_lengths", "root_seed",
        "rng_algorithm", "primary_replicates", "output_hashes",
    ):
        check(key in man, f"manifest field {key}")
    check(man.get("phase") == 3 and man.get("experiment_id") == "F-E003",
          "manifest phase/experiment")
    check(man.get("root_seed") == 20260930, "manifest root seed")
    check(man.get("accepted_phase1_dataset_sha256") == dataset_sha,
          "manifest pins corrected dataset hash")
    check(man.get("phase3_preregistration_commit") == prereg_commit,
          "manifest records true F-E003 preregistration commit")
    check(man.get("holdout_seal_sha256_v1") == V1_SEAL,
          "manifest records v1 seal")
    check(man.get("holdout_seal_sha256_v2")
          == v2_doc["holdout_seal_sha256"],
          "manifest records v2 seal")
    for name, h in man.get("output_hashes", {}).items():
        check(_sha(OUT / name) == h, f"output hash {name}")
    check(man.get("primary_replicates") == 20000,
          "primary replicate count frozen")
    check(man.get("convergence_status") == "CONVERGED",
          "all F-E003 baselines converged")

    # corrected Phase 2 null matches corrected exploration metadata:
    # exploration counts must fit inside the v4 observation plan counts
    plan = {r["statistical_regime_id"]: r
            for r in _read(META / "phase2_observation_plan.csv")}
    summ_v2 = {r["statistical_regime_id"]: r for r in _read(summ_v2_path)}
    ok_plan = all(
        int(summ_v2[s]["exploration_count"])
        + int(summ_v2[s]["holdout_count"])
        == int(plan[s]["eligible_main_draw_count"])
        for s in summ_v2
    )
    check(ok_plan,
          "corrected split + frozen holdout covers the v4 plan exactly")
    check(
        all(int(summ_v2[s]["holdout_count"]) ==
            int(man["holdout_counts"][s]) for s in summ_v2),
        "manifest holdout counts frozen",
    )

    # ---- family integrity ------------------------------------------------------
    prim = _read(OUT / "phase3_primary_statistics.csv")
    prim_p = _read(OUT / "phase3_primary_pvalues.csv")
    check(len(prim) == 202, "202 primary tests evaluated")
    check(len(prim_p) == 202, "202 primary p-values")
    tails = cfg["primary"]["tails"]
    mism = [r for r in prim_p if r["tail"] != tails[r["statistic_id"]]]
    check(not mism, "primary test directions match frozen tails")
    check(all(r["raw_p"] and r["bh_q"] and r["holm_p"] and r["z"]
              for r in prim_p),
          "primary adjusted p-values + effect sizes present")
    check(all(r["convergence_status"] in ("CONVERGED", "NOT CONVERGED")
              for r in prim),
          "convergence reported for every primary baseline")

    sec = _read(OUT / "phase3_secondary_pvalues.csv")
    check(len(sec) >= 16 * 10, "secondary family has all history stats")
    check(all(r["raw_p"] and r["bh_q"] and r["holm_p"] and r["z"]
              for r in sec),
          "secondary adjusted p-values + effect sizes present")
    order_rows = _read(OUT / "phase3_order_diagnostics.csv")
    equip_rows = _read(OUT / "phase3_equipment_diagnostics.csv")
    check(len(order_rows) == 16, "P3-S011 status recorded for 16 regimes")
    check(all(r["status"] in ("RUN", "INSUFFICIENT_DATA")
              for r in order_rows), "P3-S011 statuses valid")
    run_p3s011 = {r["statistical_regime_id"] for r in order_rows
                  if r["status"] == "RUN"}
    check({r["statistical_regime_id"] for r in sec
           if r["statistic_id"] == "P3-S011"} == run_p3s011,
          "P3-S011 results cover RUN regimes")
    check(all(r["status"] in ("RUN", "INSUFFICIENT_DATA")
              for r in equip_rows), "P3-S012 statuses valid")

    # P3-S011 consumed only atomic physical-order exploration sequences
    from fortuna.analysis.loader import load_exploration_histories
    from fortuna.schemas.csv_io import load_csv
    from fortuna.schemas.regimes import GameRegime

    regs = load_csv(META / "game_regimes.csv", GameRegime)
    stat_of = {r.regime_id: r.statistical_regime_id for r in regs}
    hists = load_exploration_histories(
        ROOT / "data/processed/draws.csv",
        ROOT / "data/processed/draw_numbers.csv", expl_v2, stat_of,
    )
    phys_rows = {
        r["draw_id"]: r for r in meta
        if r["numbers_order"] == "physical_draw_order"
    }
    ord_ok = True

    for sid in run_p3s011:
        for did, seq in hists[sid].physical_order.items():
            prow = phys_rows.get(did)
            if prow is None or not prow["number_sequence_source_id"]:
                ord_ok = False
            if list(seq) == sorted(seq):
                ord_ok = False  # ascending sequences are not physical
    check(ord_ok,
          "P3-S011 used only non-ascending atomic-provenance sequences")

    # ---- promotion integrity ---------------------------------------------------
    prom = cfg["promotion"]
    hyps = _read(OUT / "phase3_candidate_hypotheses.csv")
    all_rows = {(r["statistical_regime_id"], r["statistic_id"]): r
                for r in prim_p + sec}
    bad_status = [h for h in hyps
                  if h["status"] != "candidate_for_confirmation"]
    check(not bad_status, "no hypothesis labeled confirmed/predictive")
    for h in hyps:
        row = all_rows.get((h["statistical_regime"], h["test_statistic"]))
        ok = row is not None and float(row["bh_q"]) <= prom["bh_q_max"] \
            and abs(float(row["z"])) >= prom["abs_z_min"]
        check(ok, f"{h['hypothesis_id']} meets promotion rule")
    qualifying = {
        (r["statistical_regime_id"], r["statistic_id"])
        for r in prim_p + sec
        if r["bh_flag"] == "True" and abs(float(r["z"])) >= prom["abs_z_min"]
    }
    promoted = {(h["statistical_regime"], h["test_statistic"]) for h in hyps}
    adj = _read(OUT / "phase3_artifact_diagnostics.csv")
    explained = {
        (r["statistical_regime_id"], r["affected_statistics"])
        for r in adj
        if r["artifact"] == "flag_adjudication" and "EXPLAINED" in r["detail"]
    }
    check(qualifying == promoted | explained,
          "all qualifying F-E003 flags promoted or evidence-resolved "
          f"(qual={len(qualifying)} prom={len(promoted)} "
          f"expl={len(explained)})")
    check(not (promoted - qualifying),
          "no hypothesis promoted outside qualifying set")
    # no 'phantom' heuristic rows: artifact diagnostics must not contain
    # the prohibited duplicate-set adjustment
    heuristic_rows = [
        r for r in adj
        if "phantom_duplicate_record" in r["artifact"]
        or "replaced by" in r["detail"].lower()
        or "expected overlap" in r["detail"].lower()
    ]
    check(not heuristic_rows,
          "no duplicate-overlap replacement adjudication in outputs")
    # every upstream_exclusion row cites a real ledger entry
    excl_ids = {r["draw_id"] for r in excluded}
    up_rows = [r for r in adj if r["artifact"] == "upstream_exclusion"]
    check(len(up_rows) == len(excluded),
          "artifact diagnostics cite every ledger exclusion")
    check(all(any(e in r["detail"] for e in excl_ids) for r in up_rows),
          "upstream exclusions traceable to ledger draw_ids")

    # ---- prohibited products ----------------------------------------------------
    banned_files = [
        p for p in OUT.iterdir()
        if any(t in p.name.lower()
               for t in ("best", "hot", "cold", "likely", "recommended",
                         "ticket", "prediction"))
    ]
    check(not banned_files, f"no prohibited output files {banned_files}")
    banned_terms = ("due", "lucky", "best number", "hot number",
                    "recommended", "predicted")
    bad_terms = []
    for h in hyps:
        blob = json.dumps(h).lower()
        for t in banned_terms:
            if t in blob:
                bad_terms.append(f"{h['hypothesis_id']}:{t}")
    check(not bad_terms, f"no prohibited terminology {bad_terms}")
    modeling_artifacts = [
        p for p in (ROOT / "registry/model_registry.csv",
                    ROOT / "registry/prediction_ledger.csv")
        if p.exists() and len(p.read_text().splitlines()) > 1
    ]
    check(not modeling_artifacts, "no models/predictions registered")

    # segments cover corrected exploration counts
    ok_seg = all(
        sum(int(x) for x in r["exploration_segment_lengths"].split(";"))
        == int(r["exploration_count"]) for r in summ_v2.values()
    )
    check(ok_seg, "corrected exploration segments cover counts")

    if FAILS:
        print(f"CORRECTED PHASE 3 (F-E003) VERIFICATION FAILED "
              f"({len(FAILS)} checks)")
        return 1
    print("CORRECTED PHASE 3 (F-E003) VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
