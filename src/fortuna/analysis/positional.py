"""F-E004 Phase 3B positional statistics P3B-S001..P3B-S010.

Frozen definitions live in config/experiments/F-E004.yaml and the
F-E004 preregistration. Every statistic consumes ORDERED physical draw
sequences ``ord0`` — an (n_ord, K) array of zero-based ball labels where
column j is the j-th physically extracted ball — and is calibrated
against the FAIR SEQUENTIAL WITHOUT-REPLACEMENT null (uniform ordered
K-permutations), never against independent positions. Cross-draw
(serial/rolling) statistics operate within contiguous physical-order
segments only and never bridge a break.

Notation: n = n_ord, N = matrix.main_pool, K = matrix.main_count.
"""

import math

import numpy as np

PRIMARY_P3B = (
    "P3B-S001", "P3B-S002", "P3B-S003", "P3B-S004",
    "P3B-S006", "P3B-S007", "P3B-S008",
)
SECONDARY_P3B = ("P3B-S005", "P3B-S009", "P3B-S010")

MC_STATS = PRIMARY_P3B + ("P3B-S005", "P3B-S009")  # S010 is permutation-based


def _seg_bounds(seg_lengths: list[int]) -> list[tuple[int, int]]:
    out, s = [], 0
    for ln in seg_lengths:
        out.append((s, s + ln))
        s += ln
    return out


def position_ball_counts(ord0: np.ndarray, n_pool: int) -> np.ndarray:
    """(K, N) count matrix: c[j, a] = #draws with ball a at position j."""
    n, k = ord0.shape
    flat = (ord0 + np.arange(k)[None, :] * n_pool).ravel()
    return np.bincount(flat, minlength=k * n_pool).reshape(k, n_pool)


# ---------------------------------------------------------------- P3B-S001


def p3b_s001(ord0: np.ndarray, n_pool: int) -> float:
    """Pearson-style omnibus over the K x N position x ball matrix.

    T = sum_{j,a} (c_{j,a} - n/N)^2 / (n/N). Upper tail.
    """
    n = ord0.shape[0]
    e = n / n_pool
    c = position_ball_counts(ord0, n_pool)
    return float(((c - e) ** 2 / e).sum())


# ---------------------------------------------------------------- P3B-S002


def p3b_s002(ord0: np.ndarray, n_pool: int) -> float:
    """Max |standardized residual| over position x ball cells.

    z = (c - n*p) / sqrt(n*p*(1-p)) with p = 1/N. Upper tail.
    """
    n = ord0.shape[0]
    p = 1.0 / n_pool
    sd = math.sqrt(n * p * (1 - p))
    if sd <= 0:
        return 0.0
    c = position_ball_counts(ord0, n_pool)
    return float(np.abs(c - n * p).max() / sd)


def position_residuals(ord0: np.ndarray, n_pool: int) -> np.ndarray:
    """(K, N) standardized residuals (c - n/N)/sqrt(n p (1-p))."""
    n = ord0.shape[0]
    p = 1.0 / n_pool
    sd = math.sqrt(n * p * (1 - p))
    c = position_ball_counts(ord0, n_pool)
    return (c - n * p) / sd


# ---------------------------------------------------------------- P3B-S003


def _discrete_cvm_uniform(values: np.ndarray, n_pool: int) -> float:
    """Discrete Cramer-von Mises discrepancy vs Uniform{0..N-1}.

    T = sum_x (1/N) * (F_emp(x) - F0(x))^2 over x = 0..N-1.
    """
    xs = np.arange(n_pool, dtype=float)
    p0 = 1.0 / n_pool
    f0 = (xs + 1.0) * p0
    emp = np.sort(values.astype(float))
    f_emp = np.searchsorted(emp, xs, side="right") / emp.size
    return float((p0 * (f_emp - f0) ** 2).sum())


def p3b_s003(ord0: np.ndarray, n_pool: int) -> float:
    """Max over positions of the CvM discrepancy of that position's
    empirical label distribution vs the uniform label pmf. Upper tail."""
    return float(
        max(
            _discrete_cvm_uniform(ord0[:, j], n_pool)
            for j in range(ord0.shape[1])
        )
    )


