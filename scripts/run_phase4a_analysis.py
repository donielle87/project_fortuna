"""F-E005 Phase 4A — finite predictive walk-forward benchmark runner.

Strictly exploration-scoped: outcome fields are parsed ONLY for draw_ids
in metadata/phase3_exploration_ids_v2.csv (firewalled loader). The sealed
holdout contributes metadata-only seal/disjointness verification.

Deterministic: no RNG is consumed during historical evaluation. Scoped
PCG64DXSM streams (root_seed 20261007, experiment F-E005) are used only
for synthetic control histories.
"""

import csv
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fortuna.analysis.loader import load_exploration_draws  # noqa: E402
from fortuna.analysis.split import holdout_seal_sha256  # noqa: E402
from fortuna.backtesting import synth  # noqa: E402
from fortuna.backtesting.walkforward import (  # noqa: E402
    POOL_SIZES,
    run_regime_walkforward,
)
from fortuna.models import fm  # noqa: E402
from fortuna.schemas.csv_io import load_csv  # noqa: E402
from fortuna.schemas.regimes import GameRegime  # noqa: E402
from fortuna.simulation.matrix import statistical_matrices  # noqa: E402

META = ROOT / "metadata"
DRAWS = ROOT / "data/processed/draws.csv"
EXPL_PATH = META / "phase3_exploration_ids_v2.csv"
HOLD_PATH = META / "phase3_holdout_ids.csv"
SEAL_PATH = META / "phase3_holdout_seal_v2.json"
OUT = ROOT / "data/analysis/phase4a"
CFG_PATH = ROOT / "config/experiments/F-E005.yaml"
PREREG_COMMIT_PATH = OUT / "_prereg_commit.txt"

CANDIDATE_MODELS = ("F-M001", "F-M002", "F-M003", "F-M004")
E_GATE = 80.0
E_MIX_GATE = 20.0
M15_LIFT_GATE = 0.02
MIN_REGIME_N = 50
REGIME_FRAC_GATE = 0.60
CONCENTRATION_GATE = 0.50


def _ci95(x: np.ndarray) -> tuple[float, float]:
    if x.size < 2:
        return 0.0, 0.0
    se = float(x.std(ddof=1) / math.sqrt(x.size))
    return float(x.mean() - 1.96 * se), float(x.mean() + 1.96 * se)


def _hg_expect(n_pool: int, m: int, k: int) -> float:
    return k * m / n_pool


def _hg_tail(n_pool: int, m: int, k: int, h: int) -> float:
    den = math.comb(n_pool, k)
    return sum(
        math.comb(m, hh) * math.comb(n_pool - m, k - hh)
        for hh in range(h, min(m, k) + 1)
    ) / den


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> str:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames,
                           extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return _sha256(path)


def _summarize(rows: list[dict], k: int, n_pool: int) -> dict:
    """Pooled walk-forward summary for one model's scored-draw rows."""
    d = np.array([float(r["d_main"]) for r in rows])
    dj = np.array([float(r["d_joint"]) for r in rows])
    hits15 = np.array([r["pool_hits"].get(15, np.nan) for r in rows],
                      dtype=float)
    exp15 = _hg_expect(n_pool, 15, k) if n_pool > 15 else np.nan
    imp = hits15 - exp15
    lo, hi = _ci95(imp[~np.isnan(imp)])
    return {
        "n": d.size, "mean_d": float(d.mean()), "cum_d": float(d.sum()),
        "cum_d_joint": float(dj.sum()),
        "hits15_mean": float(np.nanmean(hits15)),
        "exp15": float(exp15), "lift15": float(np.nanmean(hits15) / exp15 - 1),
        "imp15_mean": float(np.nanmean(imp)),
        "imp15_ci": (lo, hi),
    }


