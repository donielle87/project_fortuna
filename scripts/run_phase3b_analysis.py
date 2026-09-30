"""Execute F-E004 — Phase 3B physical draw-sequence / positional
dependence exploration.

Scientific design is frozen in config/experiments/F-E004.yaml and the
F-E004 preregistration (committed BEFORE any positional outcome
statistic was computed). The analysis consumes only corrected
exploration draws whose canonical records carry physical_draw_order
semantics WITH atomic sequence provenance (number_sequence_source_id
names the staged source that supplied the stored sequence) — enforced
structurally by the exploration loader. Sorted/unknown-order rows are
never substituted; a non-physical row breaks physical-order contiguity
for all serial statistics.

Null model: FAIR SEQUENTIAL WITHOUT-REPLACEMENT ordered draws (uniform
ordered K-permutations via draw_mains_ordered), never an
independent-position null. 20,000 replicate ordered histories per
qualifying regime in 4 deterministic batches, shared across all P3B
statistics within the regime.

Holdout: the frozen 2,072-draw holdout is untouched — the loader drops
non-exploration rows before any outcome field is parsed.

Outputs: data/analysis/phase3b/.
"""

import csv
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.analysis import montecarlo_p3b, positional, positional_synth
from fortuna.analysis.loader import (
    load_exploration_draws,
    load_exploration_physical_order,
)
from fortuna.analysis.order import equipment_sufficiency
from fortuna.analysis.split import (
    exploration_segments,
    holdout_seal_sha256,
)
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime
from fortuna.simulation import convergence
from fortuna.simulation.matrix import statistical_matrices
from fortuna.simulation.observation import load_draw_metadata
from fortuna.simulation.seeding import make_rng
from fortuna.statistics.multiple_testing import benjamini_hochberg, holm
from fortuna.statistics.pvalues import mc_pvalue

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config/experiments/F-E004.yaml"
DRAWS = ROOT / "data/processed/draws.csv"
DRAWNUMS = ROOT / "data/processed/draw_numbers.csv"
META = ROOT / "metadata"
OUT = ROOT / "data/analysis/phase3b"
MANIFEST = "phase3b_manifest.json"

EXPL_PATH = META / "phase3_exploration_ids_v2.csv"
HOLD_PATH = META / "phase3_holdout_ids.csv"
SEAL_PATH = META / "phase3_holdout_seal_v2.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _stat_fn(stat_id: str):
    """(ord_history, matrix, seg_lengths) -> stat for sensitivity runs."""
    return {
        "P3B-S001": lambda h, m, s: positional.p3b_s001(h, m.main_pool),
        "P3B-S002": lambda h, m, s: positional.p3b_s002(h, m.main_pool),
        "P3B-S003": lambda h, m, s: positional.p3b_s003(h, m.main_pool),
        "P3B-S004": lambda h, m, s: positional.p3b_s004(h, m.main_pool),
        "P3B-S005": lambda h, m, s: positional.p3b_s005(h, m.main_pool),
        "P3B-S006": lambda h, m, s: positional.p3b_s006(h, m.main_pool),
        "P3B-S007": lambda h, m, s: positional.p3b_s007(
            h, m.main_pool, s, LAGS_SAME
        ),
        "P3B-S008": lambda h, m, s: positional.p3b_s008(
            h, m.main_pool, s, LAGS_CROSS
        ),
        "P3B-S009": lambda h, m, s: positional.p3b_s009(
            h, m.main_pool, s, WINDOWS
        ),
    }[stat_id]


LAGS_SAME: tuple[int, ...] = ()
LAGS_CROSS: tuple[int, ...] = ()
WINDOWS: tuple[int, ...] = ()


def _write_csv(
    path: Path, rows: list[dict], fieldnames: list[str] | None = None
) -> str:
    fields = fieldnames or (list(rows[0]) if rows else None)
    if fields is None:
        raise ValueError(f"{path.name}: no rows and no fieldnames")
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return _sha256(path)


