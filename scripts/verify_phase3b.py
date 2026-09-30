"""Verify F-E004 — Phase 3B positional dependence exploration.

Fails if ANY check fails. Covers the Task 21 checklist: upstream
verifiers green, F-E004 preregistered before analysis, dataset/seal
pins, holdout isolation, provenance-safe physical-order eligibility,
n>=100 gate, sequential-not-independent null usage, required outputs,
multiplicity, promotion rule, honest convergence, sensitivity output,
manifest hashes, and no predictive artifacts.
"""

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/analysis/phase3b"
META = ROOT / "metadata"
CONFIG = ROOT / "config/experiments/F-E004.yaml"
PREREG = "research/preregistrations/F-E004-positional-dependence.md"
DATASET_SHA = (
    "200174427b4abcc6bcc0aa3761174db237ae52e266e88cfc88bae39f27c138ff"
)
V1_SEAL = "6cb7c382924c4ad55ab0958239cb488cd95b0e0b99407ebebcfe822a4b16b91c"
V2_SEAL = "6dc9a023b4bfd7b7fcfa321ebde9455687222eb0ef316a458d0d01effe18f2e0"

PASS_COUNT = 0
FAILURES: list[str] = []


def check(cond: bool, name: str, detail: str = "") -> None:
    global PASS_COUNT
    if cond:
        PASS_COUNT += 1
        print(f"  PASS {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILURES.append(name)
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))


def _run(script: str) -> bool:
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        capture_output=True, text=True, cwd=ROOT,
    )
    return r.returncode == 0


def _csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True,
    ).stdout.strip()