def _evaluate_gate(mid: str, pooled: dict, regime_means: list[tuple[str, int, float]],
                   reg_gain: dict[str, float]) -> dict:
    """Nine frozen gate conditions -> PASS/FAIL dict."""
    pos = pooled["cum_d"] > 0
    e_model = pooled["e_model"] >= E_GATE
    e_mix = pooled["e_mix"] >= E_MIX_GATE
    eligible = [x for x in regime_means if x[1] >= MIN_REGIME_N]
    frac = (sum(1 for x in eligible if x[2] > 0) / len(eligible)
            ) if eligible else 0.0
    cond4 = frac >= REGIME_FRAC_GATE
    total_pos = sum(g for g in reg_gain.values() if g > 0)
    best = max(reg_gain.values()) if reg_gain else 0.0
    conc = (best / total_pos) if total_pos > 0 else 1.0
    cond5 = conc <= CONCENTRATION_GATE
    cond6 = pooled["lift15"] >= M15_LIFT_GATE
    lo, hi = pooled["imp15_ci"]
    cond7 = lo > 0.0
    return {
        "model_id": mid,
        "c1_positive_pooled_logscore": "PASS" if pos else "FAIL",
        "c2_evalue_ge80": "PASS" if e_model else "FAIL",
        "c3_emix_ge20": "PASS" if e_mix else "FAIL",
        "c4_regime_fraction": "PASS" if cond4 else "FAIL",
        "c5_concentration": "PASS" if cond5 else "FAIL",
        "c6_m15_lift": "PASS" if cond6 else "FAIL",
        "c7_m15_ci_excludes_zero": "PASS" if cond7 else "FAIL",
        "c8_no_leakage": "PASS",   # firewall verified upstream
        "c9_synthetic_controls": None,  # filled after controls run
        "regime_positive_fraction": f"{frac:.3f}",
        "n_eligible_regimes": len(eligible),
        "concentration": f"{conc:.4f}",
        "gate": "PENDING",
    }


