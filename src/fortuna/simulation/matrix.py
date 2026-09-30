"""Regime sampling matrix — the fair-null draw specification.

Built exclusively from the verified Phase 0 regime inventory
(metadata/game_regimes.csv). Nothing about any game's matrix is hard-coded
in the simulation layer.
"""

from dataclasses import dataclass

from fortuna.schemas.regimes import GameRegime


@dataclass(frozen=True)
class RegimeMatrix:
    """Fair-draw matrix for one statistical pool group."""

    statistical_regime_id: str
    game_id: str
    main_count: int          # K main balls per draw
    main_min: int
    main_max: int
    special_count: int = 0   # 0 -> no special ball
    special_min: int | None = None
    special_max: int | None = None

    @property
    def main_pool(self) -> int:
        """N = number of main-ball labels."""
        return self.main_max - self.main_min + 1

    @property
    def has_special(self) -> bool:
        return self.special_count > 0

    @property
    def special_pool(self) -> int:
        """M = number of special-ball labels (0 when the game has none)."""
        if not self.has_special:
            return 0
        assert self.special_min is not None and self.special_max is not None
        return self.special_max - self.special_min + 1

    def validate(self) -> None:
        if not (1 <= self.main_count <= self.main_pool):
            raise ValueError(f"{self.statistical_regime_id}: bad main matrix")
        if self.main_min < 1:
            raise ValueError(f"{self.statistical_regime_id}: bad main range")
        if self.has_special:
            if self.special_min is None or self.special_max is None:
                raise ValueError(f"{self.statistical_regime_id}: special range missing")
            if self.special_count != 1:
                raise ValueError(
                    f"{self.statistical_regime_id}: unsupported special_count "
                    f"{self.special_count}"
                )


def matrix_from_regime(reg: GameRegime) -> RegimeMatrix:
    """Build a RegimeMatrix from a verified regime-inventory row."""
    if not reg.sampling_without_replacement:
        raise ValueError(
            f"{reg.regime_id}: Phase 2 null requires sampling without replacement"
        )
    m = RegimeMatrix(
        statistical_regime_id=reg.statistical_regime_id,
        game_id=reg.game_id,
        main_count=reg.main_ball_count,
        main_min=reg.main_ball_min,
        main_max=reg.main_ball_max,
        special_count=reg.special_ball_count or 0,
        special_min=reg.special_ball_min,
        special_max=reg.special_ball_max,
    )
    m.validate()
    return m


def statistical_matrices(regimes: list[GameRegime]) -> dict[str, RegimeMatrix]:
    """One matrix per statistical regime; legal eras sharing a statistical
    pool must share the identical matrix."""
    out: dict[str, RegimeMatrix] = {}
    for reg in regimes:
        m = matrix_from_regime(reg)
        prev = out.get(m.statistical_regime_id)
        if prev is not None and prev != m:
            raise ValueError(
                f"statistical regime {m.statistical_regime_id} has conflicting "
                f"matrices across legal eras ({prev} vs {m})"
            )
        out[m.statistical_regime_id] = m
    return out
