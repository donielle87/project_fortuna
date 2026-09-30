"""Draw -> regime assignment and statistical pooling guards.

Core Phase-0 principle: no draw may enter an analytical dataset without a valid
regime assignment, and draws may only be pooled within a single
``statistical_regime_id`` (sampling-equivalence group).
"""

from collections.abc import Iterable
from datetime import date

from fortuna.schemas.draws import Draw
from fortuna.schemas.regimes import GameRegime


class NoRegimeError(ValueError):
    """No regime covers the requested (game, draw_date)."""


class AmbiguousRegimeError(ValueError):
    """More than one regime covers the requested (game, draw_date)."""


class IncompatibleMatrixError(ValueError):
    """Draws from different statistical regimes were pooled illegally."""


def assign_regime(
    game_id: str,
    draw_date: date,
    regimes: Iterable[GameRegime],
) -> GameRegime:
    """Return the regime governing ``game_id`` on ``draw_date``.

    Raises NoRegimeError if no regime covers the date — a draw must never be
    silently admitted unassigned — and AmbiguousRegimeError if several do.
    """
    matches = [
        r
        for r in regimes
        if r.game_id == game_id
        and r.span_start is not None
        and r.span_start <= draw_date
        and (r.span_end is None or draw_date <= r.span_end)
    ]
    if not matches:
        raise NoRegimeError(f"no regime covers {game_id} on {draw_date}")
    if len(matches) > 1:
        ids = [m.regime_id for m in matches]
        raise AmbiguousRegimeError(
            f"{game_id} on {draw_date} matches multiple regimes: {ids}"
        )
    return matches[0]


def statistical_groups(
    draws: Iterable[Draw], regimes: Iterable[GameRegime]
) -> dict[str, list[Draw]]:
    """Group draws by their regime's statistical_regime_id."""
    by_regime = {r.regime_id: r for r in regimes}
    groups: dict[str, list[Draw]] = {}
    for d in draws:
        if d.regime_id not in by_regime:
            raise NoRegimeError(f"draw {d.draw_id} has unknown regime_id {d.regime_id!r}")
        gid = by_regime[d.regime_id].statistical_regime_id
        groups.setdefault(gid, []).append(d)
    return groups


def assert_poolable(draws: Iterable[Draw], regimes: Iterable[GameRegime]) -> None:
    """Fail loudly if ``draws`` span more than one statistical regime.

    This is the guard that makes silent cross-matrix pooling impossible.
    """
    draws = list(draws)
    groups = statistical_groups(draws, regimes)
    if len(groups) > 1:
        detail = {gid: len(ds) for gid, ds in groups.items()}
        raise IncompatibleMatrixError(
            "draws span multiple statistical regimes and cannot be pooled: "
            f"{detail}"
        )
