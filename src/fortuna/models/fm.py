"""F-E005 frozen model family F-M000..F-M004.

Every main-ball model produces positive per-label weights ``w`` scored
through the exact weighted K-subset distribution (fortuna.models.wsubset);
every special-ball model produces a softmax categorical distribution.
All state is strictly chronological: features and fitted parameters for
draw t use only draws < t within the SAME statistical regime.

Frozen specifications (config/experiments/F-E005.yaml):

- F-M000  uniform baseline (w_i = 1).
- F-M001  shrunk expanding frequency: w_i prop (c_i + A*p), A = 100
          pseudo-draws, p = K/N.
- F-M002  EWMA frequency, half-life 50 draws, shrunk toward uniform with
          pseudo-weighted-draw strength A = 25.
- F-M003  recency/gap: single coefficient on the standardized gap
          feature; L2 penalty in {0.1, 1, 10, 100} via nested
          chronological inner validation.
- F-M004  six-feature penalized subset model (same penalty grid).

Refit cadence: F-M003/F-M004 refit every 25 scored draws per regime;
between refits parameters persist while features update.
"""

import numpy as np

from fortuna.models.wsubset import (
    inclusion_probs,
    log_p_subset,
)

SCORE_CLIP = 8.0            # w = exp(clip(score, +-8))
PENALTY_GRID = (0.1, 1.0, 10.0, 100.0)
INNER_FIT_FRAC = 0.8
INNER_MIN_FIT_DRAWS = 50
FALLBACK_PENALTY = 100.0
FIT_ITERS = 150
FIT_LR = 0.05

MODEL_IDS = ("F-M000", "F-M001", "F-M002", "F-M003", "F-M004")
FITTED_MODELS = ("F-M003", "F-M004")

# ------------------------------------------------------------ features


def _geom_log1p_moments(p: float) -> tuple[float, float]:
    """Null mean/sd of log1p(gap) under the fair geometric recurrence
    (truncated at 40x the mean recurrence — deterministic constant)."""
    mean_gap = (1.0 - p) / p
    horizon = int(max(2000, 40 * mean_gap))
    g = np.arange(horizon + 1)
    pmf = p * (1.0 - p) ** g
    pmf /= pmf.sum()
    x = np.log1p(g)
    mu = float((x * pmf).sum())
    sd = float(np.sqrt(((x - mu) ** 2 * pmf).sum()))
    return mu, sd