# ------------------------------------------------- shared pair contingency


def _pair_counts(
    ord0: np.ndarray, pairs: list[tuple[int, int]], n_pool: int
) -> np.ndarray:
    """(P, N*N) counts of ordered label pairs (a, b) for position pairs."""
    out = np.empty((len(pairs), n_pool * n_pool), dtype=np.int64)
    for i, (j, k) in enumerate(pairs):
        ids = ord0[:, j] * n_pool + ord0[:, k]
        out[i] = np.bincount(ids, minlength=n_pool * n_pool)
    return out


# ---------------------------------------------------------------- P3B-S004


def p3b_s004(ord0: np.ndarray, n_pool: int) -> float:
    """Omnibus adjacent-position transition discrepancy (P3B-S004).

    For each adjacent position pair (j, j+1), the ordered-label
    contingency c_j(a,b) is compared against the FAIR WITHOUT-REPLACEMENT
    expectation e = n / (N(N-1)) for a != b via Pearson dispersion:

        T = sum_j sum_{a != b} (c_j(a,b) - e)^2 / e.

    Cells a == b are impossible under any valid draw and excluded.
    Upper tail; calibrated under the ordered fair null (which already
    contains the no-replacement dependence).
    """
    n, k = ord0.shape
    pairs = [(j, j + 1) for j in range(k - 1)]
    if not pairs:
        return 0.0
    e = n / (n_pool * (n_pool - 1))
    cnt = _pair_counts(ord0, pairs, n_pool).reshape(
        len(pairs), n_pool, n_pool
    )
    cnt[:, np.arange(n_pool), np.arange(n_pool)] = 0  # a == b excluded
    return float(((cnt - e) ** 2 / e).sum())


# ---------------------------------------------------------------- P3B-S005


def p3b_s005(ord0: np.ndarray, n_pool: int) -> float:
    """Max |standardized ordered-pair residual| over all ordered
    position pairs (j,k), j != k, and ordered label cells a != b.

    z = (c - n*p) / sqrt(n*p*(1-p)) with p = 1/(N(N-1)). Upper tail.
    """
    n, k = ord0.shape
    pairs = [(j, kk) for j in range(k) for kk in range(k) if j != kk]
    if not pairs:
        return 0.0
    p = 1.0 / (n_pool * (n_pool - 1))
    sd = math.sqrt(n * p * (1 - p))
    if sd <= 0:
        return 0.0
    cnt = _pair_counts(ord0, pairs, n_pool).reshape(
        len(pairs), n_pool, n_pool
    )
    cnt[:, np.arange(n_pool), np.arange(n_pool)] = 0  # a == b impossible
    return float(np.abs(cnt - n * p).max() / sd)


def ordered_pair_residuals(
    ord0: np.ndarray, n_pool: int
) -> dict[tuple[int, int], np.ndarray]:
    """{(j,k): (N,N) standardized residuals} for all ordered pairs."""
    n, k = ord0.shape
    pairs = [(j, kk) for j in range(k) for kk in range(k) if j != kk]
    p = 1.0 / (n_pool * (n_pool - 1))
    sd = math.sqrt(n * p * (1 - p))
    cnt = _pair_counts(ord0, pairs, n_pool).reshape(
        len(pairs), n_pool, n_pool
    )
    return {pair: (cnt[i] - n * p) / sd for i, pair in enumerate(pairs)}


# ---------------------------------------------------------------- P3B-S006


def _mutual_information_bits(cnt: np.ndarray) -> float:
    """Empirical mutual information (bits) of an (N, N) contingency."""
    tot = cnt.sum()
    if tot <= 0:
        return 0.0
    p_ab = cnt / tot
    p_a = p_ab.sum(axis=1, keepdims=True)
    p_b = p_ab.sum(axis=0, keepdims=True)
    nz = p_ab > 0
    return float(
        (p_ab[nz] * np.log2(p_ab[nz] / (p_a @ p_b)[nz])).sum()
    )