def main() -> int:
    print("=" * 72)
    print("PHASE 3B (F-E004) VERIFICATION")
    print("=" * 72)

    # ---------- upstream gates ---------------------------------------
    print("\n[1] Upstream verifiers")
    for s in ("verify_phase0.py", "verify_phase1.py", "verify_phase2.py",
              "verify_phase3.py", "verify_phase3_corrected.py"):
        check(_run(s), f"upstream {s}")

    # ---------- preregistration --------------------------------------
    print("\n[2] F-E004 preregistration")
    prereg_path = ROOT / PREREG
    check(prereg_path.exists(), "preregistration file exists")
    cfg = yaml.safe_load(CONFIG.read_text())
    check(cfg["experiment_id"] == "F-E004", "config experiment_id")
    check(
        cfg["accepted_phase1_dataset_sha256"].strip() == DATASET_SHA,
        "config pins corrected dataset",
    )
    commits = _git(["log", "--format=%H", "--", PREREG]).splitlines()
    check(bool(commits), "preregistration committed")
    prereg_commit = commits[0] if commits else ""
    out_files = sorted(OUT.glob("*")) if OUT.exists() else []
    if out_files and prereg_commit:
        out_commits = _git(
            ["log", "--format=%H", "--reverse", "--",
             "data/analysis/phase3b/"]
        ).splitlines()
        # earliest output commit must be a descendant of the prereg
        # commit; if outputs are not yet committed, the prereg must at
        # least be an ancestor of HEAD.
        target = out_commits[0] if out_commits and out_commits[0] else "HEAD"
        r = subprocess.run(
            ["git", "merge-base", "--is-ancestor", prereg_commit, target],
            cwd=ROOT, capture_output=True,
        )
        check(r.returncode == 0, "preregistration predates output commit")
    manifest = json.loads((OUT / "phase3b_manifest.json").read_text())
    check(
        manifest.get("phase3b_preregistration_commit") == prereg_commit,
        "manifest records preregistration commit",
    )

    # ---------- dataset / holdout pins --------------------------------
    print("\n[3] Dataset and holdout pins")
    check(
        manifest["accepted_phase1_dataset_sha256"] == DATASET_SHA,
        "manifest pins corrected dataset",
    )
    check(
        manifest["phase2_v4_observation_plan_sha256"]
        == "8309e1dd673e339b66b1fae09d02a0f2b205a62ada2882c1590645d1bf2ac10a",
        "manifest pins v2 observation plan",
    )
    hold_ids = set()
    with (META / "phase3_holdout_ids.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            hold_ids.add(r["draw_id"])
    check(len(hold_ids) == 2072, "frozen holdout is 2,072 IDs")
    check(
        manifest["holdout_seal_v2_sha256"] == V2_SEAL,
        "manifest records v2 holdout seal",
    )
    v1 = json.loads((META / "phase3_holdout_seal.json").read_text())
    check(
        v1["holdout_seal_sha256"] == V1_SEAL,
        "v1 seal preserved unchanged",
    )

    # ---------- holdout isolation in outputs --------------------------
    print("\n[4] Holdout isolation")
    leaked = []
    for p in OUT.glob("*.csv"):
        first_col = p.read_text().splitlines()
        for line in first_col[1:]:
            did = line.split(",", 1)[0]
            if did in hold_ids:
                leaked.append((p.name, did))
    # draw_id appears only as window_start_draw_id in temporal diagnostics
    temporal = _csv(OUT / "phase3b_temporal_diagnostics.csv")
    leaked += [
        ("phase3b_temporal_diagnostics.csv", r["window_start_draw_id"])
        for r in temporal if r["window_start_draw_id"] in hold_ids
    ]
    check(not leaked, "no holdout draw_id in any output", str(leaked[:3]))

    # ---------- eligibility integrity ---------------------------------
    print("\n[5] Physical-order eligibility")
    meta = {}
    with (ROOT / "data/processed/draws.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            meta[r["draw_id"]] = {
                "numbers_order": r["numbers_order"],
                "seq_src": r.get("number_sequence_source_id", ""),
                "analysis_eligible": r["analysis_eligible"],
                "draw_stream": r["draw_stream"],
            }
    bad = [
        did for did in
        {r["window_start_draw_id"] for r in temporal}
        if meta.get(did, {}).get("numbers_order") != "physical_draw_order"
        or not meta.get(did, {}).get("seq_src")
        or meta.get(did, {}).get("analysis_eligible") != "true"
        or meta.get(did, {}).get("draw_stream") != "main"
    ]
    check(not bad, "temporal rows are physical-order eligible draws",
          str(bad[:3]))
    # loader-level: exploration ids file is the v2 corrected set
    expl_ids = set()
    with (META / "phase3_exploration_ids_v2.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            expl_ids.add(r["draw_id"])
    check(
        all(r["window_start_draw_id"] in expl_ids for r in temporal),
        "all analysed draws are in corrected exploration set",
    )
    check(
        not (expl_ids & hold_ids), "exploration/holdout disjoint",
    )

    # ---------- n>=100 gate --------------------------------------------
    print("\n[6] Minimum sample size")
    suff = {r["statistical_regime_id"]: r
            for r in _csv(OUT / "phase3b_regime_sufficiency.csv")}
    check(len(suff) == 16, "sufficiency covers all 16 regimes")
    prim = _csv(OUT / "phase3b_primary_pvalues.csv")
    sec = _csv(OUT / "phase3b_secondary_pvalues.csv")
    tested = {r["statistical_regime_id"] for r in prim + sec}
    small = [
        sid for sid in tested
        if int(suff[sid]["physical_order_draws"]) < 100
    ]
    check(not small, "no inferential test below n=100", str(small))
    check(
        all(
            (int(r["physical_order_draws"]) >= 100)
            == (r["status"] == "RUN") for r in suff.values()
        ),
        "sufficiency status consistent with gate",
    )
    nonqual = [
        sid for sid, r in suff.items()
        if r["status"] == "INSUFFICIENT_DATA"
    ]
    print(f"       qualifying regimes: {sorted(tested)}; "
          f"insufficient: {sorted(nonqual)}")

    # ---------- sequential (not independent) null ---------------------
    print("\n[7] Sequential null discipline")
    src = (ROOT / "src/fortuna/analysis/montecarlo_p3b.py").read_text()
    check("draw_mains_ordered" in src, "null uses ordered WOR engine")
    check(
        "draw_mains(" not in src.replace("draw_mains_ordered", ""),
        "no sorted-set null substituted",
    )
    check(
        manifest["monte_carlo"]["replicates_per_batch"] == 5000
        and manifest["monte_carlo"]["batches"] == 4,
        "20,000 replicates in 4 batches",
    )
    check(
        manifest["root_seed"] == 20260930
        and manifest["rng"] == "PCG64DXSM",
        "pinned RNG",
    )
    expl_mismatch = {
        sid: n for sid, n in manifest["physical_order_draw_counts"].items()
        if n != int(suff[sid]["physical_order_draws"])
    }
    check(not expl_mismatch, "manifest counts match sufficiency table")

    # ---------- outputs exist -----------------------------------------
    print("\n[8] Required outputs")
    required = [
        "phase3b_regime_sufficiency.csv",
        "phase3b_physical_segments.csv",
        "phase3b_position_counts.csv",
        "phase3b_position_residuals.csv",
        "phase3b_ordered_pair_diagnostics.csv",
        "phase3b_serial_diagnostics.csv",
        "phase3b_temporal_diagnostics.csv",
        "phase3b_equipment_diagnostics.csv",
        "phase3b_primary_pvalues.csv",
        "phase3b_secondary_pvalues.csv",
        "phase3b_sensitivity.csv",
        "phase3b_candidate_hypotheses.csv",
        "phase3b_manifest.json",
    ]
    for name in required:
        check((OUT / name).exists(), f"output {name}")

    # ---------- coverage of statistic catalog --------------------------
    print("\n[9] Statistic catalog coverage")
    prim_ids = {r["statistic_id"] for r in prim}
    expect_prim = {"P3B-S001", "P3B-S002", "P3B-S003", "P3B-S004",
                   "P3B-S006", "P3B-S007", "P3B-S008"}
    check(prim_ids == expect_prim, "primary catalog", str(prim_ids))
    sec_ids = {r["statistic_id"].split("|")[0] for r in sec}
    check(
        {"P3B-S005", "P3B-S009"} <= sec_ids, "secondary catalog",
        str(sec_ids),
    )

    # ---------- multiplicity + promotion --------------------------------
    print("\n[10] Multiplicity and promotion")
    for name, rows in (("primary", prim), ("secondary", sec)):
        need = {"raw_p", "bh_q", "holm_p", "z", "convergence_status",
                "mc_resolution"}
        check(
            all(need <= set(r) for r in rows),
            f"{name} rows carry p/multiplicity fields",
        )
        check(
            all(r["tail"] == "upper" for r in rows),
            f"{name} tails all upper",
        )
    cands = _csv(OUT / "phase3b_candidate_hypotheses.csv")
    bad_promo = []
    flagged = [r for r in prim + sec if r["bh_flag"] == "True"]
    promoted = {(r["statistical_regime_id"], r["statistic_id"])
                for r in cands}
    for r in flagged:
        key = (r["statistical_regime_id"], r["statistic_id"])
        qualifies = abs(float(r["z"])) >= 2.5 and (
            r["convergence_status"] in ("CONVERGED", "PERMUTATION")
        )
        if qualifies and key not in promoted:
            bad_promo.append(key)
        if key in promoted and not qualifies:
            bad_promo.append(("illegal", key))
    check(
        not bad_promo,
        "promotion rule: BH q<=0.10 AND |z|>=2.5 AND converged",
        str(bad_promo[:5]),
    )
    check(
        all(
            r["status"] == "candidate_for_confirmation" for r in cands
        ),
        "candidates labeled candidate_for_confirmation only",
    )
    nc_promoted = [
        r for r in prim + sec
        if r["bh_flag"] == "True" and abs(float(r["z"])) >= 2.5
        and r["convergence_status"] not in ("CONVERGED", "PERMUTATION")
        and (r["statistical_regime_id"], r["statistic_id"]) in promoted
    ]
    check(not nc_promoted, "no NOT CONVERGED promotion")

    # ---------- sensitivity -------------------------------------------
    print("\n[11] Sensitivity study")
    sens = _csv(OUT / "phase3b_sensitivity.csv")
    check(len(sens) > 0, "sensitivity rows exist")
    check(
        {"scenario", "statistic_id", "injected_effect_size", "power",
         "critical_value", "n_draws"} <= set(sens[0]),
        "sensitivity schema",
    )
    scenarios = {r["scenario"] for r in sens}
    check(
        {"position1_bias", "conditional_bias", "serial_same_pos",
         "serial_cross_pos", "temporal_position"} <= scenarios,
        "all scenarios present", str(scenarios),
    )

    # ---------- manifest hashes ----------------------------------------
    print("\n[12] Manifest integrity")
    oh = manifest.get("output_hashes", {})
    bad_hash = []
    for name, want in oh.items():
        p = OUT / name
        if not p.exists():
            bad_hash.append((name, "missing"))
            continue
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != want:
            bad_hash.append((name, "hash mismatch"))
    check(not bad_hash, "all output hashes verify", str(bad_hash[:3]))
    check(
        manifest.get("min_physical_order_draws") == 100,
        "manifest records min n=100",
    )
    check(
        manifest["families"]["primary"] == list(cfg["primary"][
            "family_statistics"]),
        "family definitions match config",
    )

    # ---------- prohibited artifacts ------------------------------------
    print("\n[13] No predictive artifacts")
    banned = []
    for p in OUT.iterdir():
        if p.is_file() and any(
            k in p.name.lower() for k in
            ("prediction", "ticket", "ranking", "candidate_pool",
             "hot_numbers", "best_numbers", "best", "hot", "cold",
             "likely", "recommended")
        ):
            banned.append(p.name)
    check(not banned, "no predictive output files", str(banned[:5]))
    modeling_artifacts = [
        p for p in (ROOT / "registry/model_registry.csv",
                    ROOT / "registry/prediction_ledger.csv")
        if p.exists() and len(p.read_text().splitlines()) > 1
    ]
    check(not modeling_artifacts, "no models/predictions registered")
    if cands:
        txt = (OUT / "phase3b_candidate_hypotheses.csv").read_text()
        check(
            "predictive" not in txt.lower()
            and "confirmed" not in txt.lower().replace(
                "candidate_for_confirmation", ""
            ),
            "no predictive/confirmed language in hypotheses",
        )

    print("\n" + "=" * 72)
    print(f"{PASS_COUNT} checks passed, {len(FAILURES)} failed")
    if FAILURES:
        for f_ in FAILURES:
            print(f"  FAILED: {f_}")
        print("PHASE 3B (F-E004) VERIFICATION FAILED")
        return 1
    print("PHASE 3B (F-E004) VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
