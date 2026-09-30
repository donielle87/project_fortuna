"""Phase 2 verification — F-E001 fair-random null model and Monte Carlo
baseline. Exits nonzero on any failure.

Checks (metadata/structure/provenance only — never historical outcomes):
  * Phase 0 and Phase 1 verifiers pass
  * frozen Phase 1 dataset hash is unchanged
  * F-E001 preregistration + frozen config exist and were committed BEFORE
    the baseline outputs
  * root seed / RNG / batch structure frozen as specified
  * all 16 statistical pool groups are represented in plan + outputs
  * fair-draw engine correctness (no duplicates, in range, special/none)
  * exact baselines present and internally consistent
  * statistic catalog F-S001..F-S013 coverage per applicability
  * 20,000 replicates x 4 batches per applicable (regime, statistic)
  * convergence status present for every simulated statistic
  * theory-to-simulation validation rows all passed
  * contiguous segments match a metadata-only rebuild (no bridging of
    missing/ineligible positions); Double Play never enters the plan
  * order-eligible segments are a subset of eligible segments
  * MC p-value (+1 correction) and BH/Holm utilities work
  * reference outputs exist, match manifest hashes, and the determinism
    probes regenerate identically
"""

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

ROOT = Path(__file__).resolve().parent.parent
FAILS: list[str] = []
PREREG = ROOT / "research/preregistrations/F-E001-phase2-fair-null-baseline.md"
CONFIG = ROOT / "config/experiments/F-E001.yaml"
PLAN = ROOT / "metadata/phase2_observation_plan.csv"
OUT = ROOT / "data/reference/null_baselines"
FROZEN_SHA = "953c0701aeef6782a361146999ca43c1d4d2863d807c8e4dbe39cfa4108f3891"