class RegimeFeatureState:
    """Running per-regime state producing per-ball feature vectors.

    Features are computed BEFORE the current draw's outcome is applied;
    ``features()`` is therefore strictly a function of draws < t.

    Main-ball features (F-M004):
      0 expanding-frequency z-residual
      1 EWMA(hl=25) frequency z-residual
      2 EWMA(hl=100) frequency z-residual
      3 log1p gap standardized vs fair-geometric null moments
      4 appeared-in-previous-draw indicator
      5 smoothed affinity with previous draw's balls (excess co-occurrence)

    Special-ball features (F-M004 special model):
      expanding z, EWMA-25 z, EWMA-100 z, standardized gap,
      previous-special repeat indicator.
    """

    EWMA_HLS = (25.0, 50.0, 100.0)
    # feature rows use indices 0 (hl=25) and 2 (hl=100); row 1 (hl=50)
    # is maintained for model F-M002.
    AFFINITY_PSEUDO = 50.0

    def __init__(self, n_pool: int, k: int, special_pool: int = 0):
        self.n_pool = n_pool
        self.k = k
        self.p = k / n_pool
        self.n = 0
        self.counts = np.zeros(n_pool)
        self.ewma = np.zeros((3, n_pool))
        self.ewma_mass = np.zeros(3)
        self._ewma_sq_mass = np.zeros(3)
        self._sp_ewma_sq_mass = np.zeros(3)
        self.gap = np.zeros(n_pool, dtype=float)   # draws since last seen
        self.prev = np.zeros(n_pool, dtype=bool)
        self.pair_counts = np.zeros((n_pool, n_pool))
        self.gap_mu, self.gap_sd = _geom_log1p_moments(self.p)
        self.special_pool = special_pool
        if special_pool:
            self.sp_counts = np.zeros(special_pool)
            self.sp_ewma = np.zeros((3, special_pool))
            self.sp_ewma_mass = np.zeros(3)
            self.sp_gap = np.zeros(special_pool)
            self.sp_prev = -1
            ps = 1.0 / special_pool
            self.sp_gap_mu, self.sp_gap_sd = _geom_log1p_moments(ps)

    # ---- main-ball features ------------------------------------------

    def _freq_z(self, counts: np.ndarray, mass: float) -> np.ndarray:
        p = self.p
        sd = np.sqrt(max(mass, 1e-9) * p * (1 - p))
        return (counts - mass * p) / sd

    def _ewma_z(self, row: int) -> np.ndarray:
        p = self.p
        mass = self.ewma_mass[row]
        # effective draws: mass^2 / sum(lam^{2j})
        eff_var_mass = self._ewma_sq_mass[row]
        n_eff = mass * mass / max(eff_var_mass, 1e-12)
        sd = np.sqrt(p * (1 - p) / max(n_eff, 1e-9))
        return (self.ewma[row] / max(mass, 1e-9) - p) / sd

    def main_features(self) -> np.ndarray:
        """(N, 6) feature matrix from draws < current time."""
        x = np.empty((self.n_pool, 6))
        x[:, 0] = self._freq_z(self.counts, float(self.n))
        x[:, 1] = self._ewma_z(0)
        x[:, 2] = self._ewma_z(2)
        x[:, 3] = (np.log1p(self.gap) - self.gap_mu) / self.gap_sd
        x[:, 4] = self.prev.astype(float)
        p_pair = self.k * (self.k - 1) / (self.n_pool * (self.n_pool - 1))
        a0 = self.AFFINITY_PSEUDO
        smooth = (self.pair_counts + a0 * p_pair) / (self.n + a0)
        # affinity_i = mean smoothed pair-rate with previous draw's balls,
        # excluding i's own (impossible) self-pair, minus the fair rate
        aff = smooth @ self.prev - np.diag(smooth) * self.prev
        x[:, 5] = aff / max(self.prev.sum(), 1) - p_pair
        return x

    # ---- special-ball features ----------------------------------------

    def special_features(self) -> np.ndarray:
        """(M, 5) feature matrix for the special-ball model."""
        m = self.special_pool
        p = 1.0 / m
        x = np.empty((m, 5))
        sd = np.sqrt(max(self.n, 1e-9) * p * (1 - p))
        x[:, 0] = (self.sp_counts - self.n * p) / sd
        for col, row in ((1, 0), (2, 2)):
            mass = self.sp_ewma_mass[row]
            n_eff = mass * mass / max(self._sp_ewma_sq_mass[row], 1e-12)
            sdr = np.sqrt(p * (1 - p) / max(n_eff, 1e-9))
            x[:, col] = (
                self.sp_ewma[row] / max(mass, 1e-9) - p
            ) / sdr
        x[:, 3] = (np.log1p(self.sp_gap) - self.sp_gap_mu) / self.sp_gap_sd
        prev = np.zeros(m)
        if 0 <= self.sp_prev < m:
            prev[self.sp_prev] = 1.0
        x[:, 4] = prev
        return x

    # ---- state update --------------------------------------------------

    def update(self, draw0: np.ndarray, special0: int | None) -> None:
        """Apply revealed outcome — call only AFTER scoring draw t."""
        lams = [0.5 ** (1.0 / h) for h in self.EWMA_HLS]
        hits = np.zeros(self.n_pool)
        hits[draw0] = 1.0
        for row, lam in enumerate(lams):
            self.ewma[row] = lam * self.ewma[row] + hits
            self.ewma_mass[row] = lam * self.ewma_mass[row] + 1.0
            self._ewma_sq_mass[row] = (
                lam * lam * self._ewma_sq_mass[row] + 1.0
            )
        self.counts += hits
        pc = np.outer(hits, hits)
        np.fill_diagonal(pc, 0.0)
        self.pair_counts += pc
        self.gap += 1.0
        self.gap[draw0] = 0.0
        self.prev[:] = False
        self.prev[draw0] = True
        self.n += 1
        if self.special_pool and special0 is not None:
            sh = np.zeros(self.special_pool)
            sh[special0] = 1.0
            for row, lam in enumerate(lams):
                self.sp_ewma[row] = lam * self.sp_ewma[row] + sh
                self.sp_ewma_mass[row] = lam * self.sp_ewma_mass[row] + 1.0
                self._sp_ewma_sq_mass[row] = (
                    lam * lam * self._sp_ewma_sq_mass[row] + 1.0
                )
            self.sp_counts += sh
            self.sp_gap += 1.0
            self.sp_gap[special0] = 0.0
            self.sp_prev = int(special0)


