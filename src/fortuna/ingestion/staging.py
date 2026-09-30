"""Staged draw records — one row per (source, artifact, draw) parse result.

Parsers produce StagedDraw records carrying exactly what the source reported
(no inference). The pipeline then reconciles staged records into canonical
Draw objects keyed by (game_id, draw_date, draw_stream).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from fortuna.schemas.draws import DrawStream, OrderSemantics


@dataclass
class StagedDraw:
    """A draw as reported by a single source artifact."""

    game_id: str
    draw_date: date
    draw_stream: DrawStream = DrawStream.MAIN
    main_numbers: list[int] = field(default_factory=list)
    special_ball: int | None = None
    multiplier: float | None = None
    jackpot: Decimal | None = None
    jackpot_winners: int | None = None
    drawing_identifier: str | None = None
    machine_id: str | None = None
    ball_set_id: str | None = None
    numbers_order: OrderSemantics = OrderSemantics.UNKNOWN_ORDER
    source_id: str = ""
    artifact_sha256: str = ""
    artifact_path: str = ""
    retrieved_at: datetime | None = None
    parser_version: str = ""
    notes: str | None = None
