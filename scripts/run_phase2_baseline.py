"""Execute the F-E001 Phase 2 fair-random Monte Carlo baseline.

Reads the FROZEN configuration (config/experiments/F-E001.yaml), the frozen
observation plan (metadata/phase2_observation_plan.csv), and the Phase 0
regime inventory. Writes deterministic reference outputs to
data/reference/null_baselines/ with a provenance manifest.

Never reads historical winning-number values: the only historical input is
the observation plan (counts and segment structure).
"""

import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime
from fortuna.simulation import convergence, exact, montecarlo, validation
from fortuna.simulation.matrix import statistical_matrices
from fortuna.simulation.seeding import make_rng
from fortuna.simulation.statistics import CATALOG, applicable_statistics
from fortuna.simulation.structural import structural_exact, structural_simulated

ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = ROOT / "config/experiments/F-E001.yaml"
PLAN_PATH = ROOT / "metadata/phase2_observation_plan.csv"
OUT_DIR = ROOT / "data/reference/null_baselines"
MANIFEST = "phase2_simulation_manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _pmf_stats(pmf: dict[float, float]) -> tuple[float, float]:
    v = np.array(list(pmf.keys()))
    p = np.array(list(pmf.values()))
    mu = float((v * p).sum())
    var = float(((v - mu) ** 2 * p).sum())
    return mu, var


