"""Monte Carlo p-value utility (finite-simulation corrected).

For later phases only. Phase 2 ships and tests this utility but never
applies it to historical statistics.

    p_hat = (b + 1) / (B + 1)

with B replicates and b the number at least as extreme as the observed
statistic. The +1 correction includes the observed value itself in the
reference set, so p_hat > 0 always and resolution is limited by B
(minimum attainable p is 1/(B+1)).
"""

import numpy as np


def mc_pvalue(
    observed: float, null_values: np.ndarray, tail: str = "upper"
) -> float:
    """Finite-simulation-corrected Monte Carlo tail probability.

    tail:
      - ``upper``:     b = #{x >= observed}
      - ``lower``:     b = #{x <= observed}
      - ``two-sided``: b = min(2*min(b_upper, b_lower), B)
    """
    x = np.asarray(null_values, dtype=float)
    b_total = x.size
    if b_total == 0:
        raise ValueError("null_values must be non-empty")
    b_upper = int((x >= observed).sum())
    b_lower = int((x <= observed).sum())
    if tail == "upper":
        b = b_upper
    elif tail == "lower":
        b = b_lower
    elif tail == "two-sided":
        b = min(2 * min(b_upper, b_lower), b_total)
    else:
        raise ValueError(f"unknown tail {tail!r}")
    return (b + 1) / (b_total + 1)
