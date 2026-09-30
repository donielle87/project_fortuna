"""Phase 2 observation plan — metadata-only view of the canonical dataset.

FIREWALL (Task 21): this module is the ONLY part of the simulation layer
allowed to read the canonical draw store, and it may only read the columns
whitelisted below. Winning-number values (main_numbers, special_ball,
multiplier, jackpot, ...) are never loaded here — Phase 2 sizes and segments
the null reference from structure, not outcomes.
"""

import csv
import hashlib
import json
from datetime import date
from pathlib import Path

from fortuna.schemas.regimes import GameRegime

# The only columns Phase 2 is permitted to read from draws.csv.
ALLOWED_DRAW_FIELDS = frozenset(
    {
        "draw_id",
        "game_id",
        "regime_id",
        "draw_date",
        "draw_stream",
        "analysis_eligible",
        "numbers_order",
        "number_sequence_source_id",
        "validation_status",
        "provisional",
    }
)

_WD = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def load_draw_metadata(draws_csv: Path) -> list[dict]:
    """Load only whitelisted metadata columns from the canonical store."""
    out: list[dict] = []
    with draws_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        # Winning-number and value columns may exist on disk; Phase 2 never
        # projects them into the plan.
        for row in reader:
            out.append(
                {k: row[k] for k in ALLOWED_DRAW_FIELDS if k in row}
            )
    return out


def _expected_dates(reg: GameRegime, horizon: date) -> list[date]:
    """Scheduled draw dates inside one legal-era regime row."""
    if not reg.drawing_days or reg.first_affected_draw is None:
        return []
    start = reg.first_affected_draw
    end = min(reg.last_affected_draw or horizon, horizon)
    days = {_WD[d] for d in reg.drawing_days}
    cur = start
    out = []
    while cur <= end:
        if cur.weekday() in days:
            out.append(cur)
        cur = date.fromordinal(cur.toordinal() + 1)
    return out


def contiguous_segments(
    timeline: list[date], eligible_dates: set[date]
) -> list[list[date]]:
    """Maximal runs of eligible positions along the observation timeline.

    ``timeline`` must contain every position where a draw was scheduled
    (expected dates) OR actually occurred (draw dates of eligible and
    ineligible draws alike). Any timeline position that is not
    analysis-eligible — a missing expected date, an ineligible draw, a
    Tier-3-only draw, an unresolved-conflict draw — breaks observable
    continuity. Sequential statistics must never bridge those positions.
    Eligible draws on non-scheduled dates are ordinary timeline positions:
    they stay in sequence order and do not themselves cause a break."""
    segments: list[list[date]] = []
    current: list[date] = []
    for d in sorted(set(timeline)):
        if d in eligible_dates:
            current.append(d)
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def build_observation_plan(
    draws_csv: Path,
    regimes: list[GameRegime],
    dataset_sha256: str,
) -> list[dict]:
    """One row per statistical regime — structure only, no outcomes."""
    meta = load_draw_metadata(draws_csv)
    asof = max(date.fromisoformat(r["draw_date"]) for r in meta)

    # eligible main draws per statistical regime
    stat_of = {r.regime_id: r.statistical_regime_id for r in regimes}
    by_stat: dict[str, dict] = {}
    for r in meta:
        if r["draw_stream"] != "main":
            continue
        stat_id = stat_of.get(r["regime_id"])
        if stat_id is None:
            continue
        d = date.fromisoformat(r["draw_date"])
        rec = by_stat.setdefault(
            stat_id, {"eligible": set(), "all_dates": set(), "order_phys": set()}
        )
        rec["all_dates"].add(d)
        if r["analysis_eligible"] == "true":
            rec["eligible"].add(d)
            if r.get("numbers_order") == "physical_draw_order":
                rec["order_phys"].add(d)

    # expected schedule per statistical regime = union over legal-era rows
    stat_regs: dict[str, list[GameRegime]] = {}
    for r in regimes:
        stat_regs.setdefault(r.statistical_regime_id, []).append(r)

    rows: list[dict] = []
    for stat_id in sorted(stat_regs):
        regs = sorted(stat_regs[stat_id], key=lambda r: r.first_affected_draw)
        expected: list[date] = sorted(
            {d for reg in regs for d in _expected_dates(reg, asof)}
        )
        info = by_stat.get(
            stat_id, {"eligible": set(), "all_dates": set(), "order_phys": set()}
        )
        eligible = info["eligible"]
        # timeline = every scheduled position plus every actual draw position
        # (eligible or not); excluded positions break continuity.
        timeline = sorted(set(expected) | info["all_dates"])
        segments = contiguous_segments(timeline, eligible)
        # order-eligible segments: only positions with physical draw order;
        # any other timeline position (missing/ineligible/sorted-only) breaks.
        order_segs = contiguous_segments(timeline, info["order_phys"])
        first = regs[0]
        rows.append(
            {
                "game_id": first.game_id,
                "statistical_regime_id": stat_id,
                "main_ball_count": first.main_ball_count,
                "main_ball_min": first.main_ball_min,
                "main_ball_max": first.main_ball_max,
                "special_ball_count": first.special_ball_count or 0,
                "special_ball_min": first.special_ball_min or "",
                "special_ball_max": first.special_ball_max or "",
                "eligible_main_draw_count": len(eligible),
                "first_eligible_date": min(eligible).isoformat() if eligible else "",
                "last_eligible_date": max(eligible).isoformat() if eligible else "",
                "num_contiguous_segments": len(segments),
                "contiguous_sequence_segment_lengths": ";".join(
                    str(len(s)) for s in segments
                ),
                "num_order_eligible_segments": len(order_segs),
                "order_eligible_segment_lengths": ";".join(
                    str(len(s)) for s in order_segs
                ),
                "dataset_sha256": dataset_sha256,
            }
        )
    return rows


def observation_plan_hash(rows: list[dict]) -> str:
    """Deterministic hash of the frozen plan content."""
    payload = json.dumps(rows, sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def write_observation_plan(path: Path, rows: list[dict]) -> None:
    fields = [
        "game_id", "statistical_regime_id", "main_ball_count",
        "main_ball_min", "main_ball_max", "special_ball_count",
        "special_ball_min", "special_ball_max", "eligible_main_draw_count",
        "first_eligible_date", "last_eligible_date",
        "num_contiguous_segments", "contiguous_sequence_segment_lengths",
        "num_order_eligible_segments", "order_eligible_segment_lengths",
        "dataset_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
