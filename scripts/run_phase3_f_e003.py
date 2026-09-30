"""Execute F-E003 — corrected Phase 3 historical deviation reanalysis.

Identical scientific design to F-E002 (frozen statistic definitions,
tails, replicates, RNG, multiplicity rules, promotion rule), run on the
D-007/D-008 corrected Phase 1 dataset and the v2 corrected split:

  - exploration = original F-E002 exploration IDs INTERSECT corrected
    analysis-eligible canonical draws (metadata/phase3_exploration_ids_v2.csv)
  - holdout = the FROZEN original F-E002 holdout IDs, verified against
    the v2 seal (metadata/phase3_holdout_seal_v2.json)

Differences from F-E002 are ONLY in artifact handling (D-008): the
prohibited heuristic "two consecutive identical sets => phantom, adjust
the statistic" is removed. Corrupt records were excluded upstream via
metadata/draw_exclusions.csv on independent schedule/source evidence;
statistics are then computed normally on the corrected data. Any
qualifying flag is promoted unless an independently documented
exclusion-ledger row or verifier-recorded artifact resolves it -
statistical rarity alone never adjudicates.

P3-S011 consumes only canonical records labeled physical_draw_order
with atomic sequence provenance (number_sequence_source_id names the
source that supplied the stored sequence); the exploration loader
enforces this structurally.

Outputs go to data/analysis/phase3_corrected/ — F-E002 outputs are
immutable and untouched. Holdout outcomes are never parsed.
"""

import csv
import hashlib
import json
import math
import subprocess
import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fortuna.analysis import montecarlo_p3, order, secondary
from fortuna.analysis.loader import load_exploration_histories
from fortuna.analysis.split import holdout_seal_sha256
from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.regimes import GameRegime
from fortuna.simulation import convergence, exact
from fortuna.simulation.matrix import statistical_matrices
from fortuna.simulation.seeding import make_rng
from fortuna.simulation.statistics import (
    CATALOG,
    applicable_statistics,
    history_statistics,
)
from fortuna.simulation.structural import structural_exact, structural_simulated
from fortuna.statistics.multiple_testing import benjamini_hochberg, holm
from fortuna.statistics.pvalues import mc_pvalue

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config/experiments/F-E003.yaml"
DRAWS = ROOT / "data/processed/draws.csv"
DRAWNUMS = ROOT / "data/processed/draw_numbers.csv"
META = ROOT / "metadata"
OUT = ROOT / "data/analysis/phase3_corrected"
MANIFEST = "phase3_corrected_manifest.json"

EXPL_PATH = META / "phase3_exploration_ids_v2.csv"
HOLD_PATH = META / "phase3_holdout_ids.csv"          # frozen F-E002 IDs
SEAL_PATH = META / "phase3_holdout_seal_v2.json"
SUMMARY_PATH = META / "phase3_split_summary_v2.csv"
EXCLUSIONS_PATH = META / "draw_exclusions.csv"
PREREG = ("research/preregistrations/"
          "F-E003-phase3-corrected-reanalysis.md")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _write_csv(
    path: Path, rows: list[dict], fieldnames: list[str] | None = None
) -> None:
    fields = fieldnames or (list(rows[0]) if rows else None)
    if fields is None:
        raise ValueError(f"{path.name}: no rows and no fieldnames")
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _reference_pmfs(matrix, root_seed: int, exp_id: str, n_ref: int):
    """Exact where tractable; deterministic simulated reference otherwise."""
    refs = structural_exact(matrix)
    rng = make_rng(
        root_seed, exp_id,
        f"{matrix.game_id}|{matrix.statistical_regime_id}|STRUCTREF",
    )
    refs.update(structural_simulated(rng, matrix, n_ref))
    return refs


