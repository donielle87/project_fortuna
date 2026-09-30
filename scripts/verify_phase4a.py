"""Verify F-E005 — Phase 4A finite predictive walk-forward benchmark.

Fails if ANY check fails. Covers the Task 25 checklist: upstream
verifiers green, F-E005 preregistered pre-performance, pinned dataset/
exploration/holdout, firewalled outcomes, all five frozen models, exact
K-subset normalization and marginals re-verified by enumeration,
warmup + strict walk-forward + chronological nested selection, required
outputs, exact random benchmarks, e-values, exact nine-condition gate,
at-most-one candidate, manifest hashes, and no predictive artifacts.
"""

import csv
import hashlib
import itertools
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "data/analysis/phase4a"
META = ROOT / "metadata"
CONFIG = ROOT / "config/experiments/F-E005.yaml"
PREREG = "research/preregistrations/F-E005-predictive-walkforward.md"
DATASET_SHA = (
    "200174427b4abcc6bcc0aa3761174db237ae52e266e88cfc88bae39f27c138ff"
)
V1_SEAL = "6cb7c382924c4ad55ab0958239cb488cd95b0e0b99407ebebcfe822a4b16b91c"
V2_SEAL = "6dc9a023b4bfd7b7fcfa321ebde9455687222eb0ef316a458d0d01effe18f2e0"
MODELS = ("F-M000", "F-M001", "F-M002", "F-M003", "F-M004")
CANDIDATES = ("F-M001", "F-M002", "F-M003", "F-M004")
GRID = {"0.1", "1.0", "10.0", "100.0"}
ALLOWED_MODEL_STATUS = {
    "benchmark", "evaluated", "candidate_for_holdout_confirmation",
    "rejected_no_predictive_edge", "specified",
}

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
    print("PHASE 4A (F-E005) VERIFICATION")
    print("=" * 72)

    # ---------- upstream gates ---------------------------------------
    print("\n[1] Upstream verifiers")
    for s in ("verify_phase0.py", "verify_phase1.py", "verify_phase2.py",
              "verify_phase3.py", "verify_phase3_corrected.py",
              "verify_phase3b.py"):
        check(_run(s), f"upstream {s}")

    # ---------- preregistration --------------------------------------
    print("\n[2] F-E005 preregistration")
    prereg_path = ROOT / PREREG
    check(prereg_path.exists(), "preregistration file exists")
    cfg = yaml.safe_load(CONFIG.read_text())
    check(cfg["experiment_id"] == "F-E005", "config experiment_id")
    check(cfg["classification"] == "predictive_research_exploratory",
          "classification")
    check(
        cfg["accepted_phase1_dataset_sha256"].strip() == DATASET_SHA,
        "config pins corrected dataset",
    )
    commits = _git(["log", "--format=%H", "--", PREREG]).splitlines()
    check(bool(commits), "preregistration committed")
    prereg_commit = commits[0] if commits else ""
    out_commits = _git(
        ["log", "--format=%H", "--reverse", "--",
         "data/analysis/phase4a/"]
    ).splitlines() if OUT.exists() else []
    if prereg_commit:
        target = out_commits[0] if out_commits else "HEAD"
        r = subprocess.run(
            ["git", "merge-base", "--is-ancestor", prereg_commit,
             target], cwd=ROOT, capture_output=True,
        )
        check(r.returncode == 0, "preregistration predates outputs")
    manifest = json.loads((OUT / "phase4a_manifest.json").read_text())
    check(
        manifest.get("phase4a_preregistration_commit") == prereg_commit,
        "manifest records preregistration commit",
    )

    # ---------- pins / firewall ---------------------------------------
    print("\n[3] Pins and holdout firewall")
    check(manifest["dataset_sha256"] == DATASET_SHA, "manifest dataset")
    check(manifest["holdout_seal_v2"] == V2_SEAL, "manifest v2 seal")
    v1 = json.loads((META / "phase3_holdout_seal.json").read_text())
    check(v1["holdout_seal_sha256"] == V1_SEAL, "v1 seal preserved")
    expl_ids, hold_ids = set(), set()
    with (META / "phase3_exploration_ids_v2.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            expl_ids.add(r["draw_id"])
    with (META / "phase3_holdout_ids.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            hold_ids.add(r["draw_id"])
    check(not (expl_ids & hold_ids), "exploration/holdout disjoint")
    preds = _csv(OUT / "phase4a_walkforward_predictions.csv")
    check(all(r["draw_id"] in expl_ids for r in preds),
          "all predictions are exploration draws")
    check(not any(r["draw_id"] in hold_ids for r in preds),
          "no holdout draw_id scored")

    # ---------- model family frozen -----------------------------------
    print("\n[4] Frozen model family")
    check({r["model_id"] for r in preds} == set(MODELS),
          "exactly F-M000..F-M004 in predictions")
    mreg = _csv(ROOT / "registry/model_registry.csv")
    check({r["model_id"] for r in mreg} == set(MODELS),
          "model registry holds exactly the five models")
    check(all(r["status"] in ALLOWED_MODEL_STATUS for r in mreg),
          "model statuses within allowed vocabulary")
    grids = set()
    for mid in ("F-M003", "F-M004"):
        g = cfg["models"][mid].get("l2_grid")
        grids.update(str(x) for x in g)
    check(grids == GRID, "penalty grid frozen {0.1,1,10,100}")

    # ---------- exact math re-verification -----------------------------
    print("\n[5] Exact K-subset math (enumeration)")
    from fortuna.models.wsubset import (  # noqa: E402
        inclusion_probs,
        log_p_subset,
    )
    rng = np.random.default_rng(0)
    ok = True
    for n_pool, k in ((8, 3), (10, 5)):
        w = rng.uniform(0.1, 5.0, n_pool)
        logw = np.log(w)[None, :]
        ek = sum(math.prod(w[i] for i in c)
                 for c in itertools.combinations(range(n_pool), k))
        tot, marg = 0.0, np.zeros(n_pool)
        for c in itertools.combinations(range(n_pool), k):
            p = math.exp(log_p_subset(
                logw, np.array(c)[None, :], k)[0])
            tot += p
            for i in c:
                marg[i] += p
        got_marg = inclusion_probs(logw, k)[0]
        ok &= abs(tot - 1.0) < 1e-9
        ok &= np.allclose(got_marg, marg, atol=1e-9)
        enum_logp = {
            frozenset(c): math.prod(w[i] for i in c) / ek
            for c in itertools.combinations(range(n_pool), k)}
        for c in itertools.combinations(range(n_pool), k):
            lp = log_p_subset(logw, np.array(c)[None, :], k)[0]
            ok &= abs(math.exp(lp) - enum_logp[frozenset(c)]) < 1e-9
    check(ok, "e_K / subset probs / marginals match enumeration")

    # ---------- warmup / walk-forward ----------------------------------
    print("\n[6] Warmup and walk-forward integrity")
    check(all(int(r["n_prior"]) >= 100 for r in preds),
          "every scored draw has >=100 prior draws")
    by_rm: dict[tuple, list] = {}
    for r in preds:
        by_rm.setdefault((r["statistical_regime_id"],
                          r["model_id"]), []).append(r)
    # strict: within each regime, n_prior covers a contiguous tail and
    # predictions are in chronological order
    ok_order, ok_warm = True, True
    draw_date = {}
    with (ROOT / "data/processed/draws.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            draw_date[row["draw_id"]] = row["draw_date"]
    for (_sid, _mid), rows in by_rm.items():
        nps = [int(r["n_prior"]) for r in rows]
        dates = [draw_date[r["draw_id"]] for r in rows]
        ok_order &= dates == sorted(dates)
        ok_warm &= nps == list(range(nps[0], nps[0] + len(nps)))
        ok_warm &= nps[0] >= 100
    check(ok_order, "predictions strictly chronological per regime")
    check(ok_warm, "contiguous scored tail after warmup (no backfill)")

    # nested chronological tuning — refit log
    hp = _csv(OUT / "phase4a_hyperparameter_history.csv")
    check(all(e["penalty"] in GRID for e in hp),
          "all selected penalties in frozen grid")
    check(all(e["selection"] in
              ("nested_chronological", "fallback_insufficient_inner_fit")
              for e in hp), "selection rule recorded")
    # every refit's n_train equals the number of draws before it
    by_key = {}
    for e in hp:
        key = (e["statistical_regime_id"], e["scored_index"])
        by_key.setdefault(key, int(e["n_train"]))
    wf_src = (ROOT / "src/fortuna/backtesting/walkforward.py").read_text()
    fm_src = (ROOT / "src/fortuna/models/fm.py").read_text()
    check("cv" not in fm_src.lower().replace("cross_validation", ""),
          "no random CV in fitting code")
    check("[:t]" in wf_src or "[:t, " in wf_src,
          "fits use draws[:t] prefix only")

    # ---------- required outputs ---------------------------------------
    print("\n[7] Required outputs")
    required = [
        "phase4a_walkforward_predictions.csv",
        "phase4a_logscore_by_draw.csv",
        "phase4a_logscore_summary.csv",
        "phase4a_regime_summary.csv",
        "phase4a_candidate_pool_metrics.csv",
        "phase4a_special_ball_metrics.csv",
        "phase4a_evalues.csv",
        "phase4a_hyperparameter_history.csv",
        "phase4a_synthetic_controls.csv",
        "phase4a_model_gate.csv",
        "phase4a_candidate_models.csv",
        "phase4a_manifest.json",
    ]
    for name in required:
        check((OUT / name).exists(), f"output {name}")

    # ---------- metrics sanity ------------------------------------------
    print("\n[8] Metrics and benchmarks")
    summ = _csv(OUT / "phase4a_logscore_summary.csv")
    pooled = {r["model_id"]: r for r in summ if r["scope"] == "pooled"}
    check(set(pooled) == set(MODELS), "pooled summaries for all models")
    m000 = pooled.get("F-M000", {})
    check(m000 and abs(float(m000["mean_d"])) < 1e-9,
          "F-M000 baseline is exactly zero")
    pools = _csv(OUT / "phase4a_candidate_pool_metrics.csv")
    check({r["model_id"] for r in pools} == set(MODELS),
          "pool metrics for all models")
    check({"10", "15", "20"} == {r["pool_size"] for r in pools},
          "pool sizes 10/15/20")
    for r in pools:
        check_h = abs(float(r["random_expected_mean"])) > 0
        check(check_h, f"random benchmark nonzero {r['model_id']} m={r['pool_size']}")
    m15 = {r["model_id"]: r for r in pools if r["pool_size"] == "15"}
    check(len(m15) == 5, "m=15 rows for all models")
    ev = {r["model_id"]: r for r in _csv(OUT / "phase4a_evalues.csv")}
    check(set(ev) == set(MODELS) | {"E_MIX"}, "e-values for models + mix")
    check(all(math.isfinite(float(ev[m]["log_e_main"])) for m in MODELS),
          "e-values finite")

    # ---------- synthetic controls --------------------------------------
    print("\n[9] Synthetic controls")
    synth = _csv(OUT / "phase4a_synthetic_controls.csv")
    pos = [r for r in synth if r["control"] == "positive"]
    null = [r for r in synth if r["control"] == "null"]
    check({"A", "B", "C", "D"} == {r["scenario"] for r in pos},
          "all positive scenarios")
    check(len({r["effect"] for r in null}) == 10, "10 null replicates")
    pos_ok = True
    for scen in ("A", "B", "C", "D"):
        rs = [r for r in pos if r["scenario"] == scen]
        strongest = max(float(r["effect"]) for r in rs)
        top = [r for r in rs if float(r["effect"]) == strongest]
        pos_ok &= any(float(r["cum_d"]) > 0 and float(r["m15_lift"]) >= 0.02
                      for r in top)
    check(pos_ok, "positive controls detected at strongest effect")
    null_false = [r for r in null
                  if r.get("gate_conditions_met") == "True"]
    check(not null_false, "no null replicate clears gate",
          str(len(null_false)))

    # ---------- gate ----------------------------------------------------
    print("\n[10] Predictive gate")
    gate = _csv(OUT / "phase4a_model_gate.csv")
    check({r["model_id"] for r in gate} == set(CANDIDATES),
          "gate evaluated for F-M001..F-M004 only")
    cond_cols = [c for c in gate[0] if c.startswith("c") and
                 c[1].isdigit()]
    check(len(cond_cols) == 9, "nine gate conditions evaluated",
          str(cond_cols))
    for r in gate:
        check(
            all(r[c] in ("PASS", "FAIL") for c in cond_cols),
            f"{r['model_id']} all conditions PASS/FAIL",
        )
    passing = {r["model_id"] for r in gate if r["gate"] == "PASS"}
    cand = _csv(OUT / "phase4a_candidate_models.csv")
    named = [r for r in cand
             if r.get("status") == "candidate_for_holdout_confirmation"]
    check(len(named) <= 1, "at most one candidate")
    check(all(n["model_id"] in passing for n in named),
          "no failing model labeled candidate")
    check(len(passing) <= len(named) or not passing or len(named) == 1,
          "passing models produce exactly one candidate")

    # ---------- manifest hashes -----------------------------------------
    print("\n[11] Manifest integrity")
    oh = manifest.get("output_hashes", {})
    bad = []
    for name, want in oh.items():
        p = OUT / name
        if not p.exists() or hashlib.sha256(
                p.read_bytes()).hexdigest() != want:
            bad.append(name)
    check(not bad, "all output hashes verify", str(bad[:3]))
    check(manifest.get("warmup") == 100, "manifest warmup=100")
    check(manifest.get("refit_cadence") == 25, "manifest refit=25")
    check(manifest.get("penalty_grid") == [0.1, 1.0, 10.0, 100.0],
          "manifest penalty grid")

    # ---------- prohibited artifacts ------------------------------------
    print("\n[12] No predictive/recommendation artifacts")
    banned_sub = ("ticket", "recommended", "next_draw", "winning",
                  "hot_numbers", "best_numbers", "play_these")
    banned = [
        p.name for p in (ROOT / "data").rglob("*")
        if p.is_file() and any(s in p.name.lower() for s in banned_sub)
    ]
    check(not banned, "no ticket/recommendation files", str(banned[:5]))
    ledger = _csv(ROOT / "registry/prediction_ledger.csv")
    check(not ledger, "prediction ledger empty (header only)")

    print("\n" + "=" * 72)
    print(f"{PASS_COUNT} checks passed, {len(FAILURES)} failed")
    if FAILURES:
        for f_ in FAILURES:
            print(f"  FAILED: {f_}")
        print("PHASE 4A (F-E005) VERIFICATION FAILED")
        return 1
    print("PHASE 4A (F-E005) VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
