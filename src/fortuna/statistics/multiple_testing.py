"""Multiple-testing utilities (registered for later phases, tested now).

Benjamini-Hochberg (FDR) and Holm (FWER) adjustments. Implemented directly
to keep the dependency surface minimal; returns adjusted p-values and
rejection masks.
"""

import numpy as np


def _order(pvals: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.argsort(pvals, kind="stable")
    return order, np.empty_like(order)


def benjamini_hochberg(
    pvals: np.ndarray, alpha: float = 0.05
) -> dict[str, np.ndarray]:
    """BH step-up. Returns sorted-order-adjusted p-values mapped back to the
    input order, and a boolean rejection mask (input order)."""
    p = np.asarray(pvals, dtype=float)
    m = p.size
    order = np.argsort(p, kind="stable")
    ps = p[order]
    ranks = np.arange(1, m + 1)
    adj_sorted = np.minimum.accumulate((ps * m / ranks)[::-1])[::-1]
    adj_sorted = np.clip(adj_sorted, 0, 1)
    adj = np.empty(m)
    adj[order] = adj_sorted
    crit = ranks * alpha / m
    k = 0
    for i in range(m - 1, -1, -1):
        if ps[i] <= crit[i]:
            k = i + 1
            break
    rejected = np.zeros(m, dtype=bool)
    rejected[order[:k]] = True
    return {"adjusted": adj, "rejected": rejected}


def holm(pvals: np.ndarray, alpha: float = 0.05) -> dict[str, np.ndarray]:
    """Holm step-down. Adjusted p_i = max over j<=i of (m-j+1) p_(j)."""
    p = np.asarray(pvals, dtype=float)
    m = p.size
    order = np.argsort(p, kind="stable")
    ps = p[order]
    factors = m - np.arange(m)
    adj_sorted = np.clip(np.maximum.accumulate(ps * factors), 0, 1)
    adj = np.empty(m)
    adj[order] = adj_sorted
    rejected = np.zeros(m, dtype=bool)
    for i in range(m):
        if ps[i] <= alpha / factors[i]:
            rejected[order[i]] = True
        else:
            break
    return {"adjusted": adj, "rejected": rejected}
