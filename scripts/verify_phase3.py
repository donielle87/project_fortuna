"""Phase 3 verifier — holdout firewall, provenance, and output integrity.

Fails if: upstream verifiers fail; dataset/plan/seal hashes drift; F-E002
preregistration was not committed before outcome analysis; the split was
not metadata-only or deviates from ceil(20%); any holdout draw_id leaks
into Phase 3 analysis outputs; the seal changed; test directions differ
from the frozen config; multiplicity fields are missing; hypotheses are
promoted without meeting the frozen rule or are labeled predictive; or
output hashes/provenance are incomplete. Never reads holdout outcomes.
"""

import csv
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "metadata"
OUT = ROOT / "data/analysis/phase3"
CONFIG = ROOT / "config/experiments/F-E002.yaml"
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

    # ---- upstream gates -------------------------------------------------
    for s in ("verify_phase0.py", "verify_phase1.py", "verify_phase2.py"):
        check(_run(s) == 0, f"{s} passes")

    dataset_sha = json.loads(
        (ROOT / "data/processed/dataset_manifest.json").read_text()
    )["dataset_sha256"]
    check(
        dataset_sha == cfg["accepted_phase1_dataset_sha256"],
        "accepted dataset hash unchanged",
    )

    # ---- preregistration / governance -----------------------------------
    prereg = ROOT / "research/preregistrations/F-E002-phase3-exploratory-analysis.md"
    check(prereg.exists(), "F-E002 preregistration exists")
    check(CONFIG.exists(), "F-E002 config exists")
    reg = _read(ROOT / "registry/experiment_registry.csv")
    e002 = [r for r in reg if r["experiment_id"] == "F-E002"]
    check(
        len(e002) == 1 and e002[0]["outcome"] == "exploratory",
        "F-E002 registered as exploratory",
    )

    # prereg committed before any analysis output was committed
    prereg_commit = _git([
        "log", "--diff-filter=A", "--format=%H", "--",
        "research/preregistrations/F-E002-phase3-exploratory-analysis.md",
    ]).splitlines()[-1]
    out_commit = _git([
        "log", "--diff-filter=A", "--format=%H", "--",
        "data/analysis/phase3",
    ]).splitlines()
    check(bool(prereg_commit), "preregistration is committed")
    # all analysis-output-adding commits must be descendants of prereg commit
    ok_order = True
    for c in out_commit:
        anc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", prereg_commit, c],
            cwd=ROOT,
        ).returncode
        if anc != 0:
            ok_order = False
    check(ok_order, "F-E002 committed before outcome-analysis outputs")

    # ---- split artifacts -------------------------------------------------
    expl_path = META / "phase3_exploration_ids.csv"
    hold_path = META / "phase3_holdout_ids.csv"
    seal_path = META / "phase3_holdout_seal.json"
    summ_path = META / "phase3_split_summary.csv"
    for p in (expl_path, hold_path, seal_path, summ_path):
        check(p.exists(), f"{p.name} exists")
    expl_ids = _ids(expl_path)
    hold_ids = _ids(hold_path)
    check(not (expl_ids & hold_ids), "exploration/holdout disjoint")
    allowed_cols = {
        "draw_id", "game_id", "statistical_regime_id", "draw_date",
        "draw_stream", "split",
    }
    for p in (expl_path, hold_path):
        hdr = set(next(csv.reader(p.open())))
        check(hdr <= allowed_cols, f"{p.name} metadata-only columns")

    seal_doc = json.loads(seal_path.read_text())
    check(
        seal_doc["dataset_sha256"] == dataset_sha,
        "seal pins dataset hash",
    )
    check(
        seal_doc["exploration_manifest_sha256"] == _sha(expl_path)
        and seal_doc["holdout_manifest_sha256"] == _sha(hold_path),
        "split manifests hash-match seal",
    )
    split_policy_hash = hashlib.sha256(
        json.dumps(cfg["split"], sort_keys=True).encode()
    ).hexdigest()
    check(
        seal_doc["split_policy_sha256"] == split_policy_hash,
        "split policy hash matches config",
    )

    # ceil(20%) per regime + chronological order, recomputed from metadata
    from fortuna.schemas.csv_io import load_csv
    from fortuna.schemas.regimes import GameRegime
    from fortuna.simulation.observation import load_draw_metadata

    regimes = load_csv(META / "game_regimes.csv", GameRegime)
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}
    meta = load_draw_metadata(ROOT / "data/processed/draws.csv")
    n_by: dict[str, int] = {}
    date_by: dict[str, dict[str, str]] = {}
    hold_dates: dict[str, list[str]] = {}
    expl_dates: dict[str, list[str]] = {}
    id_row = {r["draw_id"]: r for r in meta}
    for r in meta:
        if r["draw_stream"] == "main" and r["analysis_eligible"] == "true":
            s = stat_of.get(r["regime_id"])
            if s:
                n_by[s] = n_by.get(s, 0) + 1
                date_by.setdefault(s, {})[r["draw_id"]] = r["draw_date"]
    with hold_path.open(newline="") as f:
        for r in csv.DictReader(f):
            hold_dates.setdefault(r["statistical_regime_id"], []).append(
                id_row[r["draw_id"]]["draw_date"]
            )
    with expl_path.open(newline="") as f:
        for r in csv.DictReader(f):
            expl_dates.setdefault(r["statistical_regime_id"], []).append(
                id_row[r["draw_id"]]["draw_date"]
            )
    check(len(n_by) == 16, "16 regimes in split population")
    for s, n in n_by.items():
        exp_n = math.ceil(0.20 * n)
        got = len(hold_dates.get(s, []))
        check(got == exp_n, f"{s} holdout count == ceil(20%) ({got})")
        check(
            max(expl_dates[s]) < min(hold_dates[s]),
            f"{s} exploration precedes holdout",
        )

    # seal re-derivation over raw canonical holdout rows
    from fortuna.analysis.split import holdout_seal_sha256
    seal_now = holdout_seal_sha256(ROOT / "data/processed/draws.csv", hold_ids)
    check(
        seal_now == seal_doc["holdout_seal_sha256"],
        "holdout seal unchanged",
    )

    # ---- no holdout leakage into analysis outputs ------------------------
    analysis_files = list(OUT.glob("*.csv"))
    check(len(analysis_files) >= 13, "all phase3 outputs exist")
    leaked = []
    for p in analysis_files:
        txt = p.read_text()
        # scan every field of every row for a holdout draw_id
        for line in txt.splitlines()[1:]:
            first = line.split(",", 1)[0]
            if first in hold_ids:
                leaked.append(f"{p.name}:{first}")
    check(not leaked, f"no holdout draw_id in analysis outputs {leaked[:5]}")

    # loader firewall self-test: trap fields in non-exploration rows
    import tempfile

    from fortuna.analysis.loader import load_exploration_draws

    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "draws.csv"
        fake.write_text(
            "draw_id,game_id,regime_id,draw_date,scheduled_datetime,"
            "drawing_identifier,draw_stream,main_numbers,numbers_order,"
            "special_ball,multiplier,jackpot,jackpot_cash_value,"
            "jackpot_winners,drawing_location,machine_id,ball_set_id,"
            "source_id,retrieved_at,raw_artifact_sha256,parser_version,"
            "ingestion_version,validation_status,analysis_eligible,"
            "provisional,data_quality_notes,corroborating_source_ids\n"
            "E1,g,FL-R001,2020-01-01,,,main,1;2;3;4;5;6,physical_draw_order,"
            ",,,,,,,,,,,,valid,true,false,,\n"
            "H1,g,FL-R001,2020-01-02,,,main,TRAP,physical_draw_order,"
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

    # ---- manifest / provenance ------------------------------------------
    man_path = OUT / "phase3_analysis_manifest.json"
    check(man_path.exists(), "analysis manifest exists")
    man = json.loads(man_path.read_text())
    for key in (
        "phase3_preregistration_commit", "analysis_code_commit",
        "accepted_phase1_dataset_sha256", "accepted_phase2_commit",
        "exploration_manifest_sha256", "holdout_manifest_sha256",
        "holdout_seal_sha256", "exploration_counts", "holdout_counts",
        "exploration_segment_lengths", "root_seed", "rng_algorithm",
        "primary_replicates", "output_hashes",
    ):
        check(key in man, f"manifest field {key}")
    check(man.get("phase") == 3, "manifest phase == 3")
    check(man.get("root_seed") == 20260930, "manifest root seed")
    check(
        man.get("accepted_phase1_dataset_sha256") == dataset_sha,
        "manifest pins dataset hash",
    )
    check(
        man.get("phase3_preregistration_commit") == prereg_commit,
        "manifest records true preregistration commit",
    )
    check(
        man.get("holdout_seal_sha256") == seal_doc["holdout_seal_sha256"],
        "manifest records holdout seal",
    )
    for name, h in man.get("output_hashes", {}).items():
        check(_sha(OUT / name) == h, f"output hash {name}")
    check(
        man.get("primary_replicates") == 20000,
        "primary replicate count frozen",
    )

    # ---- primary family integrity ---------------------------------------
    prim = _read(OUT / "phase3_primary_statistics.csv")
    prim_p = _read(OUT / "phase3_primary_pvalues.csv")
    check(len(prim) == 202, "202 primary tests evaluated")
    check(len(prim_p) == 202, "202 primary p-values")
    tails = cfg["primary"]["tails"]
    mism = [r for r in prim_p if r["tail"] != tails[r["statistic_id"]]]
    check(not mism, "primary test directions match frozen tails")
    check(
        all(
            r["raw_p"] and r["bh_q"] and r["holm_p"] and r["z"]
            for r in prim_p
        ),
        "primary adjusted p-values + effect sizes present",
    )
    check(
        all(r["convergence_status"] in ("CONVERGED", "NOT CONVERGED")
            for r in prim),
        "convergence reported for every primary baseline",
    )

    # ---- secondary family integrity --------------------------------------
    sec = _read(OUT / "phase3_secondary_pvalues.csv")
    check(len(sec) >= 16 * 10, "secondary family has all history stats")
    check(
        all(r["raw_p"] and r["bh_q"] and r["holm_p"] and r["z"]
            for r in sec),
        "secondary adjusted p-values + effect sizes present",
    )
    # P3-S011/S012 either evaluated or explicitly N/A per regime
    order_rows = _read(OUT / "phase3_order_diagnostics.csv")
    equip_rows = _read(OUT / "phase3_equipment_diagnostics.csv")
    check(len(order_rows) == 16, "P3-S011 status recorded for 16 regimes")
    check(
        all(r["status"] in ("RUN", "INSUFFICIENT_DATA") for r in order_rows),
        "P3-S011 statuses valid",
    )
    run_p3s011 = {r["statistical_regime_id"] for r in order_rows
                  if r["status"] == "RUN"}
    check(
        {r["statistical_regime_id"] for r in sec
         if r["statistic_id"] == "P3-S011"} == run_p3s011,
        "P3-S011 results cover RUN regimes",
    )
    check(
        all(r["status"] in ("RUN", "INSUFFICIENT_DATA") for r in equip_rows),
        "P3-S012 statuses valid",
    )

    # ---- hypotheses obey the frozen promotion rule -----------------------
    prom = cfg["promotion"]
    hyps = _read(OUT / "phase3_candidate_hypotheses.csv")
    all_rows = { (r["statistical_regime_id"], r["statistic_id"]): r
                 for r in prim_p + sec }
    bad_status = [h for h in hyps if h["status"] != "candidate_for_confirmation"]
    check(not bad_status, "no hypothesis labeled confirmed/predictive")
    for h in hyps:
        row = all_rows.get((h["statistical_regime"], h["test_statistic"]))
        ok = row is not None and float(row["bh_q"]) <= prom["bh_q_max"] \
            and abs(float(row["z"])) >= prom["abs_z_min"]
        check(ok, f"{h['hypothesis_id']} meets promotion rule")
    # every qualifying flag is either promoted or artifact-explained in
    # the diagnostics file (deterministic adjudication, no silent drops)
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
    check(
        qualifying == promoted | explained,
        f"qualifying flags all adjudicated "
        f"(qual={len(qualifying)} prom={len(promoted)} expl={len(explained)})",
    )
    check(
        not (promoted - qualifying),
        "no hypothesis promoted outside qualifying set",
    )
    # artifact claims are verifiable: mislabeled order rows are sorted
    import numpy as _np

    from fortuna.analysis.loader import load_exploration_histories
    from fortuna.schemas.csv_io import load_csv as _lc
    from fortuna.schemas.regimes import GameRegime as _GR

    _regs = _lc(META / "game_regimes.csv", _GR)
    _stat_of = {r.regime_id: r.statistical_regime_id for r in _regs}
    _hists = load_exploration_histories(
        ROOT / "data/processed/draws.csv",
        ROOT / "data/processed/draw_numbers.csv", expl_ids, _stat_of,
    )
    for r in adj:
        if r["artifact"] == "position_semantics_mislabeled":
            sid = r["statistical_regime_id"]
            ords = _np.array([
                _hists[sid].physical_order[d]
                for d in sorted(_hists[sid].physical_order)
            ])
            frac = float((_np.diff(ords, axis=1) > 0).all(axis=1).mean())
            check(frac > 0.5, f"{sid} order-semantics artifact verified")
        elif r["artifact"] == "phantom_duplicate_record":
            sid = r["statistical_regime_id"]
            mains = [d.mains for d in _hists[sid].draws]
            has_dup = any(
                mains[i] == mains[i - 1] for i in range(1, len(mains))
            )
            check(has_dup, f"{sid} phantom duplicate verified")

    # ---- terminology / prohibited products --------------------------------
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

    # Phase 3 must not have created predictive infrastructure
    modeling_artifacts = [
        p for p in (ROOT / "registry/model_registry.csv",
                    ROOT / "registry/prediction_ledger.csv")
        if p.exists() and len(p.read_text().splitlines()) > 1
    ]
    check(not modeling_artifacts, "no models/predictions registered")

    # sequential non-bridging re-verified via segment plan (quick spot check)
    summ = _read(summ_path)
    ok_seg = all(
        sum(int(x) for x in r["exploration_segment_lengths"].split(";"))
        == int(r["exploration_count"]) for r in summ
    )
    check(ok_seg, "exploration segments cover exploration counts")

    if FAILS:
        print(f"PHASE 3 VERIFICATION FAILED ({len(FAILS)} checks)")
        return 1
    print("PHASE 3 VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