def main() -> int:
    t0 = time.time()
    cfg = yaml.safe_load(CONFIG.read_text())
    exp_id = cfg["experiment_id"]
    assert exp_id == "F-E004"
    root_seed = int(cfg["rng"]["root_seed"])
    mc = cfg["monte_carlo"]
    batches, reps = int(mc["batches"]), int(mc["replicates_per_batch"])
    elig = cfg["eligibility"]
    min_n = int(elig["min_physical_order_draws"])
    lags_same = tuple(cfg["statistics"]["lags_same_position"])
    lags_cross = tuple(cfg["statistics"]["lags_cross_position"])
    windows = tuple(cfg["statistics"]["rolling_windows"])
    global LAGS_SAME, LAGS_CROSS, WINDOWS
    LAGS_SAME, LAGS_CROSS, WINDOWS = lags_same, lags_cross, windows
    eq_cfg = cfg["equipment"]
    sens_cfg = cfg["sensitivity"]

    dataset_sha = json.loads(
        (ROOT / "data/processed/dataset_manifest.json").read_text()
    )["dataset_sha256"]
    assert dataset_sha == cfg["accepted_phase1_dataset_sha256"]

    seal_doc = json.loads(SEAL_PATH.read_text())
    assert seal_doc["dataset_sha256"] == dataset_sha
    assert seal_doc["seal_version"] == 2

    regimes = load_csv(META / "game_regimes.csv", GameRegime)
    matrices = statistical_matrices(regimes)
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}

    expl_ids = set()
    with EXPL_PATH.open(newline="") as f:
        for r in csv.DictReader(f):
            expl_ids.add(r["draw_id"])
    hold_ids = set()
    with HOLD_PATH.open(newline="") as f:
        for r in csv.DictReader(f):
            hold_ids.add(r["draw_id"])
    assert not (expl_ids & hold_ids)
    assert holdout_seal_sha256(DRAWS, hold_ids) == seal_doc[
        "holdout_seal_sha256"
    ], "HOLDOUT SEAL BROKEN"
    v1_doc = json.loads((META / "phase3_holdout_seal.json").read_text())
    assert v1_doc["holdout_seal_sha256"] == (
        "6cb7c382924c4ad55ab0958239cb488cd95b0e0b99407ebebcfe822a4b16b91c"
    )

    # -------- physical-order segment structure (metadata only) ----------
    meta = load_draw_metadata(DRAWS)
    order_segments = exploration_segments(
        meta, regimes, stat_of, expl_ids, order_only=True
    )
    phys_draw_ids = {
        r["draw_id"]
        for r in meta
        if r["draw_id"] in expl_ids
        and r.get("numbers_order") == "physical_draw_order"
    }

    # -------- ordered exploration outcomes (firewalled loader) ----------
    draws = {d.draw_id: d for d in load_exploration_draws(DRAWS, expl_ids)}
    physical_order = load_exploration_physical_order(DRAWNUMS, expl_ids)
    assert set(physical_order) == phys_draw_ids, (
        "physical-order outcome rows do not match metadata claims"
    )

    # (stat_regime, draw_date) -> draw_id for physical-order exploration rows
    phys_at: dict[tuple[str, str], str] = {}
    for r in meta:
        if r["draw_id"] in phys_draw_ids:
            sid = stat_of.get(r["regime_id"])
            if sid:
                phys_at[(sid, r["draw_date"])] = r["draw_id"]

    # Per regime: ordered draws arranged segment-by-segment in
    # chronological order; serial stats never bridge a segment break.
    regime_ordered: dict[str, dict] = {}
    suff_rows, seg_rows = [], []
    for sid in sorted(matrices):
        segs = order_segments.get(sid, [])
        seg_lens = [len(s) for s in segs]
        draws_ord = []
        for i, seg in enumerate(segs):
            for d in seg:
                draws_ord.append(phys_at[(sid, d.isoformat())])
            seg_rows.append({
                "statistical_regime_id": sid, "segment_index": i,
                "first_date": seg[0].isoformat(),
                "last_date": seg[-1].isoformat(),
                "segment_length": len(seg),
            })
        n_ord = len(draws_ord)
        qualifying = n_ord >= min_n
        suff_rows.append({
            "statistical_regime_id": sid,
            "physical_order_draws": n_ord,
            "physical_segments": len(segs),
            "physical_segment_lengths": ";".join(map(str, seg_lens)),
            "min_required": min_n,
            "status": "RUN" if qualifying else "INSUFFICIENT_DATA",
        })
        if qualifying:
            regime_ordered[sid] = {
                "draw_ids": draws_ord,
                "seg_lengths": seg_lens,
            }
    print(f"eligibility done ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- Monte Carlo nulls (ordered histories) -------------
    null, batch_map, conv_status = {}, {}, {}
    for sid, ro in regime_ordered.items():
        m = matrices[sid]
        n_ord = len(ro["draw_ids"])
        res = montecarlo_p3b.run_regime_p3b(
            m, n_ord, ro["seg_lengths"], root_seed, exp_id,
            batches, reps, lags_same, lags_cross, windows,
        )
        for stat_id, barr in res.items():
            if stat_id == "P3B-S009" and not positional.s009_applicable(
                ro["seg_lengths"], windows
            ):
                continue
            pooled = np.concatenate(barr)
            null[(sid, stat_id)] = pooled
            batch_map[(sid, stat_id)] = barr
            conv = convergence.check_convergence(
                barr,
                sigma_factor=cfg["convergence"]["sigma_factor"],
                atol_rel=cfg["convergence"]["atol_rel"],
            )
            conv_status[(sid, stat_id)] = conv.status
        print(f"  {sid} null done ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- observed statistics + diagnostics -----------------
    pos_rows, pair_rows = [], []
    serial_rows, temporal_rows = [], []
    equip_suff_rows, equip_rows = [], []
    obs_stats, equip_results = {}, {}

    for sid, ro in regime_ordered.items():
        m = matrices[sid]
        ids, seg_lens = ro["draw_ids"], ro["seg_lengths"]
        n_ord = len(ids)
        ordered = np.array(
            [physical_order[d] for d in ids], dtype=np.int64
        )
        ord0 = ordered - m.main_min
        assert ord0.shape == (n_ord, m.main_count)

        obs_stats.update({
            (sid, k): v for k, v in positional.p3b_mc_statistics(
                ord0, m.main_pool, seg_lens, lags_same, lags_cross, windows
            ).items()
        })
        if not positional.s009_applicable(seg_lens, windows):
            obs_stats.pop((sid, "P3B-S009"), None)

        # ----- descriptive position x ball outputs (sorted, not ranked)
        cmat = positional.position_ball_counts(ord0, m.main_pool)
        zmat = positional.position_residuals(ord0, m.main_pool)
        e = n_ord / m.main_pool
        for j in range(m.main_count):
            for a in range(m.main_pool):
                pos_rows.append({
                    "statistical_regime_id": sid, "position": j + 1,
                    "ball": a + m.main_min,
                    "observed_count": int(cmat[j, a]),
                    "expected_count": e,
                    "standardized_residual": float(zmat[j, a]),
                })

        # ----- ordered-pair diagnostics (lexicographic) -----
        presid = positional.ordered_pair_residuals(ord0, m.main_pool)
        for (j, kk) in sorted(presid):
            z = presid[(j, kk)]
            cnt = positional._pair_counts(
                ord0, [(j, kk)], m.main_pool
            )[0].reshape(m.main_pool, m.main_pool)
            ep = n_ord / (m.main_pool * (m.main_pool - 1))
            for a in range(m.main_pool):
                for b in range(m.main_pool):
                    if a == b:
                        continue
                    pair_rows.append({
                        "statistical_regime_id": sid,
                        "position_j": j + 1, "position_k": kk + 1,
                        "ball_a": a + m.main_min, "ball_b": b + m.main_min,
                        "observed_count": int(cnt[a, b]),
                        "expected_count": ep,
                        "standardized_residual": float(z[a, b]),
                    })

        # ----- serial diagnostics -----
        for (j, lag), v in sorted(
            positional.p3b_s007_components(
                ord0, m.main_pool, seg_lens, lags_same
            ).items()
        ):
            serial_rows.append({
                "statistical_regime_id": sid, "record": "P3B-S007",
                "source_position": j + 1, "dest_position": j + 1,
                "lag": lag, "hits": v["hits"], "n_pairs": v["n_pairs"],
                "z": v["z"],
            })
        for (j, kk, lag), v in sorted(
            positional.p3b_s008_components(
                ord0, m.main_pool, seg_lens, lags_cross
            ).items()
        ):
            serial_rows.append({
                "statistical_regime_id": sid, "record": "P3B-S008",
                "source_position": j + 1, "dest_position": kk + 1,
                "lag": lag, "hits": v["hits"], "n_pairs": v["n_pairs"],
                "z": v["z"],
            })

        # ----- temporal diagnostics -----
        if positional.s009_applicable(seg_lens, windows):
            _, diag = positional.p3b_s009_scan(
                ord0, m.main_pool, seg_lens, windows
            )
            bounds = positional._seg_bounds(seg_lens)
            for row in diag:
                start = row.pop("window_start_index")
                seg_i = next(
                    i for i, (s, e) in enumerate(bounds) if s <= start < e
                )
                row["statistical_regime_id"] = sid
                row["segment_index"] = seg_i
                row["window_start_draw_id"] = ids[start]
                row["ball"] = row.pop("ball_index") + m.main_min
                row["selected_identity_note"] = (
                    "DATA-DERIVED IDENTITY — REQUIRES INDEPENDENT CONFIRMATION"
                )
                temporal_rows.append(row)

        # ----- P3B-S010 equipment x position -----
        eq_ids = ro["draw_ids"]
        for fld in eq_cfg["fields"]:
            labs_all = [draws[d].__getattribute__(fld) for d in eq_ids]
            suff = equipment_sufficiency(
                labs_all, eq_cfg["min_categories"],
                eq_cfg["min_draws_per_category"], eq_cfg["min_total_draws"],
            )
            equip_suff_rows.append({
                "statistical_regime_id": sid, "field": fld,
                "n_populated": suff["n_populated"],
                "n_categories": suff["n_categories"],
                "n_eligible_categories": suff["n_eligible_categories"],
                "n_included_draws": suff["n_included_draws"],
                "categories": json.dumps(suff["categories"]),
                "sufficient": suff["sufficient"],
            })
            if not suff["sufficient"]:
                equip_rows.append({
                    "statistical_regime_id": sid, "field": fld,
                    "status": "INSUFFICIENT_DATA", "observed_T": "",
                    "perm_mean": "", "perm_sd": "", "z": "", "raw_p": "",
                    "n_permutations": "",
                })
                continue
            keep = np.array([lab in suff["included"] for lab in labs_all])
            sel_ord = ord0[keep]
            sel_lab = np.array(
                [lab for lab, k2 in zip(labs_all, keep, strict=True) if k2]
            )
            years = np.array(
                [draws[d].draw_date[:4] for d, k2 in
                 zip(eq_ids, keep, strict=True) if k2]
            )
            t_obs = positional.p3b_s010_chi2(sel_ord, sel_lab, m.main_pool)
            n_perm = int(mc["equipment_permutations"])
            rng_eq = make_rng(
                root_seed, exp_id,
                f"{m.game_id}|{m.statistical_regime_id}|P3B_EQUIP|{fld}",
            )
            null_perm = positional.p3b_s010_permutation_null(
                sel_ord, sel_lab, years, m.main_pool, rng_eq, n_perm
            )
            sd = float(null_perm.std())
            z = (t_obs - null_perm.mean()) / max(sd, 1e-12)
            p = mc_pvalue(t_obs, null_perm, "upper")
            equip_results[(sid, fld)] = {
                "observed": t_obs, "null": null_perm, "z": z, "p": p,
            }
            equip_rows.append({
                "statistical_regime_id": sid, "field": fld,
                "status": "RUN", "observed_T": t_obs,
                "perm_mean": float(null_perm.mean()), "perm_sd": sd,
                "z": z, "raw_p": p, "n_permutations": n_perm,
            })
        print(f"  {sid} observed done ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- p-values + multiplicity ---------------------------
    bh_q = float(cfg["primary"]["family_bh_q"])
    holm_a = float(cfg["primary"]["family_holm_alpha"])
    z_promo = float(cfg["promotion"]["min_abs_z"])

    def _fam_rows(stat_ids, applicable):
        keys, pvals, rows = [], [], []
        for sid in sorted(regime_ordered):
            for stat_id in stat_ids:
                if (sid, stat_id) not in applicable:
                    continue
                obs, vals = obs_stats[(sid, stat_id)], null[(sid, stat_id)]
                p = mc_pvalue(obs, vals, "upper")
                sd = max(vals.std(), 1e-12)
                keys.append((sid, stat_id))
                pvals.append(p)
                rows.append({
                    "statistical_regime_id": sid, "statistic_id": stat_id,
                    "observed": obs, "null_mean": float(vals.mean()),
                    "null_sd": float(vals.std()),
                    "null_min": float(vals.min()),
                    "null_max": float(vals.max()),
                    "se_mean": float(
                        vals.std(ddof=1) / math.sqrt(vals.size)
                    ),
                    "empirical_percentile": float((vals <= obs).mean()),
                    "z": (obs - vals.mean()) / sd, "tail": "upper",
                    "raw_p": p, "mc_resolution": vals.size + 1,
                    "convergence_status": conv_status[(sid, stat_id)],
                })
        bh = benjamini_hochberg(np.array(pvals), alpha=bh_q)
        hm = holm(np.array(pvals), alpha=holm_a)
        for i, row in enumerate(rows):
            row["bh_q"] = float(bh["adjusted"][i])
            row["holm_p"] = float(hm["adjusted"][i])
            row["bh_flag"] = bool(bh["rejected"][i])
        return rows

    prim_rows = _fam_rows(positional.PRIMARY_P3B, obs_stats)
    sec_rows = _fam_rows(
        ("P3B-S005", "P3B-S009"), obs_stats
    )
    for (sid, fld), r in sorted(equip_results.items()):
        sec_rows.append({
            "statistical_regime_id": sid,
            "statistic_id": f"P3B-S010|{fld}",
            "observed": r["observed"],
            "null_mean": float(r["null"].mean()),
            "null_sd": float(r["null"].std()),
            "null_min": float(r["null"].min()),
            "null_max": float(r["null"].max()),
            "se_mean": float(
                r["null"].std(ddof=1) / math.sqrt(r["null"].size)
            ),
            "empirical_percentile": float((r["null"] <= r["observed"]).mean()),
            "z": r["z"], "tail": "upper", "raw_p": r["p"],
            "mc_resolution": r["null"].size + 1,
            "convergence_status": "PERMUTATION",
            "bh_q": "", "holm_p": "", "bh_flag": False,
        })
    # secondary family correction over all secondary p-values (incl S010)
    sec_pvals = np.array(
        [r["raw_p"] for r in sec_rows], dtype=float
    )
    bh2 = benjamini_hochberg(sec_pvals, alpha=bh_q)
    hm2 = holm(sec_pvals, alpha=holm_a)
    for i, row in enumerate(sec_rows):
        row["bh_q"] = float(bh2["adjusted"][i])
        row["holm_p"] = float(hm2["adjusted"][i])
        row["bh_flag"] = bool(bh2["rejected"][i])

    # ---------------- promotion ------------------------------------------
    cand_rows = []
    n_h = 0
    for rows in (prim_rows, sec_rows):
        for r in rows:
            if (
                r["bh_flag"]
                and abs(float(r["z"])) >= z_promo
                and r["convergence_status"] in ("CONVERGED", "PERMUTATION")
            ):
                n_h += 1
                cand_rows.append({
                    "hypothesis_id": f"F-H{n_h:03d}",
                    "source_experiment": exp_id,
                    "status": "candidate_for_confirmation",
                    "statistical_regime_id": r["statistical_regime_id"],
                    "statistic_id": r["statistic_id"],
                    "observed": r["observed"],
                    "null_mean": r["null_mean"], "null_sd": r["null_sd"],
                    "raw_p": r["raw_p"], "bh_q": r["bh_q"],
                    "z": r["z"],
                    "identity_selection_note": (
                        "DATA-DERIVED IDENTITY — REQUIRES INDEPENDENT "
                        "CONFIRMATION"
                    ),
                })

    # ---------------- sensitivity / power study -------------------------
    sens_rows = []
    if sens_cfg["enabled"]:
        n_sens = int(sens_cfg["replicates"])
        crit_alpha = float(sens_cfg["critical_alpha"])
        for sid in sorted(regime_ordered):
            ro = regime_ordered[sid]
            m = matrices[sid]
            for scenario, grid in sens_cfg["scenarios"].items():
                stats_for = positional_synth.SCENARIO_STATS[scenario]
                for eff in grid:
                    rng_s = make_rng(
                        root_seed, exp_id,
                        f"{m.game_id}|{m.statistical_regime_id}"
                        f"|P3B_SENS|{scenario}|{eff}",
                    )
                    vals = {s: [] for s in stats_for}
                    for _ in range(n_sens):
                        h = positional_synth.make_history(
                            rng_s, m, len(ro["draw_ids"]),
                            ro["seg_lengths"], scenario, float(eff),
                        )
                        for s in stats_for:
                            if (sid, s) not in null:
                                continue
                            vals[s].append(_stat_fn(s)(
                                h, m, ro["seg_lengths"]
                            ))
                    for s in stats_for:
                        if (sid, s) not in null:
                            continue
                        crit = float(np.quantile(
                            null[(sid, s)], 1 - crit_alpha
                        ))
                        arr = np.asarray(vals[s])
                        sens_rows.append({
                            "statistical_regime_id": sid,
                            "scenario": scenario, "statistic_id": s,
                            "n_draws": len(ro["draw_ids"]),
                            "injected_effect_size": eff,
                            "replicates": n_sens,
                            "critical_value_alpha": crit_alpha,
                            "critical_value": crit,
                            "power": float((arr >= crit).mean()),
                        })
            print(
                f"  {sid} sensitivity done ({time.time()-t0:.0f}s)",
                flush=True,
            )
        # detection threshold (smallest injected effect with power >=
        # 0.8) is derived from sens_rows at report time.

    # ---------------- outputs -------------------------------------------
    OUT.mkdir(parents=True, exist_ok=True)
    hashes = {}
    hashes["phase3b_regime_sufficiency.csv"] = _write_csv(
        OUT / "phase3b_regime_sufficiency.csv", suff_rows
    )
    hashes["phase3b_physical_segments.csv"] = _write_csv(
        OUT / "phase3b_physical_segments.csv", seg_rows,
        ["statistical_regime_id", "segment_index", "first_date",
         "last_date", "segment_length"],
    )
    hashes["phase3b_position_counts.csv"] = _write_csv(
        OUT / "phase3b_position_counts.csv", pos_rows
    )
    hashes["phase3b_position_residuals.csv"] = _write_csv(
        OUT / "phase3b_position_residuals.csv", pos_rows
    )
    hashes["phase3b_ordered_pair_diagnostics.csv"] = _write_csv(
        OUT / "phase3b_ordered_pair_diagnostics.csv", pair_rows
    )
    hashes["phase3b_serial_diagnostics.csv"] = _write_csv(
        OUT / "phase3b_serial_diagnostics.csv", serial_rows
    )
    hashes["phase3b_temporal_diagnostics.csv"] = _write_csv(
        OUT / "phase3b_temporal_diagnostics.csv", temporal_rows,
        ["statistical_regime_id", "segment_index", "window_length",
         "window_start_draw_id", "position", "ball", "max_abs_z",
         "selected_identity_note"],
    )
    equip_fields = [
        "statistical_regime_id", "field", "status",
        "n_populated", "n_categories", "n_eligible_categories",
        "n_included_draws", "categories", "sufficient",
        "observed_T", "perm_mean", "perm_sd", "z", "raw_p",
        "n_permutations",
    ]
    equip_rows_all = [
        {k: r.get(k, "") for k in equip_fields}
        for r in (equip_suff_rows + equip_rows)
    ]
    hashes["phase3b_equipment_diagnostics.csv"] = _write_csv(
        OUT / "phase3b_equipment_diagnostics.csv",
        equip_rows_all, equip_fields,
    )
    hashes["phase3b_primary_pvalues.csv"] = _write_csv(
        OUT / "phase3b_primary_pvalues.csv", prim_rows
    )
    hashes["phase3b_secondary_pvalues.csv"] = _write_csv(
        OUT / "phase3b_secondary_pvalues.csv", sec_rows
    )
    hashes["phase3b_sensitivity.csv"] = _write_csv(
        OUT / "phase3b_sensitivity.csv", sens_rows
    )
    cand_fields = [
        "hypothesis_id", "source_experiment", "status",
        "statistical_regime_id", "statistic_id", "observed",
        "null_mean", "null_sd", "raw_p", "bh_q", "z",
        "identity_selection_note",
    ]
    if cand_rows:
        hashes["phase3b_candidate_hypotheses.csv"] = _write_csv(
            OUT / "phase3b_candidate_hypotheses.csv", cand_rows, cand_fields
        )
    else:
        p = OUT / "phase3b_candidate_hypotheses.csv"
        with p.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cand_fields)
            w.writeheader()
        hashes["phase3b_candidate_hypotheses.csv"] = _sha256(p)

    prereg_commit = _git(
        ["log", "--format=%H", "-n", "1", "--",
         "research/preregistrations/F-E004-positional-dependence.md"]
    )
    manifest = {
        "phase": "3B",
        "experiment_id": exp_id,
        "classification": "exploratory",
        "phase3b_preregistration_commit": prereg_commit,
        "analysis_code_commit": _git(["rev-parse", "HEAD"]),
        "accepted_phase1_dataset_sha256": dataset_sha,
        "phase2_v4_observation_plan_sha256": cfg[
            "accepted_phase2_plan_sha256"
        ],
        "phase3_corrected_exploration_manifest_sha256": _sha256(EXPL_PATH),
        "holdout_manifest_sha256": _sha256(HOLD_PATH),
        "holdout_seal_v2_sha256": seal_doc["holdout_seal_sha256"],
        "physical_order_draw_counts": {
            sid: len(ro["draw_ids"]) for sid, ro in regime_ordered.items()
        },
        "physical_segment_lengths": {
            sid: ro["seg_lengths"] for sid, ro in regime_ordered.items()
        },
        "min_physical_order_draws": min_n,
        "root_seed": root_seed,
        "rng": cfg["rng"]["algorithm"],
        "monte_carlo": {
            "batches": batches, "replicates_per_batch": reps,
            "equipment_permutations": int(mc["equipment_permutations"]),
        },
        "families": {
            "primary": list(positional.PRIMARY_P3B),
            "secondary": list(positional.SECONDARY_P3B),
        },
        "bh_q": bh_q, "holm_alpha": holm_a,
        "promotion_min_abs_z": z_promo,
        "sensitivity": sens_cfg,
        "output_hashes": hashes,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")

    n_prim = len(prim_rows)
    n_prim_raw = sum(1 for r in prim_rows if r["raw_p"] <= 0.05)
    n_prim_bh = sum(1 for r in prim_rows if r["bh_flag"])
    n_prim_holm = sum(
        1 for r in prim_rows if isinstance(r["holm_p"], float)
        and r["holm_p"] <= holm_a
    )
    n_sec = len(sec_rows)
    n_sec_raw = sum(1 for r in sec_rows if r["raw_p"] <= 0.05)
    n_sec_bh = sum(1 for r in sec_rows if r["bh_flag"])
    n_sec_holm = sum(
        1 for r in sec_rows if isinstance(r["holm_p"], float)
        and r["holm_p"] <= holm_a
    )
    print(f"primary: {n_prim} tests, raw<=.05 {n_prim_raw}, "
          f"BH {n_prim_bh}, Holm {n_prim_holm}")
    print(f"secondary: {n_sec} tests, raw<=.05 {n_sec_raw}, "
          f"BH {n_sec_bh}, Holm {n_sec_holm}")
    print(f"candidate hypotheses: {len(cand_rows)}")
    print(f"F-E004 done ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
