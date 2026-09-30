"""Phase 3 exploration-only outcome loader — structural holdout firewall.

This is the ONLY Phase 3 module permitted to read winning-number fields
from the canonical store, and only for draw_ids present in
``metadata/phase3_exploration_ids.csv``.

Firewall rule: a row's ``draw_id`` is checked against the exploration id
set BEFORE any winning-number field (``main_numbers``, ``special_ball``,
``number``) is parsed. A holdout row — or any row outside the exploration
set — is dropped while its outcome payload is still an unread string, so
malformed/trap content in non-exploration rows can never be triggered.

If a holdout draw_id were ever included in the exploration id set, the
outcome parser would run on it and fail — a test asserts both halves.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

# Winning-number fields — parsed ONLY for exploration draw_ids.
_DRAW_OUTCOME_FIELDS = ("main_numbers", "special_ball")
_NUMBER_OUTCOME_FIELDS = ("number",)


@dataclass
class ExplorationDraw:
    draw_id: str
    regime_id: str
    draw_date: str
    numbers_order: str
    mains: tuple[int, ...]           # sorted main-ball labels
    special: int | None
    machine_id: str
    ball_set_id: str


@dataclass
class ExplorationHistory:
    """Exploration outcomes for one statistical regime."""

    draws: list[ExplorationDraw] = field(default_factory=list)
    # draw_id -> main labels in physical draw order (positions 1..K);
    # only for draws whose records carry physical_draw_order semantics.
    physical_order: dict = field(default_factory=dict)

    @property
    def mains(self):
        return [d.mains for d in self.draws]

    @property
    def specials(self):
        return [d.special for d in self.draws]


def _parse_mains(raw: str) -> tuple[int, ...]:
    return tuple(sorted(int(x) for x in raw.split(";")))


def load_exploration_draws(
    draws_csv: Path, exploration_ids: set[str]
) -> list[ExplorationDraw]:
    """Parse draws.csv outcome fields for exploration ids only."""
    out: list[ExplorationDraw] = []
    with draws_csv.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["draw_id"] not in exploration_ids:
                continue  # dropped BEFORE outcome parsing — firewall
            mains = _parse_mains(row["main_numbers"])
            special = (
                int(row["special_ball"]) if row["special_ball"] else None
            )
            # D-007 atomicity: a physical-order label is admissible only
            # when the row names the staged source that supplied the
            # stored sequence.
            if row["numbers_order"] == "physical_draw_order":
                assert row["number_sequence_source_id"], (
                    f"{row['draw_id']}: physical_draw_order without "
                    "number_sequence_source_id"
                )
            out.append(
                ExplorationDraw(
                    draw_id=row["draw_id"],
                    regime_id=row["regime_id"],
                    draw_date=row["draw_date"],
                    numbers_order=row["numbers_order"],
                    mains=mains,
                    special=special,
                    machine_id=row["machine_id"],
                    ball_set_id=row["ball_set_id"],
                )
            )
    return out


def load_exploration_physical_order(
    draw_numbers_csv: Path, exploration_ids: set[str]
) -> dict[str, list[int]]:
    """draw_id -> main labels in physical draw order.

    Reads draw_numbers.csv; a row is skipped on its draw_id BEFORE the
    ``number`` field is parsed. Only ``ball_type == 'main'`` rows with
    ``position_semantics == 'physical_draw_order'`` are used — sorted or
    unknown order is never substituted for physical order.
    """
    positions: dict[str, dict[int, int]] = {}
    with draw_numbers_csv.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["draw_id"] not in exploration_ids:
                continue  # dropped BEFORE outcome parsing — firewall
            if (
                row["ball_type"] != "main"
                or row["position_semantics"] != "physical_draw_order"
            ):
                continue
            positions.setdefault(row["draw_id"], {})[
                int(row["ball_position"])
            ] = int(row["number"])
    return {
        did: [pos[i] for i in sorted(pos)] for did, pos in positions.items()
    }


def load_exploration_histories(
    draws_csv: Path,
    draw_numbers_csv: Path,
    exploration_ids: set[str],
    stat_of: dict[str, str],
) -> dict[str, ExplorationHistory]:
    """All exploration outcomes grouped by statistical regime.

    Rows are assigned to statistical regimes via the legal-regime map;
    draws are returned in chronological order. No row outside
    ``exploration_ids`` has any outcome field parsed.
    """
    draws = load_exploration_draws(draws_csv, exploration_ids)
    order = load_exploration_physical_order(draw_numbers_csv, exploration_ids)
    seen_ids = {d.draw_id for d in draws}
    missing = exploration_ids - seen_ids
    if missing:
        raise ValueError(f"exploration ids missing from store: {sorted(missing)[:5]}")

    by_stat: dict[str, ExplorationHistory] = {}
    for d in sorted(draws, key=lambda d: (d.draw_date, d.draw_id)):
        stat_id = stat_of[d.regime_id]
        h = by_stat.setdefault(stat_id, ExplorationHistory())
        h.draws.append(d)
        if d.draw_id in order:
            h.physical_order[d.draw_id] = order[d.draw_id]
    return by_stat