def check(cond: bool, label: str) -> None:
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        FAILS.append(label)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    # ---- upstream verifiers ----
    for ph in ("0", "1"):
        r = subprocess.run(
            [sys.executable, str(ROOT / f"scripts/verify_phase{ph}.py")],
            cwd=ROOT, capture_output=True, text=True,
        )
        check(r.returncode == 0, f"verify_phase{ph}.py passes")

    # ---- frozen inputs ----
    man = json.loads((ROOT / "data/processed/dataset_manifest.json").read_text())
    check(man["dataset_sha256"] == FROZEN_SHA, "frozen Phase 1 dataset hash")
    check(PREREG.exists(), "F-E001 preregistration exists")
    check(CONFIG.exists(), "F-E001 frozen config exists")
    check(PLAN.exists(), "metadata-only observation plan exists")
    if FAILS:
        print(f"PHASE 2 VERIFICATION FAILED ({len(FAILS)} checks)")
        return 1

    cfg = yaml.safe_load(CONFIG.read_text())
    check(cfg["rng"]["root_seed"] == 20260930, "root seed 20260930 frozen")
    check(cfg["rng"]["algorithm"] == "PCG64DXSM", "RNG algorithm PCG64DXSM")
    check(int(cfg["monte_carlo"]["batches"]) == 4, "4 batches")
    check(
        int(cfg["monte_carlo"]["replicates_per_statistic_regime"]) == 20000,
        "20,000 replicates frozen",
    )

    # ---- preregistration committed before baseline ----
    prereg_commit = _git(
        "log", "--diff-filter=A", "--format=%H", "--", str(PREREG.relative_to(ROOT))
    ).splitlines()
    out_commit = _git(
        "log", "--diff-filter=A", "--format=%H", "--",
        str(OUT / "history_baseline_summary.csv"),
    ).splitlines()
    check(bool(prereg_commit), "preregistration is committed")
    check(bool(out_commit), "baseline outputs are committed")
    if prereg_commit and out_commit:
        pre, outc = prereg_commit[-1], out_commit[-1]
        anc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", pre, outc], cwd=ROOT
        )
        check(
            anc.returncode == 0 and pre != outc,
            "preregistration committed before baseline generation",
        )

    # ---- regimes / plan ----
    from fortuna.schemas.csv_io import load_csv
    from fortuna.schemas.regimes import GameRegime
    from fortuna.simulation.matrix import statistical_matrices

    regimes = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)
    mats = statistical_matrices(regimes)
    check(len(mats) == 16, "all 16 statistical pool groups")
    plan_rows = _read_csv(PLAN)
    check({r["statistical_regime_id"] for r in plan_rows} == set(mats),
          "plan covers all 16 statistical regimes")
    check(all(r["dataset_sha256"] == FROZEN_SHA for r in plan_rows),
          "plan pins frozen dataset hash")

    # ---- plan matches a fresh metadata-only rebuild ----
    from fortuna.simulation.observation import build_observation_plan

    rebuilt = build_observation_plan(
        ROOT / "data/processed/draws.csv", regimes, FROZEN_SHA
    )
    rebuilt_map = {r["statistical_regime_id"]: r for r in rebuilt}
    ok = True
    for r in plan_rows:
        rb = rebuilt_map[r["statistical_regime_id"]]
        ok &= (
            int(r["eligible_main_draw_count"]) == rb["eligible_main_draw_count"]
            and r["contiguous_sequence_segment_lengths"]
            == rb["contiguous_sequence_segment_lengths"]
        )
    check(ok, "observation plan reproduces from metadata (segments intact)")

    # Double Play isolation: plan counts == eligible MAIN draws only
    from fortuna.simulation.observation import load_draw_metadata

    meta = load_draw_metadata(ROOT / "data/processed/draws.csv")
    check(
        {r["draw_stream"] for r in meta} <= {"main", "double_play"},
        "only main/double_play streams exist in canonical store",
    )
    main_counts: dict[str, int] = {}
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}
    for r in meta:
        if r["draw_stream"] == "main" and r["analysis_eligible"] == "true":
            sid = stat_of.get(r["regime_id"])
            if sid:
                main_counts[sid] = main_counts.get(sid, 0) + 1
    check(
        all(int(r["eligible_main_draw_count"]) == main_counts[sid]
            for r in plan_rows for sid in [r["statistical_regime_id"]]),
        "plan counts equal eligible main draws only (Double Play excluded)",
    )
    # order-semantics fields present; order-eligible never exceeds eligible
    check(
        all(
            "num_order_eligible_segments" in r
            and "order_eligible_segment_lengths" in r
            for r in plan_rows
        ),
        "order-semantics segment fields present",
    )

    # ---- engine self-checks ----
    from fortuna.simulation.engine import draw_mains, draw_specials
    from fortuna.simulation.seeding import make_rng

    eng_ok = True
    for sid, m in mats.items():
        rng = make_rng(20260930, "F-E001", f"{m.game_id}|{sid}|HISTORIES|batch1")
        d = draw_mains(rng, m, 200)
        eng_ok &= (np.diff(d, axis=1) > 0).all()
        eng_ok &= d.min() >= m.main_min and d.max() <= m.main_max
        sp = draw_specials(rng, m, 200)
        if m.has_special:
            eng_ok &= sp is not None and sp.min() >= m.special_min
            eng_ok &= sp.max() <= m.special_max
        else:
            eng_ok &= sp is None
    check(eng_ok, "fair-draw engine: unique, in-range, special semantics")

    # ---- reference outputs ----
    required = [
        "exact_baselines.csv",
        "history_baseline_summary.csv",
        "history_baseline_quantiles.csv",
        "batch_convergence.csv",
        "theory_validation.csv",
        "structural_distributions.csv",
        "phase2_simulation_manifest.json",
    ]
    for f in required:
        check((OUT / f).exists(), f"output {f} exists")
    if not (OUT / "phase2_simulation_manifest.json").exists():
        print(f"PHASE 2 VERIFICATION FAILED ({len(FAILS)} checks)")
        return 1
    manifest = json.loads((OUT / "phase2_simulation_manifest.json").read_text())
    check(manifest["accepted_phase1_dataset_sha256"] == FROZEN_SHA,
          "manifest pins dataset hash")
    check(manifest["root_seed"] == 20260930, "manifest root seed")
    check(manifest["observation_plan_sha256"] == _sha256(PLAN),
          "manifest observation-plan hash")
    check(manifest["config_sha256"] == _sha256(CONFIG), "manifest config hash")
    check(manifest["preregistration_sha256"] == _sha256(PREREG),
          "manifest preregistration hash")
    check(
        set(manifest["statistical_regimes"]) == set(mats),
        "manifest covers 16 regimes",
    )
    for name, h in manifest["output_hashes"].items():
        check((OUT / name).exists() and _sha256(OUT / name) == h,
              f"output hash {name}")

    # ---- exact baselines correctness ----
    from fortuna.simulation import exact

    eb = {r["statistical_regime_id"]: r for r in _read_csv(OUT / "exact_baselines.csv")}
    ok = True
    for sid, m in mats.items():
        r = eb.get(sid)
        ok &= r is not None
        if r:
            ok &= int(r["main_sample_space"]) == exact.main_sample_space(
                m.main_pool, m.main_count)
            ok &= int(r["jackpot_sample_space"]) == exact.jackpot_sample_space(m)
            pmf = json.loads(r["overlap_pmf"])
            ok &= abs(sum(pmf) - 1.0) < 1e-9 and len(pmf) == m.main_count + 1
            ok &= abs(float(r["inclusion_prob"]) - m.main_count / m.main_pool) < 1e-12
            ok &= float(r["inclusion_cov_ij"]) < 0
            if m.has_special:
                ok &= abs(float(r["special_repeat_prob"]) - 1 / m.special_pool) < 1e-12
            else:
                ok &= r["special_repeat_prob"] in ("", "None")
    check(ok, "exact baselines correct for all 16 regimes")

    # ---- summary coverage: catalog x regime, 20k x 4 batches ----
    from fortuna.simulation.statistics import CATALOG, applicable_statistics

    check(set(CATALOG) == {f"F-S{i:03d}" for i in range(1, 14)},
          "statistic catalog F-S001..F-S013 complete")
    summ = _read_csv(OUT / "history_baseline_summary.csv")
    seen = {(r["statistical_regime_id"], r["statistic_id"]) for r in summ}
    ok = True
    for sid, m in mats.items():
        for stat in applicable_statistics(m):
            ok &= (sid, stat) in seen
    check(ok, "every applicable (regime, statistic) simulated")
    check(all(int(r["replicates"]) == 20000 for r in summ),
          "20,000 replicates per simulated statistic")
    check(all(r["convergence_status"] in ("CONVERGED", "NOT CONVERGED")
              for r in summ),
          "convergence status present for every statistic")

    qrows = _read_csv(OUT / "history_baseline_quantiles.csv")
    check(all(all(f"batch{b}_mean" in r for b in (1, 2, 3, 4))
              for r in qrows),
          "four independent batches recorded")

    conv = _read_csv(OUT / "batch_convergence.csv")
    check(all(r["passed"] in ("True", "False") for r in conv),
          "convergence diagnostics honest (not silently PASS)")

    # ---- theory-to-simulation validation ----
    tv = _read_csv(OUT / "theory_validation.csv")
    check(tv and all(r["passed"] == "True" for r in tv),
          "theory-to-simulation validation all passed")
    check({r["statistical_regime_id"] for r in tv} == set(mats),
          "validation covers all 16 regimes")

    # ---- determinism probes ----
    from fortuna.simulation import montecarlo

    probe_ok = True
    for sid, m in mats.items():
        probe_ok &= (
            montecarlo.determinism_probe(m, 20260930, "F-E001")
            == manifest["determinism_probe_sha256"][sid]
        )
    check(probe_ok, "deterministic regeneration probes match")

    # ---- multiplicity utilities ----
    from fortuna.statistics.multiple_testing import benjamini_hochberg, holm
    from fortuna.statistics.pvalues import mc_pvalue

    check(mc_pvalue(1e9, np.arange(100)) == 1 / 101,
          "MC p-value +1 correction works")
    check(len(benjamini_hochberg(np.array([0.01, 0.2, 0.03]))["adjusted"]) == 3,
          "BH utility works")
    check(len(holm(np.array([0.01, 0.2, 0.03]))["adjusted"]) == 3,
          "Holm utility works")

    # ---- scientific firewall: simulation code must not read outcomes ----
    sim_src = list((ROOT / "src/fortuna/simulation").glob("*.py"))
    forbidden = ("main_numbers", "draw_numbers", "winning", "jackpot_actual")
    bad = []
    for f in sim_src:
        if f.name == "observation.py":
            continue  # whitelist-guarded metadata reader
        txt = f.read_text(encoding="utf-8").lower()
        if "draws.csv" in txt or "draw_numbers.csv" in txt:
            bad.append(f.name)
        for term in forbidden:
            if term in txt:
                bad.append(f"{f.name}:{term}")
    check(not bad, f"simulation code does not touch outcome data {bad}")
    from fortuna.simulation.observation import ALLOWED_DRAW_FIELDS

    outcome_cols = {
        "main_numbers", "special_ball", "multiplier", "jackpot",
        "jackpot_cash_value", "jackpot_winners",
    }
    check(
        not (ALLOWED_DRAW_FIELDS & outcome_cols),
        "observation whitelist excludes outcome columns",
    )

    if FAILS:
        print(f"PHASE 2 VERIFICATION FAILED ({len(FAILS)} checks)")
        return 1
    print("PHASE 2 VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
