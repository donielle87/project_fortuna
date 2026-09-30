"""F-E005 strict walk-forward engine.

Per statistical regime, draws are processed in chronological order:

1. state/features built from draws < t only;
2. fitted models refit (on draws < t) every REFIT_CADENCE scored draws,
   with L2 penalty chosen by nested chronological inner validation;
3. probabilities for draw t frozen, then scored;
4. outcome applied to state.

Nothing ever uses draws >= t to predict draw t.
"""

import math

import numpy as np

from fortuna.models import fm
from fortuna.models.wsubset import (
    inclusion_probs,
    log_p_subset,
    uniform_log_p,
)

WARMUP = 100
REFIT_CADENCE = 25
POOL_SIZES = (10, 15, 20)


def predict_weights(model_id: str, state: fm.RegimeFeatureState,
                    feats_t: np.ndarray, beta: np.ndarray | None
                    ) -> np.ndarray:
    """Per-ball positive weights for the main draw at time t."""
    n = state.n_pool
    if model_id == "F-M000":
        return fm.weights_m000(n)
    if model_id == "F-M001":
        return fm.weights_m001(state.counts, state.n, n, state.k)
    if model_id == "F-M002":
        return fm.weights_m002(state.ewma[1], state.ewma_mass[1], n,
                               state.k)
    if model_id == "F-M003":
        return np.exp(np.clip(feats_t[:, 3] * beta[0],
                              -fm.SCORE_CLIP, fm.SCORE_CLIP))
    if model_id == "F-M004":
        return np.exp(np.clip(feats_t @ beta, -fm.SCORE_CLIP,
                              fm.SCORE_CLIP))
    raise ValueError(model_id)


def predict_special_probs(model_id: str, state: fm.RegimeFeatureState,
                          feats_sp_t: np.ndarray,
                          beta_sp: np.ndarray | None) -> np.ndarray:
    """Categorical distribution over the special-ball pool at time t."""
    m = state.special_pool
    if model_id == "F-M000":
        return np.full(m, 1.0 / m)
    if model_id == "F-M001":
        return fm.special_probs_shrunk(state.sp_counts, m, 100.0)
    if model_id == "F-M002":
        return fm.special_probs_shrunk(state.sp_ewma[1], m, 25.0)
    if model_id == "F-M003":
        s = np.clip(feats_sp_t[:, 3] * beta_sp[0], -fm.SCORE_CLIP,
                    fm.SCORE_CLIP)
    elif model_id == "F-M004":
        s = np.clip(feats_sp_t @ beta_sp, -fm.SCORE_CLIP, fm.SCORE_CLIP)
    else:
        raise ValueError(model_id)
    s = s - s.max()
    p = np.exp(s)
    return p / p.sum()


def _hypergeom_tail(n_pool: int, m: int, k: int, hits: int) -> float:
    """P(X >= hits) for X ~ Hypergeometric(N=n_pool, m, K=k): drawing
    K winning balls, m pool members."""
    den = math.comb(n_pool, k)
    return sum(
        math.comb(m, h) * math.comb(n_pool - m, k - h)
        for h in range(hits, min(m, k) + 1)
    ) / den


def run_regime_walkforward(
    draws0: np.ndarray, specials0: np.ndarray | None,
    n_pool: int, k: int, special_pool: int, regime_id: str,
    refit_log: list[dict],
) -> dict[str, list[dict]]:
    """Run all five models over one regime's chronological history.

    Returns {model_id: [per-scored-draw result dicts]} plus refit_log
    entries appended in place. draws0 are zero-based sorted labels.
    """
    f_main, f_sp = fm.feature_trajectories(
        draws0, specials0, n_pool, k, special_pool)
    state = fm.RegimeFeatureState(n_pool, k, special_pool)
    logp_unif_main = uniform_log_p(n_pool, k)
    logp_unif_sp = (
        -math.log(special_pool) if special_pool else 0.0
    )

    rows: dict[str, list[dict]] = {m: [] for m in fm.MODEL_IDS}
    params: dict[str, dict] = {
        m: {"beta": None, "beta_sp": None} for m in fm.FITTED_MODELS
    }
    scored_idx = 0
    for t in range(draws0.shape[0]):
        if state.n < WARMUP:
            state.update(draws0[t],
                         None if specials0 is None else
                         int(specials0[t]))
            continue
        # refit on draws < t only
        if scored_idx % REFIT_CADENCE == 0:
            for mid in fm.FITTED_MODELS:
                if mid == "F-M003":
                    fm_x = f_main[:t, :, 3:4]
                    sp_x = (
                        f_sp[:t, :, 3:4] if f_sp is not None else None
                    )
                else:
                    fm_x = f_main[:t]
                    sp_x = f_sp[:t] if f_sp is not None else None
                _lam, beta = fm._nested_penalty(
                    fm_x, draws0[:t], k, False, refit_log,
                    regime_id, scored_idx)
                params[mid]["beta"] = beta
                refit_log[-1]["model_id"] = mid
                refit_log[-1]["target"] = "main"
                if sp_x is not None:
                    _lam_s, beta_sp = fm._nested_penalty(
                        sp_x, specials0[:t], None, True, refit_log,
                        regime_id, scored_idx)
                    params[mid]["beta_sp"] = beta_sp
                    refit_log[-1]["model_id"] = mid
                    refit_log[-1]["target"] = "special"
        feats_t = f_main[t]
        feats_sp_t = f_sp[t] if f_sp is not None else None
        for mid in fm.MODEL_IDS:
            w = predict_weights(mid, state, feats_t,
                                params.get(mid, {}).get("beta"))
            logp_m = float(log_p_subset(
                np.log(w)[None, :], draws0[t][None, :], k)[0])
            inc = inclusion_probs(np.log(w)[None, :], k)[0]
            pool_hits = {}
            for m_pool in POOL_SIZES:
                if m_pool < n_pool:
                    top = np.argpartition(inc, -m_pool)[-m_pool:]
                    pool_hits[m_pool] = int(
                        np.isin(draws0[t], top).sum())
            rec = {
                "draw_index": t, "n_prior": state.n,
                "logp_main_model": logp_m,
                "logp_main_uniform": logp_unif_main,
                "d_main": logp_m - logp_unif_main,
                "pool_hits": pool_hits,
            }
            if feats_sp_t is not None and specials0 is not None:
                bsp = params.get(mid, {}).get("beta_sp")
                sp = predict_special_probs(mid, state, feats_sp_t,
                                           bsp)
                actual_sp = int(specials0[t])
                logp_s = float(np.log(sp[actual_sp]))
                order = np.argsort(-sp, kind="stable")
                rec.update({
                    "logp_special_model": logp_s,
                    "logp_special_uniform": logp_unif_sp,
                    "d_special": logp_s - logp_unif_sp,
                    "d_joint": logp_m - logp_unif_main + logp_s
                               - logp_unif_sp,
                    "sp_prob_actual": float(sp[actual_sp]),
                    "sp_rank_actual": int(
                        np.where(order == actual_sp)[0][0]) + 1,
                    "sp_top5": bool(actual_sp in set(order[:5])),
                })
            else:
                rec.update({
                    "logp_special_model": 0.0,
                    "logp_special_uniform": 0.0,
                    "d_special": 0.0,
                    "d_joint": logp_m - logp_unif_main,
                    "sp_prob_actual": None,
                    "sp_rank_actual": None,
                    "sp_top5": None,
                })
            rows[mid].append(rec)
        state.update(draws0[t],
                     None if specials0 is None else int(specials0[t]))
        scored_idx += 1
    return rows