def feature_trajectories(
    draws0: np.ndarray, specials0: np.ndarray | None,
    n_pool: int, k: int, special_pool: int = 0,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Precompute the strict-past feature trajectory for a regime.

    Returns main (T, N, 6) and special (T, M, 5) or None. F[t] depends
    only on draws < t.
    """
    t_n = draws0.shape[0]
    st = RegimeFeatureState(n_pool, k, special_pool)
    f_main = np.empty((t_n, n_pool, 6))
    f_sp = (
        np.empty((t_n, special_pool, 5)) if special_pool else None
    )
    for t in range(t_n):
        f_main[t] = st.main_features()
        if f_sp is not None:
            f_sp[t] = st.special_features()
        st.update(draws0[t], None if specials0 is None else
                  int(specials0[t]))
    return f_main, f_sp


# ------------------------------------------------------------ models


def _scores_to_logw(scores: np.ndarray) -> np.ndarray:
    return np.clip(scores, -SCORE_CLIP, SCORE_CLIP)


def _subset_loglik(logw: np.ndarray, draws0: np.ndarray, k: int) -> float:
    return float(log_p_subset(logw, draws0, k).sum())


def _fit_subset_gradient(
    feats: np.ndarray, draws0: np.ndarray, k: int,
    penalty: float, n_iters: int = FIT_ITERS, lr: float = FIT_LR,
    beta0: np.ndarray | None = None,
) -> np.ndarray:
    """Penalized conditional log-likelihood fit of beta.

    Objective: sum_t log P_w(S_t) - (penalty/2) * ||beta||^2 with
    w_i = exp(clip(beta.x_i)). Gradient via exact inclusion marginals:
    d logP/d score_i = 1[i in S] - P(i in S | w).
    Adam-style adaptive steps, deterministic.
    """
    t_n, n_pool, n_feat = feats.shape
    beta = np.zeros(n_feat) if beta0 is None else beta0.copy()
    m1 = np.zeros(n_feat)
    m2 = np.zeros(n_feat)
    b1, b2, eps = 0.9, 0.999, 1e-8
    hit = np.zeros((t_n, n_pool))
    np.put_along_axis(hit, draws0, 1.0, axis=1)
    for it in range(1, n_iters + 1):
        s = np.clip(np.einsum("tnf,f->tn", feats, beta),
                    -SCORE_CLIP, SCORE_CLIP)
        inc = inclusion_probs(s, k)                    # (t, N)
        resid = hit - inc                              # d logP / d score
        # clip is a projection: zero gradient where clipped and moving out
        raw = np.einsum("tnf,f->tn", feats, beta)
        active = (np.abs(raw) < SCORE_CLIP) | (resid * np.sign(raw) > 0)
        resid = resid * active
        grad = np.einsum("tn,tnf->f", resid, feats) - penalty * beta
        m1 = b1 * m1 + (1 - b1) * grad
        m2 = b2 * m2 + (1 - b2) * grad * grad
        beta = beta + lr * (m1 / (1 - b1 ** it)) / (
            np.sqrt(m2 / (1 - b2 ** it)) + eps
        )
    return beta


def _fit_softmax_gradient(
    feats: np.ndarray, draws0: np.ndarray,
    penalty: float, n_iters: int = FIT_ITERS, lr: float = FIT_LR,
    beta0: np.ndarray | None = None,
) -> np.ndarray:
    """Penalized multinomial logit fit for the special ball."""
    t_n, m_pool, n_feat = feats.shape
    beta = np.zeros(n_feat) if beta0 is None else beta0.copy()
    m1 = np.zeros(n_feat)
    m2 = np.zeros(n_feat)
    b1, b2, eps = 0.9, 0.999, 1e-8
    hit = np.zeros((t_n, m_pool))
    np.put_along_axis(hit, draws0[:, None], 1.0, axis=1)
    for it in range(1, n_iters + 1):
        s = np.einsum("tmf,f->tm", feats, beta)
        s = s - s.max(axis=1, keepdims=True)
        pr = np.exp(s)
        pr /= pr.sum(axis=1, keepdims=True)
        grad = np.einsum("tm,tmf->f", hit - pr, feats) - penalty * beta
        m1 = b1 * m1 + (1 - b1) * grad
        m2 = b2 * m2 + (1 - b2) * grad * grad
        beta = beta + lr * (m1 / (1 - b1 ** it)) / (
            np.sqrt(m2 / (1 - b2 ** it)) + eps
        )
    return beta


def _nested_penalty(
    feats: np.ndarray, draws0: np.ndarray, k: int | None,
    softmax: bool, refit_log: list[dict], regime_id: str, t_abs: int,
) -> tuple[float, np.ndarray]:
    """Nested chronological inner validation for the L2 penalty.

    Inner fit uses the first 80% of the CURRENT training sample; the
    last 20% is validation. Ties break toward the stronger penalty.
    The chosen penalty is then refit on the full current sample.
    """
    t_n = feats.shape[0]
    n_fit = int(INNER_FIT_FRAC * t_n)
    if n_fit < INNER_MIN_FIT_DRAWS:
        lam = FALLBACK_PENALTY
        fit_all = _fit(feats, draws0, k, lam, softmax)
        refit_log.append({
            "statistical_regime_id": regime_id, "scored_index": t_abs,
            "n_train": t_n, "penalty": lam,
            "selection": "fallback_insufficient_inner_fit",
        })
        return lam, fit_all
    x_in, y_in = feats[:n_fit], draws0[:n_fit]
    x_va, y_va = feats[n_fit:], draws0[n_fit:]
    best_lam, best_ll = None, -np.inf
    for lam in PENALTY_GRID:
        b = _fit(x_in, y_in, k, lam, softmax)
        ll = _eval_loglik(b, x_va, y_va, k, softmax)
        if ll > best_ll + 1e-9:
            best_lam, best_ll = lam, ll
    refit_log.append({
        "statistical_regime_id": regime_id, "scored_index": t_abs,
        "n_train": t_n, "penalty": best_lam,
        "selection": "nested_chronological",
    })
    return best_lam, _fit(feats, draws0, k, best_lam, softmax)


def _fit(feats, draws0, k, lam, softmax, beta0=None):
    if softmax:
        return _fit_softmax_gradient(feats, draws0, lam, beta0=beta0)
    return _fit_subset_gradient(feats, draws0, k, lam, beta0=beta0)


def _eval_loglik(beta, feats, draws0, k, softmax) -> float:
    if softmax:
        s = np.einsum("tmf,f->tm", feats, beta)
        s = s - s.max(axis=1, keepdims=True)
        logp = s - np.log(np.exp(s).sum(axis=1, keepdims=True))
        return float(logp[np.arange(draws0.size), draws0].sum())
    logw = _scores_to_logw(np.einsum("tnf,f->tn", feats, beta))
    return _subset_loglik(logw, draws0, k)


# ------------------------------------------------------------- weights


def weights_m000(n_pool: int) -> np.ndarray:
    return np.ones(n_pool)


def weights_m001(counts: np.ndarray, n: int, n_pool: int,
                 k: int) -> np.ndarray:
    """Shrunk expanding frequency: w_i prop c_i + A*p, A=100."""
    p = k / n_pool
    return counts + 100.0 * p


def weights_m002(ewma_hits: float, ewma_mass: float, n_pool: int,
                 k: int) -> np.ndarray:
    """EWMA frequency shrunk toward uniform, pseudo strength A=25."""
    p = k / n_pool
    return ewma_hits + 25.0 * p


def special_probs_shrunk(counts: np.ndarray, m_pool: int,
                         pseudo: float) -> np.ndarray:
    """(c_i + A/M) normalized — proper categorical distribution."""
    v = counts + pseudo / m_pool
    return v / v.sum()


# --------------------------------------------------------------- draws


def draw_weighted_subset(
    rng: np.random.Generator, w: np.ndarray, k: int
) -> np.ndarray:
    """Sequential proportional sampling without replacement (Efraimidis-
    Spirakis keys): a valid biased K-subset generator used ONLY for
    synthetic controls — never a null model."""
    keys = rng.random(w.size) ** (1.0 / w)
    return np.argpartition(keys, -k)[-k:]