def p3b_s006(ord0: np.ndarray, n_pool: int) -> float:
    """Max empirical mutual information (bits) over adjacent position
    pairs (j, j+1), using empirical marginals. Upper tail; the fair
    null already carries nonzero MI from no-replacement dependence, so
    calibration is against the null distribution of the SAME measure.
    """
    k = ord0.shape[1]
    pairs = [(j, j + 1) for j in range(k - 1)]
    if not pairs:
        return 0.0
    cnt = _pair_counts(ord0, pairs, n_pool)
    return float(
        max(
            _mutual_information_bits(cnt[i].reshape(n_pool, n_pool))
            for i in range(len(pairs))
        )
    )


# ------------------------------------------------------- serial statistics


def _lag_pairs(
    ord0: np.ndarray, seg_lengths: list[int], lag: int
) -> tuple[np.ndarray, np.ndarray]:
    """Index arrays (t_src, t_dst) for within-segment lagged pairs."""
    src, dst = [], []
    for s, e in _seg_bounds(seg_lengths):
        if e - s > lag:
            t = np.arange(s, e - lag)
            src.append(t)
            dst.append(t + lag)
    if not src:
        return np.empty(0, dtype=int), np.empty(0, dtype=int)
    return np.concatenate(src), np.concatenate(dst)


def _binom_z(hits: float, n_pairs: int, p: float) -> float:
    if n_pairs <= 0:
        return 0.0
    sd = math.sqrt(n_pairs * p * (1 - p))
    return 0.0 if sd <= 0 else (hits - n_pairs * p) / sd


def p3b_s007_components(
    ord0: np.ndarray, n_pool: int, seg_lengths: list[int], lags
) -> dict[tuple[int, int], dict]:
    """Per (position j, lag) equality-hit z for the same physical
    position across draws. p = 1/N per pair under the fair null."""
    k = ord0.shape[1]
    p = 1.0 / n_pool
    out = {}
    for lag in lags:
        src, dst = _lag_pairs(ord0, seg_lengths, lag)
        for j in range(k):
            hits = float((ord0[src, j] == ord0[dst, j]).sum())
            out[(j, lag)] = {
                "hits": hits, "n_pairs": int(src.size),
                "z": _binom_z(hits, int(src.size), p),
            }
    return out


def p3b_s007(
    ord0: np.ndarray, n_pool: int, seg_lengths: list[int], lags
) -> float:
    """Max |z| over position x lag same-position serial hits."""
    comp = p3b_s007_components(ord0, n_pool, seg_lengths, lags)
    return float(max(abs(v["z"]) for v in comp.values()))


def p3b_s008_components(
    ord0: np.ndarray, n_pool: int, seg_lengths: list[int], lags
) -> dict[tuple[int, int, int], dict]:
    """Per (source j, destination k, lag) equality-hit z."""
    k = ord0.shape[1]
    p = 1.0 / n_pool
    out = {}
    for lag in lags:
        src, dst = _lag_pairs(ord0, seg_lengths, lag)
        eq = ord0[src][:, :, None] == ord0[dst][:, None, :]  # (P, K, K)
        n_pairs = int(src.size)
        for j in range(k):
            for kk in range(k):
                hits = float(eq[:, j, kk].sum())
                out[(j, kk, lag)] = {
                    "hits": hits, "n_pairs": n_pairs,
                    "z": _binom_z(hits, n_pairs, p),
                }
    return out


def p3b_s008(
    ord0: np.ndarray, n_pool: int, seg_lengths: list[int], lags
) -> float:
    """Max |z| over (source position, dest position, lag) cross-position
    serial equality hits. Upper tail."""
    comp = p3b_s008_components(ord0, n_pool, seg_lengths, lags)
    return float(max(abs(v["z"]) for v in comp.values()))


# ---------------------------------------------------------------- P3B-S009


