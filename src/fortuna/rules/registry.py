"""Load and integrity-check the game regime inventory (metadata/game_regimes.csv)."""

from datetime import date, timedelta
from pathlib import Path

from fortuna.schemas.csv_io import load_csv
from fortuna.schemas.games import Game
from fortuna.schemas.regimes import GameRegime

DEFAULT_METADATA_DIR = Path("metadata")


class RegimeIntegrityError(ValueError):
    """Raised when the regime inventory is internally contradictory."""


def load_games(path: str | Path = DEFAULT_METADATA_DIR / "games.csv") -> list[Game]:
    return load_csv(path, Game)


def load_regimes(path: str | Path = DEFAULT_METADATA_DIR / "game_regimes.csv") -> list[GameRegime]:
    """Load the regime inventory and run cross-row integrity checks."""
    regimes = load_csv(path, GameRegime)
    check_regime_integrity(regimes)
    return regimes


def check_regime_integrity(regimes: list[GameRegime]) -> list[str]:
    """Validate the inventory as a whole. Returns a list of non-fatal warnings.

    Fatal conditions (raise RegimeIntegrityError):
      - duplicate regime_id or statistical_regime_id collisions
      - overlapping draw spans within one game
      - regimes sharing a pool group with different sampling matrices
      - a regime whose classification claims a material change but reuses the
        prior pool group (or vice versa: non-material change but new group)
      - unknown pool-group ordering (groups must be introduced by matrix or
        mechanism/baseline events)
    """
    warnings: list[str] = []

    ids = [r.regime_id for r in regimes]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise RegimeIntegrityError(f"duplicate regime_id(s): {sorted(dupes)}")

    # Pool-group consistency: identical matrix_key within each statistical group.
    groups: dict[str, list[GameRegime]] = {}
    for r in regimes:
        groups.setdefault(r.statistical_regime_id, []).append(r)
    for gid, members in groups.items():
        keys = {m.matrix_key() for m in members}
        if len(keys) > 1:
            raise RegimeIntegrityError(
                f"statistical_regime_id {gid} spans incompatible matrices — "
                "pool group members must be sampling-equivalent"
            )
        game_ids = {m.game_id for m in members}
        if len(game_ids) > 1:
            raise RegimeIntegrityError(f"statistical_regime_id {gid} spans multiple games")

    # Material-change classification must agree with pool-group novelty.
    first_seen_group: dict[str, str] = {}
    for r in sorted(
        regimes,
        key=lambda r: (r.game_id, r.span_start or r.legal_effective_start or date.max),
    ):
        first_seen_group.setdefault(r.statistical_regime_id, r.regime_id)
    for r in regimes:
        introduces_new_group = first_seen_group[r.statistical_regime_id] == r.regime_id
        material = r.change_classification.value in ("baseline", "matrix", "mechanism")
        if material and not introduces_new_group:
            raise RegimeIntegrityError(
                f"{r.regime_id}: classified {r.change_classification.value} but reuses "
                f"existing pool group {r.statistical_regime_id}"
            )
        if (
            r.change_classification.value in ("schedule", "economic", "administrative")
            and introduces_new_group
        ):
            raise RegimeIntegrityError(
                f"{r.regime_id}: non-material change ({r.change_classification.value}) "
                f"introduces new pool group {r.statistical_regime_id}"
            )

    # Span overlap check per game.
    by_game: dict[str, list[GameRegime]] = {}
    for r in regimes:
        by_game.setdefault(r.game_id, []).append(r)
    far_future = date(9999, 12, 31)
    for game_id, rows in by_game.items():
        dated = [r for r in rows if r.span_start is not None]
        dated.sort(key=lambda r: r.span_start)  # type: ignore[arg-type]
        prev: GameRegime | None = None
        for r in dated:  # noqa: B007 - r used below
            if prev is not None:
                prev_end = prev.span_end or far_future
                if r.span_start <= prev_end:  # type: ignore[operator]
                    raise RegimeIntegrityError(
                        f"{game_id}: regimes {prev.regime_id} and {r.regime_id} have "
                        f"overlapping draw spans ({prev.span_start}..{prev.span_end} vs "
                        f"{r.span_start}..{r.span_end})"
                    )
                gap_days = (r.span_start - prev_end).days - 1  # type: ignore[operator]
                if gap_days > 0:
                    # A gap only matters if a scheduled draw day falls inside it.
                    scheduled = {
                        "mon": 0, "tue": 1, "wed": 2, "thu": 3,
                        "fri": 4, "sat": 5, "sun": 6,
                    }
                    days = set(prev.drawing_days) | set(r.drawing_days)
                    weekdays = {scheduled[d] for d in days}
                    lost_draws = any(
                        (prev_end + timedelta(days=i)).weekday() in weekdays
                        for i in range(1, gap_days + 1)
                    )
                    if lost_draws:
                        warnings.append(
                            f"{game_id}: coverage gap containing scheduled draw "
                            f"day(s) between {prev.regime_id} and {r.regime_id} "
                            f"({prev_end} -> {r.span_start})"
                        )
            prev = r
        undated = [r.regime_id for r in rows if r.span_start is None]
        if undated:
            warnings.append(f"{game_id}: regimes with no usable dates: {undated}")

    # Quarantine-window consistency.
    for r in regimes:
        if r.first_unambiguous_draw is None:
            continue
        if r.verification_status.value == "verified":
            warnings.append(
                f"{r.regime_id}: verified regime carries a quarantine window — "
                "either the boundary is proven (drop first_unambiguous_draw) or "
                "it is not (downgrade verification_status)"
            )
        if r.last_affected_draw and r.first_unambiguous_draw > r.last_affected_draw:
            warnings.append(
                f"{r.regime_id}: quarantine window extends past span end — "
                "the entire regime span is unproven"
            )

    return warnings