def main() -> int:
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    exp_id = cfg["experiment_id"]
    root_seed = int(cfg["rng"]["root_seed"])
    mc = cfg["monte_carlo"]
    batches, reps = int(mc["batches"]), int(mc["replicates_per_batch"])

    dataset_sha = json.loads(
        (ROOT / "data/processed/dataset_manifest.json").read_text()
    )["dataset_sha256"]
    assert dataset_sha == cfg["accepted_phase1_dataset_sha256"], (
        "Phase 1 dataset hash mismatch — frozen input violated"
    )

    regimes = load_csv(ROOT / "metadata/game_regimes.csv", GameRegime)
    matrices = statistical_matrices(regimes)

    with PLAN_PATH.open(newline="") as f:
        plan_rows = {r["statistical_regime_id"]: r for r in csv.DictReader(f)}

    assert set(plan_rows) == set(matrices), "plan/regime mismatch"
    assert len(matrices) == 16, "expected 16 statistical pool groups"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # ---------- exact baselines ----------
    exact_rows = []
    for sid, m in sorted(matrices.items()):
        n_pool, k = m.main_pool, m.main_count
        mom = exact.inclusion_moments(n_pool, k)
        ov = exact.overlap_pmf(n_pool, k)
        oe = exact.odd_even_pmf(m.main_min, m.main_max, k)
        tk = exact.ticket_match_pmf(m)
        ov_mu, ov_var = _pmf_stats({float(j): p for j, p in enumerate(ov)})
        exact_rows.append({
            "statistical_regime_id": sid,
            "game_id": m.game_id,
            "main_pool_N": n_pool,
            "main_count_K": k,
            "special_pool_M": m.special_pool if m.has_special else 0,
            "main_sample_space": exact.main_sample_space(n_pool, k),
            "jackpot_sample_space": exact.jackpot_sample_space(m),
            "jackpot_prob": exact.jackpot_prob(m),
            "inclusion_prob": exact.inclusion_prob(n_pool, k),
            "pair_prob": exact.pair_prob(n_pool, k),
            "triple_prob": exact.triple_prob(n_pool, k),
            "overlap_pmf": json.dumps([float(p) for p in ov]),
            "overlap_mean": ov_mu,
            "overlap_var": ov_var,
            "odd_even_pmf": json.dumps([float(p) for p in oe]),
            "special_repeat_prob": exact.special_repeat_prob(m) or "",
            "ticket_match_pmf": json.dumps([float(p) for p in tk]),
            "inclusion_var": mom["var"],
            "inclusion_cov_ij": mom["cov"],
        })
    _write_csv(OUT_DIR / "exact_baselines.csv", exact_rows)

    # ---------- structural single-draw distributions ----------
    struct_rows = []
    for sid, m in sorted(matrices.items()):
        for name, pmf in structural_exact(m).items():
            mu, var = _pmf_stats(pmf)
            struct_rows.append({
                "statistical_regime_id": sid, "statistic": name,
                "method": "exact", "mean": mu, "var": var,
                "pmf": json.dumps(pmf),
            })
        rng_s = make_rng(root_seed, exp_id,
                         f"{m.game_id}|{m.statistical_regime_id}|STRUCTURAL")
        for name, pmf in structural_simulated(rng_s, m, 200_000).items():
            mu, var = _pmf_stats(pmf)
            struct_rows.append({
                "statistical_regime_id": sid, "statistic": name,
                "method": "simulated", "mean": mu, "var": var,
                "pmf": json.dumps(pmf),
            })
    _write_csv(OUT_DIR / "structural_distributions.csv", struct_rows)
    print("exact + structural baselines written", flush=True)

    # ---------- Monte Carlo history baselines ----------
    summary_rows, quant_rows, conv_rows = [], [], []
    q_list = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
    for sid in sorted(matrices):
        m = matrices[sid]
        prow = plan_rows[sid]
        n = int(prow["eligible_main_draw_count"])
        seg_lengths = [int(x) for x in
                       prow["contiguous_sequence_segment_lengths"].split(";")]
        res = montecarlo.run_regime(
            m, n, seg_lengths, root_seed, exp_id, batches, reps
        )
        for stat_id in applicable_statistics(m):
            batch_arrays = res[stat_id]
            pooled = np.concatenate(batch_arrays)
            conv = convergence.check_convergence(
                batch_arrays,
                sigma_factor=cfg["convergence"]["sigma_factor"],
                atol_rel=cfg["convergence"]["atol_rel"],
            )
            spec = CATALOG[stat_id]
            summary_rows.append({
                "statistical_regime_id": sid, "statistic_id": stat_id,
                "statistic": spec.name, "sequential": spec.sequential,
                "n_draws_per_replicate": n,
                "replicates": pooled.size,
                "mean": float(pooled.mean()), "var": float(pooled.var()),
                "std": float(pooled.std()),
                "se_mean": float(pooled.std(ddof=1) / np.sqrt(pooled.size)),
                "min": float(pooled.min()), "max": float(pooled.max()),
                "convergence_status": conv.status,
            })
            qv = np.quantile(pooled, q_list)
            row = {"statistical_regime_id": sid, "statistic_id": stat_id}
            row.update({f"q{int(q*100):02d}": float(v)
                        for q, v in zip(q_list, qv, strict=True)})
            for bi, b in enumerate(batch_arrays, 1):
                row[f"batch{bi}_mean"] = float(b.mean())
                row[f"batch{bi}_var"] = float(b.var())
            quant_rows.append(row)
            for met in conv.metrics:
                conv_rows.append({
                    "statistical_regime_id": sid, "statistic_id": stat_id,
                    "metric": met.metric, "pooled": met.pooled,
                    "batch_values": json.dumps(met.batch_values),
                    "max_dev": met.max_dev, "se": met.se, "atol": met.atol,
                    "passed": met.passed,
                })
        print(f"  {sid} done ({time.time()-t0:.0f}s)", flush=True)

    _write_csv(OUT_DIR / "history_baseline_summary.csv", summary_rows)
    _write_csv(OUT_DIR / "history_baseline_quantiles.csv", quant_rows)
    _write_csv(OUT_DIR / "batch_convergence.csv", conv_rows)

    # ---------- theory-to-simulation validation ----------
    val_rows = []
    for sid, m in sorted(matrices.items()):
        rv = validation.validate_regime(
            m, root_seed, exp_id, cfg["validation"]["draws_per_regime"]
        )
        for c in rv.checks:
            val_rows.append({
                "statistical_regime_id": sid, "check": c.name,
                "observed": c.observed, "expected": c.expected,
                "se": c.se, "z": c.z, "passed": c.passed,
            })
        print(f"  {sid} validation {rv.status}", flush=True)
    _write_csv(OUT_DIR / "theory_validation.csv", val_rows)

    # ---------- determinism probes (batch-1 stream fingerprints) ----------
    probes = {
        sid: montecarlo.determinism_probe(m, root_seed, exp_id)
        for sid, m in sorted(matrices.items())
    }

    # ---------- manifest ----------
    outputs = sorted(p for p in OUT_DIR.iterdir() if p.name != MANIFEST)
    manifest = {
        "phase": 2,
        "experiment_id": exp_id,
        "phase2_preregistration_commit": _git(["rev-parse", "HEAD"]),
        "simulation_code_commit": _git(["rev-parse", "HEAD"]),
        "accepted_phase1_dataset_sha256": dataset_sha,
        "root_seed": root_seed,
        "rng_algorithm": cfg["rng"]["algorithm"],
        "child_derivation": cfg["rng"]["child_derivation"],
        "numpy_version": np.__version__,
        "replicates_per_statistic_regime": mc["replicates_per_statistic_regime"],
        "batches": batches,
        "replicates_per_batch": reps,
        "statistics_catalog_version": cfg["statistics_catalog_version"],
        "statistical_regimes": sorted(matrices),
        "observation_plan_sha256": _sha256(PLAN_PATH),
        "determinism_probe_sha256": probes,
        "config_sha256": _sha256(CONFIG_PATH),
        "preregistration_sha256": _sha256(
            ROOT / "research/preregistrations/F-E001-phase2-fair-null-baseline.md"
        ),
        "output_hashes": {p.name: _sha256(p) for p in outputs},
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "validation_status": (
            "PASS" if all(r["passed"] for r in val_rows) else "FAIL"
        ),
        "convergence_status": (
            "NOT CONVERGED"
            if any(r["convergence_status"] == "NOT CONVERGED"
                   for r in summary_rows)
            else "CONVERGED"
        ),
    }
    (OUT_DIR / MANIFEST).write_text(json.dumps(manifest, indent=2))
    print(f"manifest written ({time.time()-t0:.0f}s total)")
    return 0


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