def p3b_s009_scan(
    ord0: np.ndarray, n_pool: int, seg_lengths: list[int], windows
) -> tuple[float, list[dict]]:
    """Rolling positional-frequency scan (P3B-S009).

    For each within-segment window of length w, each position j and each
    ball a: z = (c - w*p) / sqrt(w*p*(1-p)), p = 1/N. Statistic = max |z|
    over all windows x positions x balls. Returns (stat, per-window
    diagnostic rows) where each row is the window's max |z| and the
    attaining (position, ball) identity.
    """
    n, k = ord0.shape
    p = 1.0 / n_pool
    zmax = 0.0
    diag: list[dict] = []
    for s, e in _seg_bounds(seg_lengths):
        seg = ord0[s:e]
        n_seg = e - s
        for w in windows:
            if w > n_seg:
                continue
            sd = math.sqrt(w * p * (1 - p))
            for j in range(k):
                mem = np.zeros((n_seg, n_pool))
                mem[np.arange(n_seg), seg[:, j]] = 1.0
                cs = np.vstack([np.zeros((1, n_pool)), np.cumsum(mem, 0)])
                sums = cs[w:] - cs[:-w]                      # (n-w+1, N)
                z = np.abs(sums - w * p) / sd
                imax = int(np.argmax(z))
                wz = float(z.flat[imax])
                wi, bi = divmod(imax, n_pool)
                zmax = max(zmax, wz)
                diag.append({
                    "window_length": w, "window_start_index": s + wi,
                    "position": j + 1, "ball_index": bi,
                    "max_abs_z": wz,
                })
    return zmax, diag


def p3b_s009(
    ord0: np.ndarray, n_pool: int, seg_lengths: list[int], windows
) -> float:
    return p3b_s009_scan(ord0, n_pool, seg_lengths, windows)[0]


def s009_applicable(seg_lengths: list[int], windows) -> bool:
    """A rolling window is used only when it fits inside a segment."""
    return any(ln >= min(windows) for ln in seg_lengths)


# ---------------------------------------------------------------- P3B-S010


def p3b_s010_chi2(
    ord0: np.ndarray, labels: np.ndarray, n_pool: int
) -> float:
    """Equipment x position x ball Pearson discrepancy (P3B-S010).

    T = sum_cat sum_j sum_a (c - n_cat/N)^2 / (n_cat/N) over the
    category x position x ball contingency — tests positional outcome
    patterns jointly by equipment category, calibrated by calendar-year
    blocked permutation of the equipment labels.
    """
    n, k = ord0.shape
    t = 0.0
    for cat in np.unique(labels):
        sel = ord0[labels == cat]
        n_cat = sel.shape[0]
        e = n_cat / n_pool
        if e <= 0:
            continue
        c = position_ball_counts(sel, n_pool)
        t += float(((c - e) ** 2 / e).sum())
    return t


def p3b_s010_permutation_null(
    ord0: np.ndarray,
    labels: np.ndarray,
    year_blocks: np.ndarray,
    n_pool: int,
    rng: np.random.Generator,
    n_perm: int,
) -> np.ndarray:
    """Calendar-year blocked permutation null for P3B-S010."""
    out = np.empty(n_perm)
    lab = labels.copy()
    for i in range(n_perm):
        perm = lab.copy()
        for y in np.unique(year_blocks):
            idx = np.flatnonzero(year_blocks == y)
            perm[idx] = lab[idx][rng.permutation(idx.size)]
        out[i] = p3b_s010_chi2(ord0, perm, n_pool)
    return out


# ---------------------------------------------------------------- driver


def p3b_mc_statistics(
    ord0: np.ndarray,
    n_pool: int,
    seg_lengths: list[int],
    lags_same,
    lags_cross,
    windows,
) -> dict[str, float]:
    """All Monte-Carlo-calibrated P3B statistics for one ordered history.

    ``ord0`` is (n_ord, K) zero-based ordered labels; ``seg_lengths`` are
    the contiguous physical-order segment lengths (serial/rolling stats
    never bridge a break). P3B-S010 is excluded (permutation-calibrated).
    """
    return {
        "P3B-S001": p3b_s001(ord0, n_pool),
        "P3B-S002": p3b_s002(ord0, n_pool),
        "P3B-S003": p3b_s003(ord0, n_pool),
        "P3B-S004": p3b_s004(ord0, n_pool),
        "P3B-S005": p3b_s005(ord0, n_pool),
        "P3B-S006": p3b_s006(ord0, n_pool),
        "P3B-S007": p3b_s007(ord0, n_pool, seg_lengths, lags_same),
        "P3B-S008": p3b_s008(ord0, n_pool, seg_lengths, lags_cross),
        "P3B-S009": p3b_s009(ord0, n_pool, seg_lengths, windows),
    }