def main() -> None:
    t0 = time.time()
    cfg = yaml.safe_load(CFG_PATH.read_text())
    exp_id = cfg["experiment_id"]
    OUT.mkdir(parents=True, exist_ok=True)

    dataset_sha = json.loads(
        (ROOT / "data/processed/dataset_manifest.json").read_text()
    )["dataset_sha256"]
    assert dataset_sha == cfg["accepted_phase1_dataset_sha256"]
    seal_doc = json.loads(SEAL_PATH.read_text())
    assert seal_doc["dataset_sha256"] == dataset_sha
    assert seal_doc["holdout_seal_sha256"] == cfg[
        "expected_holdout_seal_v2"]

    regimes = load_csv(META / "game_regimes.csv", GameRegime)
    matrices = statistical_matrices(regimes)
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}
    game_of_sid = {s: m.game_id for s, m in matrices.items()}

    expl_ids, hold_ids = set(), set()
    with EXPL_PATH.open(newline="") as f:
        for r in csv.DictReader(f):
            expl_ids.add(r["draw_id"])
    with HOLD_PATH.open(newline="") as f:
        for r in csv.DictReader(f):
            hold_ids.add(r["draw_id"])
    assert not (expl_ids & hold_ids)
    assert holdout_seal_sha256(DRAWS, hold_ids) == seal_doc[
        "holdout_seal_sha256"], "HOLDOUT SEAL BROKEN"

    draws = load_exploration_draws(DRAWS, expl_ids)
    by_sid: dict[str, list] = {}
    for d in sorted(draws, key=lambda d: (d.draw_date, d.draw_id)):
        by_sid.setdefault(stat_of[d.regime_id], []).append(d)

    refit_log: list[dict] = []
    pred_rows: list[dict] = []
    # sid -> mid -> per-scored-draw result dicts
    reg_rows: dict[str, dict[str, list]] = {}
    for sid in sorted(by_sid):
        m = matrices[sid]
        hist = by_sid[sid]
        draws0 = np.array(
            [[x - m.main_min for x in d.mains] for d in hist])
        sp0 = (np.array([d.special - m.special_min for d in hist])
               if m.has_special else None)
        rows = run_regime_walkforward(
            draws0, sp0, m.main_pool, m.main_count,
            m.special_pool, sid, refit_log)
        reg_rows[sid] = rows
        for mid, recs in rows.items():
            for r in recs:
                d = hist[r["draw_index"]]
                pred_rows.append({
                    "draw_id": d.draw_id,
                    "statistical_regime_id": sid,
                    "game_id": m.game_id,
                    "model_id": mid,
                    "n_prior": r["n_prior"],
                    "logp_main_model": f'{r["logp_main_model"]:.6f}',
                    "logp_main_uniform": f'{r["logp_main_uniform"]:.6f}',
                    "d_main": f'{r["d_main"]:.6f}',
                    "logp_special_model": f'{r["logp_special_model"]:.6f}',
                    "logp_special_uniform":
                        f'{r["logp_special_uniform"]:.6f}',
                    "d_special": f'{r["d_special"]:.6f}',
                    "d_joint": f'{r["d_joint"]:.6f}',
                    "pool_hits_10": r["pool_hits"].get(10, ""),
                    "pool_hits_15": r["pool_hits"].get(15, ""),
                    "pool_hits_20": r["pool_hits"].get(20, ""),
                    "sp_prob_actual": r["sp_prob_actual"],
                    "sp_rank_actual": r["sp_rank_actual"],
                    "sp_top5": r["sp_top5"],
                })
        print(f"{sid}: {len(hist)} exploration draws, "
              f"{len(rows['F-M004'])} scored ({time.time()-t0:.0f}s)",
              flush=True)

    # ---------------- pooled / regime summaries -----------------------
    pooled: dict[str, dict] = {}
    for mid in fm.MODEL_IDS:
        rows = [r for sid in reg_rows for r in reg_rows[sid][mid]]
        pooled[mid] = {"rows": rows}
    e_main = {mid: sum(float(r["d_main"]) for r in pooled[mid]["rows"])
              for mid in fm.MODEL_IDS}
    e_joint = {mid: sum(float(r["d_joint"]) for r in pooled[mid]["rows"])
               for mid in fm.MODEL_IDS}
    e_mix = sum(math.exp(e_joint[m]) for m in CANDIDATE_MODELS) / 4

    reg_means: dict[str, list] = {}   # mid -> [(sid, n, mean_d)]
    reg_gain: dict[str, dict] = {}    # mid -> {sid: cum_d}
    for mid in fm.MODEL_IDS:
        reg_means[mid], reg_gain[mid] = [], {}
        for sid in reg_rows:
            dd = np.array([float(r["d_main"]) for r in
                           reg_rows[sid][mid]])
            reg_means[mid].append((sid, dd.size, float(dd.mean())))
            reg_gain[mid][sid] = float(dd.sum())

    summary_rows, regime_rows = [], []
    for mid in fm.MODEL_IDS:
        d = np.array([float(r["d_main"]) for r in pooled[mid]["rows"]])
        lo, hi = _ci95(d)
        summary_rows.append({
            "model_id": mid, "scope": "pooled", "n_scored": d.size,
            "mean_d": f"{d.mean():.6f}", "median_d": f"{np.median(d):.6f}",
            "cum_d": f"{d.sum():.4f}",
            "se": f"{d.std(ddof=1)/math.sqrt(d.size):.6f}",
            "ci95_lo": f"{lo:.6f}", "ci95_hi": f"{hi:.6f}",
        })
        for gid in sorted(set(game_of_sid.values())):
            gd = np.array([float(r["d_main"]) for sid in reg_rows
                           if game_of_sid[sid] == gid
                           for r in reg_rows[sid][mid]])
            if gd.size:
                lo, hi = _ci95(gd)
                summary_rows.append({
                    "model_id": mid, "scope": f"game:{gid}",
                    "n_scored": gd.size, "mean_d": f"{gd.mean():.6f}",
                    "median_d": f"{np.median(gd):.6f}",
                    "cum_d": f"{gd.sum():.4f}",
                    "se": f"{gd.std(ddof=1)/math.sqrt(gd.size):.6f}",
                    "ci95_lo": f"{lo:.6f}", "ci95_hi": f"{hi:.6f}",
                })
        for sid in sorted(reg_rows):
            dd = np.array([float(r["d_main"]) for r in
                           reg_rows[sid][mid]])
            lo, hi = _ci95(dd)
            regime_rows.append({
                "model_id": mid, "statistical_regime_id": sid,
                "game_id": game_of_sid[sid], "n_scored": dd.size,
                "mean_d": f"{dd.mean():.6f}",
                "median_d": f"{np.median(dd):.6f}",
                "cum_d": f"{dd.sum():.4f}",
                "se": f"{dd.std(ddof=1)/math.sqrt(dd.size):.6f}"
                if dd.size > 1 else "0",
                "ci95_lo": f"{lo:.6f}", "ci95_hi": f"{hi:.6f}",
            })

    print(f"historical scoring done ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- candidate-pool metrics --------------------------
    pool_rows = []
    pool_lift15: dict[str, tuple] = {}
    for mid in fm.MODEL_IDS:
        for m_pool in POOL_SIZES:
            hits_l, exp_l, tail_l = [], [], {3: [], 4: [], 5: []}
            for sid in reg_rows:
                m = matrices[sid]
                if m_pool >= m.main_pool:
                    continue
                for r in reg_rows[sid][mid]:
                    hits_l.append(r["pool_hits"][m_pool])
                    exp_l.append(_hg_expect(m.main_pool, m_pool,
                                            m.main_count))
                    for h in (3, 4, 5):
                        if h <= m.main_count:
                            tail_l[h].append(_hg_tail(
                                m.main_pool, m_pool, m.main_count, h))
            if not hits_l:
                continue
            hits = np.array(hits_l, dtype=float)
            expv = np.array(exp_l)
            n_draws = hits.size
            obs_mean = float(hits.mean())
            exp_mean = float(expv.mean())
            imp = hits - expv
            lo, hi = _ci95(imp)
            row = {
                "model_id": mid, "pool_size": m_pool,
                "n_draws": n_draws,
                "mean_hits": f"{obs_mean:.4f}",
                "random_expected_mean": f"{exp_mean:.4f}",
                "relative_lift": f"{obs_mean/exp_mean - 1:.4f}",
                "abs_improvement": f"{imp.mean():.4f}",
                "imp_ci95_lo": f"{lo:.4f}", "imp_ci95_hi": f"{hi:.4f}",
                "obs_P_ge3": f"{(hits >= 3).mean():.4f}",
                "obs_P_ge4": f"{(hits >= 4).mean():.4f}",
                "obs_P_ge5": f"{(hits >= 5).mean():.4f}",
                "rand_P_ge3": f"{np.mean(tail_l[3]):.4f}",
                "rand_P_ge4": f"{np.mean(tail_l[4]):.4f}",
                "rand_P_ge5": f"{np.mean(tail_l[5]):.4f}",
            }
            # all-but-one: K=5 -> >=4; K=6 -> >=5
            abo_hits, abo_rand, abo_n = 0, 0.0, 0
            for sid in reg_rows:
                m = matrices[sid]
                if m_pool >= m.main_pool:
                    continue
                target = 4 if m.main_count == 5 else 5
                for r in reg_rows[sid][mid]:
                    if m_pool in r["pool_hits"]:
                        abo_n += 1
                        abo_hits += int(r["pool_hits"][m_pool] >= target)
                        abo_rand += _hg_tail(m.main_pool, m_pool,
                                             m.main_count, target)
            row["all_but_one_obs"] = f"{abo_hits/abo_n:.5f}"
            row["all_but_one_rand"] = f"{abo_rand/abo_n:.5f}"
            pool_rows.append(row)
            if m_pool == 15:
                pool_lift15[mid] = (obs_mean / exp_mean - 1, lo, hi)

    # ---------------- special-ball metrics ----------------------------
    sp_rows = []
    for sid in reg_rows:
        m = matrices[sid]
        if not m.has_special:
            continue
        mp = m.special_pool
        for mid in fm.MODEL_IDS:
            recs = reg_rows[sid][mid]
            d_sp = np.array([float(r["d_special"]) for r in recs])
            pa = np.array([float(r["sp_prob_actual"]) for r in recs])
            rk = np.array([int(r["sp_rank_actual"]) for r in recs])
            t5 = np.array([bool(r["sp_top5"]) for r in recs])
            sp_rows.append({
                "model_id": mid, "statistical_regime_id": sid,
                "n_scored": len(recs), "special_pool": mp,
                "mean_d_special": f"{d_sp.mean():.6f}",
                "mean_prob_actual": f"{pa.mean():.5f}",
                "uniform_prob": f"{1.0/mp:.5f}",
                "top1_hit_rate": f"{(rk == 1).mean():.4f}",
                "rand_top1": f"{1.0/mp:.4f}",
                "top5_hit_rate": f"{t5.mean():.4f}",
                "rand_top5": f"{min(5, mp)/mp:.4f}",
            })

    # ---------------- e-values ---------------------------------------
    evalue_rows = []
    for mid in fm.MODEL_IDS:
        evalue_rows.append({
            "model_id": mid,
            "log_e_main": f"{e_main[mid]:.4f}",
            "e_main": f"{math.exp(min(e_main[mid], 700)):.6g}",
            "log_e_joint": f"{e_joint[mid]:.4f}",
            "e_joint": f"{math.exp(min(e_joint[mid], 700)):.6g}",
        })
    evalue_rows.append({
        "model_id": "E_MIX",
        "log_e_main": "",
        "e_main": f"{sum(math.exp(min(e_main[m],700)) for m in CANDIDATE_MODELS)/4:.6g}",
        "log_e_joint": "",
        "e_joint": f"{e_mix:.6g}",
    })

    # ---------------- synthetic controls ------------------------------
    ctrl = cfg["synthetic_controls"]
    cn, ck, cm = (ctrl["matrix"]["N"], ctrl["matrix"]["K"],
                  ctrl["matrix"]["M"])
    t_len = ctrl["history_length"]
    synth_rows = []
    control_pass = {"positive": True, "null": True}

    scen_cfg = {
        "A": ctrl["positive_scenarios"]["A_persistent_weight_bias"]["deltas"],
        "B": ctrl["positive_scenarios"]["B_recency_gap_bias"]["betas"],
        "C": ctrl["positive_scenarios"]["C_previous_draw_bias"]["betas"],
        "D": ctrl["positive_scenarios"]["D_time_varying_bias"]["deltas"],
    }
    boosted = np.arange(7)
    for scen, strengths in scen_cfg.items():
        for s in strengths:
            rng = synth.control_rng(exp_id, scen, float(s), 0)
            draws0, sp0 = synth.biased_history(
                rng, t_len, cn, ck, cm, scen, float(s), boosted)
            log: list[dict] = []
            rows = run_regime_walkforward(
                draws0, sp0, cn, ck, cm, f"SYN-{scen}-{s}", log)
            for mid in CANDIDATE_MODELS:
                d = np.array([float(r["d_main"]) for r in rows[mid]])
                h15 = np.array([r["pool_hits"].get(15, np.nan)
                                for r in rows[mid]], dtype=float)
                e15 = _hg_expect(cn, 15, ck)
                lift = float(np.nanmean(h15) / e15 - 1)
                synth_rows.append({
                    "control": "positive", "scenario": scen,
                    "effect": s, "model_id": mid,
                    "n_scored": d.size, "mean_d": f"{d.mean():.6f}",
                    "cum_d": f"{d.sum():.3f}",
                    "log_e_main": f"{d.sum():.3f}",
                    "m15_lift": f"{lift:.4f}",
                })
        strongest = max(float(s) for s in strengths)
        ok = any(
            float(r["cum_d"]) > 0 and float(r["m15_lift"]) >= M15_LIFT_GATE
            for r in synth_rows
            if r["scenario"] == scen and float(r["effect"]) == strongest)
        control_pass["positive"] &= ok
        print(f"control {scen} strongest={strongest}: "
              f"{'PASS' if ok else 'FAIL'} ({time.time()-t0:.0f}s)",
              flush=True)

    for rep in range(ctrl["null_replicates"]):
        rng = synth.control_rng(exp_id, "NULL", 0.0, rep)
        draws0, sp0 = synth.fair_history(rng, t_len, cn, ck, cm)
        log: list[dict] = []
        rows = run_regime_walkforward(
            draws0, sp0, cn, ck, cm, f"SYN-NULL-{rep}", log)
        for mid in CANDIDATE_MODELS:
            d = np.array([float(r["d_main"]) for r in rows[mid]])
            h15 = np.array([r["pool_hits"].get(15, np.nan)
                            for r in rows[mid]], dtype=float)
            e15 = _hg_expect(cn, 15, ck)
            lift = float(np.nanmean(h15) / e15 - 1)
            imp = h15[~np.isnan(h15)] - e15
            lo, hi = _ci95(imp)
            gate_would_pass = (
                d.sum() > 0 and d.sum() >= math.log(E_GATE)
                and lift >= M15_LIFT_GATE and lo > 0)
            synth_rows.append({
                "control": "null", "scenario": "NULL",
                "effect": rep, "model_id": mid,
                "n_scored": d.size, "mean_d": f"{d.mean():.6f}",
                "cum_d": f"{d.sum():.3f}",
                "log_e_main": f"{d.sum():.3f}",
                "m15_lift": f"{lift:.4f}",
                "gate_conditions_met": bool(gate_would_pass),
            })
            if gate_would_pass:
                control_pass["null"] = False
        print(f"null rep {rep} done ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- gate --------------------------------------------
    gate_rows = []
    for mid in CANDIDATE_MODELS:
        # per-row paired m15 improvement vs the row's own regime null
        hits_l, exp_l = [], []
        for sid in reg_rows:
            m = matrices[sid]
            if 15 >= m.main_pool:
                continue
            for r in reg_rows[sid][mid]:
                hits_l.append(r["pool_hits"][15])
                exp_l.append(_hg_expect(m.main_pool, 15, m.main_count))
        hits15 = np.array(hits_l, dtype=float)
        exp15 = np.array(exp_l)
        imp = hits15 - exp15
        lo, hi = _ci95(imp)
        lift15 = float(hits15.mean() / exp15.mean() - 1)
        d = np.array([float(r["d_main"]) for r in pooled[mid]["rows"]])
        p = {
            "cum_d": float(d.sum()), "e_model": math.exp(min(e_joint[mid], 700)),
            "e_mix": e_mix, "lift15": lift15, "imp15_ci": (lo, hi),
        }
        g = _evaluate_gate(mid, p, reg_means[mid], reg_gain[mid])
        g["c9_synthetic_controls"] = (
            "PASS" if control_pass["positive"] and
            control_pass["null"] else "FAIL")
        overall = all(v == "PASS" for k, v in g.items()
                      if k.startswith("c") and k != "c9_synthetic_controls"
                      ) and g["c9_synthetic_controls"] == "PASS"
        g["gate"] = "PASS" if overall else "FAIL"
        gate_rows.append(g)

    # candidate selection (frozen rule)
    passing = [g["model_id"] for g in gate_rows if g["gate"] == "PASS"]
    cand_rows = []
    if passing:
        def _key(mid):
            cum = sum(float(r["d_main"]) for r in pooled[mid]["rows"])
            return (-cum, -pool_lift15.get(mid, (0,))[0],
                    int(mid[-1]))
        cand = sorted(passing, key=_key)[0]
        cand_rows.append({
            "model_id": cand,
            "status": "candidate_for_holdout_confirmation",
            "cum_d_main": f"{sum(float(r['d_main']) for r in pooled[cand]['rows']):.4f}",
            "m15_lift": f"{pool_lift15[cand][0]:.4f}",
            "note": "Selected by frozen tie-break rule; holdout remains "
                    "sealed pending research-lead authorization.",
        })

    # ---------------- write outputs -----------------------------------
    hashes = {}
    hashes["phase4a_walkforward_predictions.csv"] = _write_csv(
        OUT / "phase4a_walkforward_predictions.csv", pred_rows,
        list(pred_rows[0].keys()))
    score_rows = [
        {k: r[k] for k in ("draw_id", "statistical_regime_id",
                           "model_id", "n_prior", "logp_main_model",
                           "logp_main_uniform", "d_main",
                           "logp_special_model", "d_special", "d_joint")}
        for r in pred_rows]
    hashes["phase4a_logscore_by_draw.csv"] = _write_csv(
        OUT / "phase4a_logscore_by_draw.csv", score_rows,
        list(score_rows[0].keys()))
    hashes["phase4a_logscore_summary.csv"] = _write_csv(
        OUT / "phase4a_logscore_summary.csv", summary_rows,
        list(summary_rows[0].keys()))
    hashes["phase4a_regime_summary.csv"] = _write_csv(
        OUT / "phase4a_regime_summary.csv", regime_rows,
        list(regime_rows[0].keys()))
    hashes["phase4a_candidate_pool_metrics.csv"] = _write_csv(
        OUT / "phase4a_candidate_pool_metrics.csv", pool_rows,
        list(pool_rows[0].keys()))
    hashes["phase4a_special_ball_metrics.csv"] = _write_csv(
        OUT / "phase4a_special_ball_metrics.csv", sp_rows,
        list(sp_rows[0].keys()))
    hashes["phase4a_evalues.csv"] = _write_csv(
        OUT / "phase4a_evalues.csv", evalue_rows,
        list(evalue_rows[0].keys()))
    hp_rows = [{
        "statistical_regime_id": e["statistical_regime_id"],
        "model_id": e["model_id"], "target": e["target"],
        "scored_index": e["scored_index"], "n_train": e["n_train"],
        "penalty": e["penalty"], "selection": e["selection"],
    } for e in refit_log]
    hashes["phase4a_hyperparameter_history.csv"] = _write_csv(
        OUT / "phase4a_hyperparameter_history.csv", hp_rows,
        list(hp_rows[0].keys()))
    hashes["phase4a_synthetic_controls.csv"] = _write_csv(
        OUT / "phase4a_synthetic_controls.csv", synth_rows,
        list(synth_rows[0].keys()))
    hashes["phase4a_model_gate.csv"] = _write_csv(
        OUT / "phase4a_model_gate.csv", gate_rows,
        list(gate_rows[0].keys()))
    if cand_rows:
        hashes["phase4a_candidate_models.csv"] = _write_csv(
            OUT / "phase4a_candidate_models.csv", cand_rows,
            list(cand_rows[0].keys()))
    else:
        hashes["phase4a_candidate_models.csv"] = _write_csv(
            OUT / "phase4a_candidate_models.csv",
            [{"model_id": "", "status": "none", "cum_d_main": "",
              "m15_lift": "",
              "note": "No model cleared the gate; no candidate."}],
            ["model_id", "status", "cum_d_main", "m15_lift", "note"])

    feature_schema = {
        "main": cfg["models"]["F-M004"]["features_main"],
        "special": cfg["models"]["F-M004"]["features_special"],
    }
    manifest = {
        "experiment_id": exp_id,
        "phase4a_preregistration_commit": subprocess.run(
            ["git", "log", "--format=%H", "-n", "1", "--",
             "research/preregistrations/F-E005-predictive-walkforward.md",
             "config/experiments/F-E005.yaml"],
            capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "analysis_code_commit":
            subprocess.run(["git", "rev-parse", "HEAD"],
                           capture_output=True, text=True,
                           cwd=ROOT).stdout.strip(),
        "dataset_sha256": dataset_sha,
        "exploration_manifest_sha256": _sha256(EXPL_PATH),
        "holdout_manifest_sha256": _sha256(HOLD_PATH),
        "holdout_seal_v2": seal_doc["holdout_seal_sha256"],
        "n_exploration_draws": len(expl_ids),
        "n_holdout_draws_metadata_only": len(hold_ids),
        "models": {m: cfg["models"][m] for m in fm.MODEL_IDS},
        "feature_schema_sha256": hashlib.sha256(
            json.dumps(feature_schema, sort_keys=True).encode()
        ).hexdigest(),
        "warmup": 100, "refit_cadence": 25,
        "inner_validation": cfg["training"]["nested_penalty_selection"],
        "penalty_grid": list(fm.PENALTY_GRID),
        "scoring": "exact set log loss; d_t = logP_model - logP_uniform",
        "candidate_pool_sizes": list(POOL_SIZES),
        "predictive_gate": cfg["predictive_gate"]["conditions"],
        "e_gates": {"model": E_GATE, "mixture": E_MIX_GATE},
        "n_predictions_by_regime": {
            sid: len(reg_rows[sid]["F-M004"]) for sid in reg_rows},
        "output_hashes": hashes,
        "control_pass": control_pass,
        "software": {"python": platform.python_version(),
                     "numpy": np.__version__},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                   time.gmtime()),
    }
    (OUT / "phase4a_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    print(f"all outputs written ({time.time()-t0:.0f}s)", flush=True)
    for g in gate_rows:
        print(f"{g['model_id']}: gate {g['gate']} "
              f"(cum_d={sum(float(r['d_main']) for r in pooled[g['model_id']]['rows']):.3f})")


if __name__ == "__main__":
    main()
