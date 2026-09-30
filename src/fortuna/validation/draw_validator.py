"""Validate draw records against their assigned regime.

Fails loudly: every violation produces a reason string; ``validate_draws``
raises unless ``collect`` is used to gather per-draw results.
"""

from dataclasses import dataclass, field

from fortuna.rules.assign import NoRegimeError, assign_regime
from fortuna.schemas.draws import Draw, DrawValidationStatus
from fortuna.schemas.regimes import GameRegime


@dataclass
class DrawRejection:
    draw_id: str
    reasons: list[str] = field(default_factory=list)


def validate_draw(
    draw: Draw,
    regime: GameRegime | None,
    known_regime_ids: set[str] | None = None,
) -> list[str]:
    """Return a list of violation reasons (empty = valid).

    ``regime`` is the regime the draw CLAIMS (draw.regime_id). Checks both the
    claim's consistency with the regime record and the draw's fit inside it.
    """
    reasons: list[str] = []

    if not draw.regime_id:
        reasons.append("missing regime assignment")

    if regime is None:
        reasons.append(f"unknown regime_id {draw.regime_id!r}")
        return reasons

    if regime.game_id != draw.game_id:
        reasons.append(
            f"regime {regime.regime_id} belongs to {regime.game_id}, not {draw.game_id}"
        )

    if known_regime_ids is not None and draw.regime_id not in known_regime_ids:
        reasons.append(f"regime_id {draw.regime_id!r} not in inventory")

    if regime.span_start is not None and draw.draw_date < regime.span_start:
        reasons.append(
            f"draw_date {draw.draw_date} precedes regime start {regime.span_start}"
        )
    if regime.span_end is not None and draw.draw_date > regime.span_end:
        reasons.append(
            f"draw_date {draw.draw_date} is after regime end {regime.span_end}"
        )

    nums = draw.main_numbers
    if len(nums) != regime.main_ball_count:
        reasons.append(
            f"expected {regime.main_ball_count} main numbers, got {len(nums)}"
        )
    for n in nums:
        if not (regime.main_ball_min <= n <= regime.main_ball_max):
            reasons.append(
                f"main number {n} outside regime range "
                f"{regime.main_ball_min}-{regime.main_ball_max}"
            )
    if regime.sampling_without_replacement and len(set(nums)) != len(nums):
        reasons.append("duplicate main numbers where sampling is without replacement")

    if regime.special_ball_count == 0:
        if draw.special_ball is not None:
            reasons.append(
                f"regime {regime.regime_id} has no special ball but draw supplies "
                f"{draw.special_ball}"
            )
    else:
        if draw.special_ball is None:
            reasons.append("special ball required by regime but missing")
        elif not (regime.special_ball_min <= draw.special_ball <= regime.special_ball_max):  # type: ignore[operator]
            reasons.append(
                f"special ball {draw.special_ball} outside regime range "
                f"{regime.special_ball_min}-{regime.special_ball_max}"
            )
        # NB: the special ball is drawn from its own pool; matching a main
        # number is always legal.

    # Impossible special-ball structure on the regime side is prevented by the
    # schema; here we double-check degenerate pools.
    if regime.special_ball_count > 0 and (
        regime.special_ball_min is None or regime.special_ball_max is None
    ):
        reasons.append("regime declares special balls but lacks min/max")

    return reasons


def validate_draws(
    draws: list[Draw],
    regimes: list[GameRegime],
    collect: bool = False,
) -> dict[str, list[str]]:
    """Validate draws against the regime inventory.

    Also verifies each draw's claimed regime equals the regime actually
    governing its draw_date (a wrong-but-plausible assignment is still wrong).
    """
    by_id = {r.regime_id: r for r in regimes}
    known_ids = set(by_id)
    results: dict[str, list[str]] = {}
    for d in draws:
        reasons = validate_draw(d, by_id.get(d.regime_id), known_ids)
        try:
            actual = assign_regime(d.game_id, d.draw_date, regimes)
            if actual.regime_id != d.regime_id:
                reasons.append(
                    f"draw claims {d.regime_id} but {d.draw_date} is governed by "
                    f"{actual.regime_id}"
                )
        except NoRegimeError as exc:
            reasons.append(str(exc))
        if reasons or collect:
            results[d.draw_id] = reasons
        d.validation_status = (
            DrawValidationStatus.REJECTED if reasons else DrawValidationStatus.VALID
        )
    bad = {k: v for k, v in results.items() if v}
    if bad and not collect:
        raise ValueError(f"invalid draw records: {bad}")
    return results