def main() -> int:
    t0 = time.time()
    cfg = yaml.safe_load(CONFIG.read_text())
    exp_id = cfg["experiment_id"]
    assert exp_id == "F-E003"
    root_seed = int(cfg["rng"]["root_seed"])
    mc = cfg["monte_carlo"]
    batches, reps = int(mc["batches"]), int(mc["replicates_per_batch"])
    sec_cfg = cfg["secondary"]

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

    # v2 seal re-verification: same frozen IDs, corrected canonical rows
    seal_now = holdout_seal_sha256(DRAWS, hold_ids)
    assert seal_now == seal_doc["holdout_seal_sha256"], "HOLDOUT SEAL BROKEN"
    # v1 seal preserved as the immutable historical record
    v1_doc = json.loads((META / "phase3_holdout_seal.json").read_text())
    assert v1_doc["holdout_seal_sha256"] == (
        "6cb7c382924c4ad55ab0958239cb488cd95b0e0b99407ebebcfe822a4b16b91c"
    )

    with SUMMARY_PATH.open(newline="") as f:
        split_rows = {r["statistical_regime_id"]: r for r in csv.DictReader(f)}

    # Exclusion ledger — the ONLY basis for artifact adjudication.
    with EXCLUSIONS_PATH.open(newline="") as f:
        exclusions = [
            r for r in csv.DictReader(f)
            if r["decision_status"] == "excluded"
        ]
    excl_ids = {r["draw_id"] for r in exclusions}
    assert not (excl_ids & expl_ids), "excluded draw leaked into exploration"
    assert not (excl_ids & hold_ids), "excluded draw inside frozen holdout"

    tails = cfg["primary"]["tails"]
    lags = tuple(sec_cfg["lagged_overlap"]["lags"])
    windows = tuple(sec_cfg["rolling_scan"]["windows"])

    # ---------------- Monte Carlo null (exploration-matched) -------------
    null = {}          # (stat_regime, stat_id) -> pooled replicates
    batch_map = {}     # (stat_regime, stat_id) -> [batch arrays]
    conv_status = {}
    ref_pmfs = {}      # sid -> quantity-name -> reference pmf
    overlap_mv = {}    # sid -> (mean, var) of exact overlap pmf
    for sid in sorted(matrices):
        m = matrices[sid]
        srow = split_rows[sid]
        seg_lengths = [
            int(x) for x in srow["exploration_segment_lengths"].split(";")
        ]
        n = sum(seg_lengths)
        refs = _reference_pmfs(
            m, root_seed, exp_id, mc["structural_reference_draws"]
        )
        ref_pmfs[sid] = refs
        ov = exact.overlap_pmf(m.main_pool, m.main_count)
        ov_x = np.arange(len(ov))
        ov_mu = float((ov_x * ov).sum())
        ov_var = float(((ov_x - ov_mu) ** 2 * ov).sum())
        overlap_mv[sid] = (ov_mu, ov_var)
        res = montecarlo_p3.run_regime_p3(
            m, n, seg_lengths, root_seed, exp_id, batches, reps,
            lags, ov_mu, ov_var, windows, refs,
        )
        for stat_id, barr in res.items():
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

    # ---------------- observed exploration outcomes --------------------
    histories = load_exploration_histories(DRAWS, DRAWNUMS, expl_ids, stat_of)

    num_rows, spec_rows, pair_rows = [], [], []
    triple_rows, serial_rows, struct_obs_rows = [], [], []
    order_rows = []
    equip_suff_rows, equip_rows = [], []
    obs_stats = {}
    equip_results = {}

    for sid in sorted(matrices):
        m = matrices[sid]
        srow = split_rows[sid]
        seg_lengths = [
            int(x) for x in srow["exploration_segment_lengths"].split(";")
        ]
        h = histories[sid]
        n = len(h.draws)
        assert n == sum(seg_lengths), f"{sid}: exploration count mismatch"
        mains = np.array([d.mains for d in h.draws], dtype=np.int64)
        specials = (
            np.array([d.special for d in h.draws], dtype=np.int64)
            if m.has_special else None
        )
        mains0 = mains - m.main_min

        # ----- observed primary statistics -----
        stats = history_statistics(mains, specials, m, seg_lengths)
        obs_stats.update({(sid, k): v for k, v in stats.items()})

        # ----- number / special frequency diagnostics -----
        k_, npool = m.main_count, m.main_pool
        c = np.bincount(mains0.ravel(), minlength=npool)
        mu = n * k_ / npool
        for ball in range(npool):
            obs = int(c[ball])
            z = (obs - mu) / math.sqrt(mu * (1 - k_ / npool))
            num_rows.append({
                "statistical_regime_id": sid, "number": ball + m.main_min,
                "observed_count": obs, "expected_count": mu,
                "count_residual": obs - mu, "standardized_residual": z,
                "observed_proportion": obs / n,
                "expected_inclusion_prob": k_ / npool,
            })
        if m.has_special and specials is not None:
            sp0 = specials - m.special_min
            sc = np.bincount(sp0, minlength=m.special_pool)
            smu = n / m.special_pool
            for ball in range(m.special_pool):
                obs = int(sc[ball])
                z = (obs - smu) / math.sqrt(smu * (1 - 1 / m.special_pool))
                spec_rows.append({
                    "statistical_regime_id": sid,
                    "special_ball": ball + m.special_min,
                    "observed_count": obs, "expected_count": smu,
                    "count_residual": obs - smu, "standardized_residual": z,
                    "observed_proportion": obs / n,
                    "expected_inclusion_prob": 1 / m.special_pool,
                })

        # ----- pair counts for EVERY pair (lexicographic) -----
        pair_expect = n * exact.pair_prob(npool, k_)
        cols = [
            mains0[:, i] * npool + mains0[:, j]
            for i, j in combinations(range(k_), 2)
        ]
        pids = np.bincount(
            np.concatenate(cols), minlength=npool * npool
        )
        for a in range(npool):
            base = a * npool
            for b in range(a + 1, npool):
                pair_rows.append({
                    "statistical_regime_id": sid,
                    "ball_a": a + m.main_min, "ball_b": b + m.main_min,
                    "observed_count": int(pids[base + b]),
                    "expected_count": pair_expect,
                })

        # ----- triple maximum drill-down -----
        mx, trips = secondary.argmax_triples(mains0, npool)
        for t in trips:
            triple_rows.append({
                "statistical_regime_id": sid, "max_triple_count": mx,
                "ball_a": t[0], "ball_b": t[1], "ball_c": t[2],
            })

        # ----- serial diagnostics -----
        ov_mu, ov_var = overlap_mv[sid]
        lag_res = secondary.lagged_overlap_scan(
            mains0, seg_lengths, lags, ov_mu, ov_var
        )
        for lag, v in lag_res.items():
            serial_rows.append({
                "statistical_regime_id": sid, "record": "P3-S002",
                "lag": lag, "label": "",
                "aggregate": v["aggregate"], "n_pairs": v["n_pairs"],
                "z": v["z"],
            })
        mem = np.zeros((n, npool), dtype=bool)
        np.put_along_axis(mem, mains0, True, axis=1)
        trailing = secondary.terminal_drought_by_ball(mem, seg_lengths)
        for ball in range(npool):
            serial_rows.append({
                "statistical_regime_id": sid, "record": "P3-S003",
                "lag": "", "label": ball + m.main_min,
                "aggregate": float(trailing[ball]), "n_pairs": "",
                "z": "",
            })

        # ----- observed secondary stats -----
        sec_obs = secondary.p3_history_statistics(
            mains, m, seg_lengths, lags, ov_mu, ov_var, windows,
            ref_pmfs[sid],
        )
        obs_stats.update({(sid, k): v for k, v in sec_obs.items()})

        for p3id, qname in secondary.STRUCTURAL_TESTS.items():
            struct_obs_rows.append({
                "statistical_regime_id": sid, "statistic_id": p3id,
                "quantity": qname, "observed_T": sec_obs[p3id],
                "ref_method": (
                    "exact" if qname
                    in ("draw_sum", "range", "odd_count") else "simulated"
                ),
            })

        # ----- P3-S011 physical order (atomic-provenance rows only) -----
        ordered_ids = sorted(h.physical_order)
        n_ord = len(ordered_ids)
        pos_cfg = sec_cfg["physical_order"]
        if n_ord >= pos_cfg["min_order_draws"]:
            ordered = np.array(
                [h.physical_order[d] for d in ordered_ids], dtype=np.int64
            )
            obs_val = order.position_omnibus(ordered - m.main_min, npool)
            null_rep = order.order_null_replicates(
                m, n_ord, root_seed, exp_id, batches, reps
            )
            pooled_ord = np.concatenate(null_rep)
            obs_stats[(sid, "P3-S011")] = obs_val
            null[(sid, "P3-S011")] = pooled_ord
            batch_map[(sid, "P3-S011")] = null_rep
            conv_status[(sid, "P3-S011")] = "NOT APPLICABLE"
            order_rows.append({
                "statistical_regime_id": sid, "n_ordered_draws": n_ord,
                "status": "RUN", "observed": obs_val,
                "null_mean": float(pooled_ord.mean()),
                "null_sd": float(pooled_ord.std()),
                "z": float(
                    (obs_val - pooled_ord.mean())
                    / max(pooled_ord.std(), 1e-12)
                ),
            })
        else:
            order_rows.append({
                "statistical_regime_id": sid, "n_ordered_draws": n_ord,
                "status": "INSUFFICIENT_DATA", "observed": "",
                "null_mean": "", "null_sd": "", "z": "",
            })

        # ----- P3-S012 equipment -----
        eq_cfg = sec_cfg["equipment"]
        for fld in eq_cfg["fields"]:
            labs_all = [getattr(d, fld) for d in h.draws]
            suff = order.equipment_sufficiency(
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
            keep = np.array(
                [lab in suff["included"] for lab in labs_all]
            )
            sel_m0 = mains0[keep]
            sel_lab = np.array(
                [lab for lab, k2 in zip(labs_all, keep, strict=True) if k2]
            )
            years = np.array(
                [d.draw_date[:4] for d, k2 in
                 zip(h.draws, keep, strict=True) if k2]
            )
            t_obs = order.equipment_chi2(sel_m0, sel_lab, npool, k_)
            n_perm = int(mc["equipment_permutations"])
            rng_eq = make_rng(
                root_seed, exp_id,
                f"{m.game_id}|{m.statistical_regime_id}|EQUIP|{fld}",
            )
            null_perm = order.equipment_permutation_null(
                sel_m0, sel_lab, years, npool, k_, rng_eq, n_perm
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
                "perm_mean": float(null_perm.mean()),
                "perm_sd": sd, "z": z, "raw_p": p,
                "n_permutations": n_perm,
            })
        print(f"  {sid} observed done ({time.time()-t0:.0f}s)", flush=True)

    # ---------------- p-values + multiplicity ---------------------------
    prim_p_rows = []
    sec_p_rows = []
    prim_pvals, prim_keys = [], []
    for sid in sorted(matrices):
        m = matrices[sid]
        for stat_id in applicable_statistics(m):
            obs = obs_stats[(sid, stat_id)]
            vals = null[(sid, stat_id)]
            p = mc_pvalue(obs, vals, tails[stat_id])
            z = (obs - vals.mean()) / max(vals.std(), 1e-12)
            prim_keys.append((sid, stat_id))
            prim_pvals.append(p)
            prim_p_rows.append({
                "statistical_regime_id": sid, "statistic_id": stat_id,
                "statistic": CATALOG[stat_id].name,
                "observed": obs,
                "null_mean": float(vals.mean()),
                "null_sd": float(vals.std()),
                "null_min": float(vals.min()),
                "null_max": float(vals.max()),
                "se_mean": float(vals.std(ddof=1) / math.sqrt(vals.size)),
                "empirical_percentile": float((vals <= obs).mean()),
                "z": z, "tail": tails[stat_id], "raw_p": p,
                "mc_resolution": vals.size + 1,
                "convergence_status": conv_status[(sid, stat_id)],
            })
    bh = benjamini_hochberg(
        np.array(prim_pvals), alpha=cfg["primary"]["family_bh_q"]
    )
    hm = holm(np.array(prim_pvals), alpha=cfg["primary"]["family_holm_alpha"])
    for i, row in enumerate(prim_p_rows):
        row["bh_q"] = float(bh["adjusted"][i])
        row["holm_p"] = float(hm["adjusted"][i])
        row["bh_flag"] = bool(bh["rejected"][i])

    sec_keys, sec_pvals = [], []
    sec_lookup = {}
    for sid in sorted(matrices):
        for stat_id in secondary.HISTORY_SECONDARY:
            obs = obs_stats[(sid, stat_id)]
            vals = null[(sid, stat_id)]
            p = mc_pvalue(obs, vals, "upper")
            z = (obs - vals.mean()) / max(vals.std(), 1e-12)
            sec_keys.append((sid, stat_id))
            sec_pvals.append(p)
            sec_lookup[(sid, stat_id)] = {
                "statistical_regime_id": sid, "statistic_id": stat_id,
                "method": "monte_carlo", "observed": obs,
                "null_mean": float(vals.mean()),
                "null_sd": float(vals.std()),
                "z": z, "tail": "upper", "raw_p": p,
                "n_replicates": vals.size,
            }
        if (sid, "P3-S011") in obs_stats:
            obs = obs_stats[(sid, "P3-S011")]
            vals = null[(sid, "P3-S011")]
            p = mc_pvalue(obs, vals, "upper")
            z = (obs - vals.mean()) / max(vals.std(), 1e-12)
            sec_keys.append((sid, "P3-S011"))
            sec_pvals.append(p)
            sec_lookup[(sid, "P3-S011")] = {
                "statistical_regime_id": sid, "statistic_id": "P3-S011",
                "method": "monte_carlo", "observed": obs,
                "null_mean": float(vals.mean()),
                "null_sd": float(vals.std()),
                "z": z, "tail": "upper", "raw_p": p,
                "n_replicates": vals.size,
            }
        for fld in sec_cfg["equipment"]["fields"]:
            key = (sid, f"P3-S012:{fld}")
            if (sid, fld) in equip_results:
                r = equip_results[(sid, fld)]
                sec_keys.append(key)
                sec_pvals.append(r["p"])
                sec_lookup[key] = {
                    "statistical_regime_id": sid,
                    "statistic_id": f"P3-S012:{fld}",
                    "method": "permutation_year_blocked",
                    "observed": r["observed"],
                    "null_mean": float(r["null"].mean()),
                    "null_sd": float(r["null"].std()),
                    "z": r["z"], "tail": "upper", "raw_p": r["p"],
                    "n_replicates": r["null"].size,
                }
    sec_bh = benjamini_hochberg(
        np.array(sec_pvals), alpha=sec_cfg["family_bh_q"]
    )
    sec_hm = holm(
        np.array(sec_pvals), alpha=sec_cfg["family_holm_alpha"]
    )
    for i, key in enumerate(sec_keys):
        row = sec_lookup[key]
        row["bh_q"] = float(sec_bh["adjusted"][i])
        row["holm_p"] = float(sec_hm["adjusted"][i])
        row["bh_flag"] = bool(sec_bh["rejected"][i])
        sec_p_rows.append(row)

    # ---------------- artifact documentation (D-008) --------------------
    # No heuristic adjudication here. The diagnostics file records the
    # exclusion ledger applied upstream and a DESCRIPTIVE integrity scan.
    # A qualifying flag can be withheld from promotion only by independent
    # documented evidence (ledger row or recorded decision) - never by
    # rarity under the null.
    artifact_rows = []
    artifact_explained: dict[tuple[str, str], str] = {}
    for r in exclusions:
        artifact_rows.append({
            "artifact": "upstream_exclusion",
            "statistical_regime_id": "",
            "detail": (
                f"{r['draw_id']} ({r['game_id']} {r['draw_date']}) "
                f"excluded upstream per ledger {r['exclusion_id']} "
                f"[{r['reason_code']}; {r['decision_id']}]: "
                f"{r['evidence'][:180]}"
            ),
            "affected_statistics": "upstream_data",
        })
    # descriptive integrity scans - informational only, zero adjudicative
    # force
    for sid in sorted(matrices):
        h = histories[sid]
        m = matrices[sid]
        ords = np.array(
            [h.physical_order[d] for d in sorted(h.physical_order)]
        ) if h.physical_order else np.empty((0, m.main_count), dtype=int)
        if len(ords):
            frac = float(
                (np.diff(ords, axis=1) > 0).all(axis=1).mean()
            )
            artifact_rows.append({
                "artifact": "descriptive_scan",
                "statistical_regime_id": sid,
                "detail": (
                    f"physical-order population n={len(ords)}, "
                    f"{frac:.1%} literally ascending (post-audit "
                    "provenance; ascending rows carry unknown_order, "
                    "not physical_draw_order)"
                ),
                "affected_statistics": "P3-S011",
            })
        dup = sum(
            1
            for i in range(1, len(h.draws))
            if h.draws[i].mains == h.draws[i - 1].mains
        )
        artifact_rows.append({
            "artifact": "descriptive_scan",
            "statistical_regime_id": sid,
            "detail": (
                f"consecutive identical main sets in corrected "
                f"exploration: {dup} (descriptive only; identical sets "
                "alone cannot establish artifact status)"
            ),
            "affected_statistics": "F-S006,P3-S002",
        })

    qualifying = []
    for row in prim_p_rows + sec_p_rows:
        if row["bh_flag"] and abs(row["z"]) >= cfg["promotion"]["abs_z_min"]:
            qualifying.append(row)

    for row in qualifying:
        sid, stat_id = row["statistical_regime_id"], row["statistic_id"]
        key = (sid, stat_id.split(":")[0])
        # artifact_explained stays empty unless a documented exclusion/
        # decision resolves the flag; no automatic adjustment exists.
        if key in artifact_explained:
            detail = (
                f"{stat_id} BH-flagged (z={row['z']:.2f}, "
                f"q={row['bh_q']:.4f}) -> EXPLAINED by "
                f"{artifact_explained[key]}"
            )
        else:
            detail = (
                f"{stat_id} BH-flagged (z={row['z']:.2f}, "
                f"q={row['bh_q']:.4f}) -> promoted to candidate"
            )
        artifact_rows.append({
            "artifact": "flag_adjudication",
            "statistical_regime_id": sid,
            "detail": detail,
            "affected_statistics": stat_id,
        })

    # ---------------- candidate hypotheses ------------------------------
    hyp_rows = []
    candidates = [
        (row["statistical_regime_id"], row["statistic_id"], row)
        for row in qualifying
        if (row["statistical_regime_id"], row["statistic_id"].split(":")[0])
        not in artifact_explained
    ]
    for j, (sid, stat_id, row) in enumerate(candidates, 1):
        srow = split_rows[sid]
        hyp_rows.append({
            "hypothesis_id": f"F-H{j:03d}",
            "date": time.strftime("%Y-%m-%d", time.gmtime()),
            "source_experiment": exp_id,
            "status": "candidate_for_confirmation",
            "game": matrices[sid].game_id,
            "statistical_regime": sid,
            "exploration_interval": (
                f"<= {srow['exploration_end_date']}"
            ),
            "observed_phenomenon": (
                f"{stat_id} observed={row['observed']:.6g} vs null mean "
                f"{row['null_mean']:.6g} (sd {row['null_sd']:.3g})"
            ),
            "direction": row["tail"],
            "test_statistic": stat_id,
            "effect_size_z": row["z"],
            "raw_p": row["raw_p"],
            "adjusted_q": row["bh_q"],
            "mechanistic_rationale": "none identified a priori",
            "alternative_explanations": (
                "chance; multiple-testing noise; source/recording "
                "artifact; regime artifact; physical/mechanical signal"
            ),
            "confirmatory_test": (
                "identical statistic on untouched frozen holdout of the "
                "same statistical regime"
            ),
            "holdout_population_reserved": (
                f"{srow['holdout_count']} draws "
                f"{srow['holdout_start_date']}..end"
            ),
            "min_confirmation_effect": "|z| >= 2.5 with one-sided p<=0.05",
            "failure_criterion": (
                "confirmatory p > 0.05 or effect reverses direction"
            ),
        })

    # ---------------- outputs -------------------------------------------
    OUT.mkdir(parents=True, exist_ok=True)
    _write_csv(
        OUT / "phase3_primary_statistics.csv",
        [{k: r[k] for k in (
            "statistical_regime_id", "statistic_id", "statistic",
            "observed", "null_mean", "null_sd", "null_min", "null_max",
            "se_mean", "empirical_percentile", "z",
            "convergence_status")}
         for r in prim_p_rows],
    )
    _write_csv(
        OUT / "phase3_primary_pvalues.csv",
        [{k: r[k] for k in (
            "statistical_regime_id", "statistic_id", "observed",
            "null_mean", "null_sd", "z", "empirical_percentile",
            "tail", "raw_p", "bh_q", "holm_p", "mc_resolution",
            "convergence_status", "bh_flag")}
         for r in prim_p_rows],
    )
    _write_csv(OUT / "phase3_number_frequency_diagnostics.csv", num_rows)
    _write_csv(OUT / "phase3_special_frequency_diagnostics.csv", spec_rows)
    _write_csv(OUT / "phase3_pair_counts.csv", pair_rows)
    _write_csv(OUT / "phase3_triple_diagnostics.csv", triple_rows)
    _write_csv(OUT / "phase3_serial_diagnostics.csv", serial_rows)
    _write_csv(OUT / "phase3_structural_diagnostics.csv", struct_obs_rows)
    _write_csv(OUT / "phase3_order_diagnostics.csv", order_rows)
    _write_csv(OUT / "phase3_equipment_sufficiency.csv", equip_suff_rows)
    _write_csv(OUT / "phase3_equipment_diagnostics.csv", equip_rows)
    _write_csv(OUT / "phase3_secondary_pvalues.csv", sec_p_rows)
    _write_csv(
        OUT / "phase3_artifact_diagnostics.csv", artifact_rows,
        fieldnames=[
            "artifact", "statistical_regime_id", "detail",
            "affected_statistics",
        ],
    )
    _write_csv(
        OUT / "phase3_candidate_hypotheses.csv", hyp_rows,
        fieldnames=[
            "hypothesis_id", "date", "source_experiment", "status",
            "game", "statistical_regime", "exploration_interval",
            "observed_phenomenon", "direction", "test_statistic",
            "effect_size_z", "raw_p", "adjusted_q",
            "mechanistic_rationale", "alternative_explanations",
            "confirmatory_test", "holdout_population_reserved",
            "min_confirmation_effect", "failure_criterion",
        ],
    )

    prereg_commit = _git([
        "log", "--diff-filter=A", "--format=%H", "--", PREREG,
    ]).splitlines()[-1]

    outputs = sorted(p for p in OUT.iterdir() if p.name != MANIFEST)
    manifest = {
        "phase": 3,
        "experiment_id": exp_id,
        "corrects": "F-E002 (immutable; see D-006/D-007/D-008)",
        "phase3_preregistration_commit": prereg_commit,
        "analysis_code_commit": _git(["rev-parse", "HEAD"]),
        "accepted_phase1_dataset_sha256": dataset_sha,
        "accepted_phase2_commit": cfg["accepted_phase2_commit"],
        "observation_plan_sha256": cfg.get("observation_plan_sha256"),
        "corrected_exploration_manifest_sha256":
            seal_doc["corrected_exploration_manifest_sha256"],
        "holdout_manifest_sha256": seal_doc["holdout_manifest_sha256"],
        "holdout_seal_sha256_v1": v1_doc["holdout_seal_sha256"],
        "holdout_seal_sha256_v2": seal_doc["holdout_seal_sha256"],
        "holdout_population": "frozen original F-E002 IDs",
        "exploration_counts":
            {s["statistical_regime_id"]: int(s["exploration_count"])
             for s in split_rows.values()},
        "exploration_removed_counts":
            {s["statistical_regime_id"]:
             int(s["exploration_removed_count"])
             for s in split_rows.values()},
        "holdout_counts":
            {s["statistical_regime_id"]: int(s["holdout_count"])
             for s in split_rows.values()},
        "exploration_segment_lengths":
            {s["statistical_regime_id"]:
             [int(x) for x in s["exploration_segment_lengths"].split(";")]
             for s in split_rows.values()},
        "exclusion_ledger": "metadata/draw_exclusions.csv",
        "excluded_draw_ids": sorted(excl_ids),
        "root_seed": root_seed,
        "rng_algorithm": cfg["rng"]["algorithm"],
        "primary_replicates": mc["replicates_per_statistic_regime"],
        "secondary_replicates": mc["replicates_per_statistic_regime"],
        "equipment_permutations": mc["equipment_permutations"],
        "primary_family": "F-S001..F-S013 applicable x 16 regimes (202)",
        "secondary_family":
            "P3-S001..S012 applicable across regimes (one family)",
        "bh_threshold": cfg["primary"]["family_bh_q"],
        "holm_threshold": cfg["primary"]["family_holm_alpha"],
        "effect_size_threshold": cfg["promotion"]["abs_z_min"],
        "candidate_hypotheses": len(hyp_rows),
        "flags_artifact_explained": len(artifact_explained),
        "convergence_status": (
            "NOT CONVERGED" if any(
                v == "NOT CONVERGED" for v in conv_status.values()
            ) else "CONVERGED"
        ),
        "output_hashes": {p.name: _sha256(p) for p in outputs},
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (OUT / MANIFEST).write_text(json.dumps(manifest, indent=2))
    print(
        f"manifest written; candidate hypotheses: {len(hyp_rows)} "
        f"({time.time()-t0:.0f}s total)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
