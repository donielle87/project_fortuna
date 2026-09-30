"""Future historical-draw data contract (Task 9).

Defined now so Phase 1 ingestion lands on a stable, validated contract.
``ball_position`` in DrawNumber records the SOURCE-DEFINED ordering — physical
draw order if and only if the source preserves it. If order is unavailable,
``ball_position`` is null; it is never invented. For games where the official
source reports numbers in sorted order, positions 1..N mean "sorted ascending",
documented in docs/data_dictionary.md.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fortuna.schemas.common import parse_list


class BallType(str, Enum):
    MAIN = "main"
    SPECIAL = "special"


class DrawStream(str, Enum):
    """Which drawing within a game a record belongs to.

    ``DOUBLE_PLAY`` covers Florida Lotto Double Play (and Powerball Double
    Play should it ever be ingested): a separate drawing conducted after the
    main draw that must never be conflated with the main series.
    """

    MAIN = "main"
    DOUBLE_PLAY = "double_play"


class OrderSemantics(str, Enum):
    """What ``ball_position``/``main_numbers`` ordering means."""

    PHYSICAL_DRAW_ORDER = "physical_draw_order"
    SOURCE_SORTED_ORDER = "source_sorted_order"
    UNKNOWN_ORDER = "unknown_order"


class DrawValidationStatus(str, Enum):
    PENDING = "pending"
    VALID = "valid"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class Draw(BaseModel):
    """Header record for one official drawing."""

    model_config = ConfigDict(extra="forbid")

    draw_id: str = Field(pattern=r"^[A-Z]{2,4}-D-\d{4}-\d{2}-\d{2}(-[A-Z0-9]+)?$")
    game_id: str
    regime_id: str = Field(
        description="REQUIRED — no draw may exist without a regime assignment"
    )
    draw_date: date
    scheduled_datetime: datetime | None = None
    drawing_identifier: str | None = Field(
        default=None, description="Official draw/serial identifier if the source provides one"
    )
    draw_stream: DrawStream = DrawStream.MAIN

    main_numbers: list[int] = Field(
        min_length=1, description="Main-ball numbers in source-reported order"
    )
    numbers_order: OrderSemantics = Field(
        default=OrderSemantics.UNKNOWN_ORDER,
        description="Semantics of main_numbers ordering — never inferred",
    )
    special_ball: int | None = None
    multiplier: float | None = Field(
        default=None, description="Drawn multiplier (Power Play / Megaplier / built-in)"
    )

    jackpot: Decimal | None = Field(default=None, ge=0)
    jackpot_cash_value: Decimal | None = Field(default=None, ge=0)
    jackpot_winners: int | None = Field(default=None, ge=0)

    drawing_location: str | None = None
    machine_id: str | None = None
    ball_set_id: str | None = None

    source_id: str | None = None
    retrieved_at: datetime | None = None
    raw_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    parser_version: str | None = None
    ingestion_version: str | None = None
    validation_status: DrawValidationStatus = DrawValidationStatus.PENDING

    # Phase 1 additions
    analysis_eligible: bool = Field(
        default=False,
        description="False unless the record passes every eligibility gate "
        "(provenance, validation, regime, non-quarantined, non-provisional, "
        "no unresolved winning-number conflict).",
    )
    provisional: bool = Field(
        default=False,
        description="True for non-authoritative/secondary-source records "
        "retained for reconciliation only — never analysis-eligible.",
    )
    data_quality_notes: str | None = None
    corroborating_source_ids: list[str] = Field(default_factory=list)

    @field_validator("corroborating_source_ids", mode="before")
    @classmethod
    def _split_sources(cls, v: object) -> object:
        if v is None or isinstance(v, str):
            return parse_list(v)
        return v

    @field_validator("main_numbers", mode="before")
    @classmethod
    def _split_numbers(cls, v: object) -> object:
        if isinstance(v, str):
            return [int(x) for x in parse_list(v)]
        return v

    def to_draw_numbers(self) -> list["DrawNumber"]:
        """Normalized representation. Positions are source-reported order
        (physical draw order only if the source preserves it — see module
        docstring)."""
        rows = [
            DrawNumber(
                draw_id=self.draw_id,
                ball_position=i + 1,
                ball_type=BallType.MAIN,
                number=n,
                position_semantics=self.numbers_order,
            )
            for i, n in enumerate(self.main_numbers)
        ]
        if self.special_ball is not None:
            rows.append(
                DrawNumber(
                    draw_id=self.draw_id,
                    ball_position=len(self.main_numbers) + 1,
                    ball_type=BallType.SPECIAL,
                    number=self.special_ball,
                    position_semantics=self.numbers_order,
                )
            )
        return rows


class DrawNumber(BaseModel):
    """One ball in one draw — normalized form (draw_id, position, number)."""

    model_config = ConfigDict(extra="forbid")

    draw_id: str
    ball_position: int | None = Field(
        default=None,
        description="Source-defined ordering; None iff order is not preserved",
    )
    ball_type: BallType = BallType.MAIN
    number: int
    position_semantics: OrderSemantics = OrderSemantics.UNKNOWN_ORDER

    @model_validator(mode="after")
    def _check_position(self) -> "DrawNumber":
        if self.ball_position is not None and self.ball_position < 1:
            raise ValueError("ball_position must be >= 1 or None")
        return self
